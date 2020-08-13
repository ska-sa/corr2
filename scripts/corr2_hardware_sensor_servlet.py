#!/usr/bin/env python


#from __future__ import print_function
import os
import logging
#import sys
import argparse
import katcp
from katcp.kattypes import request, return_reply, Float, Int, Str, Bool
import signal
from tornado import gen
from tornado.ioloop import IOLoop
import time
import casperfpga
import socket
from concurrent import futures

import corr2

from corr2 import sensors
from corr2.sensors import Corr2Sensor
from corr2 import corr2LogHandlers

#This variable exists because of problems with kcs - the rack location sensor needs to be transmitted a few times
reportRackLocation = 0

class Corr2HardwareSensorServer(katcp.DeviceServer):

    # Interface version information.
    VERSION_INFO = ('corr2 hardware sensor servlet', 0, 1)

    # Device server build / instance information.
    BUILD_INFO = ('corr2', 0, 1, 'alpha')

    # @profile
    def __init__(self, *args, **kwargs):
        use_tornado = kwargs.pop('tornado')
        super(Corr2HardwareSensorServer, self).__init__(*args)
        if use_tornado:
            self.set_concurrency_options(thread_safe=False, handler_thread=False)
            self.executor = futures.ThreadPoolExecutor(max_workers=1)
            self.host = casperfpga.CasperFpga(kwargs["skarab_host"])
            self._created = False
            self._initialised = False

            if kwargs['log_here']:
                self.log_file_dir = os.path.abspath('.')
            else:
                self.log_file_dir = '/var/log/skarab'

            # set timeout for the sensor reads
            self.timeout = kwargs['timeout']

            start_time = str(time.time())
            self.log_filename = '{}_hardware_sensor_servlet.log'.format(kwargs['skarab_host'])
            self.log_level = kwargs.pop('log_level', logging.WARN)

            #I am not sure if this function needs to be here, it is called in the corr2_sensor_sevlet so I put it here to be consistent
            corr2LogHandlers.create_katcp_and_file_handlers(self._logger, self.mass_inform,
                                            self.log_filename, self.log_file_dir,
                                            self.log_level)

            self.sensor_manager = corr2.sensors.SensorManager(self, instrument=None,
                mass_inform_func=self.mass_inform,
                log_filename=self.log_filename,
                log_file_dir=self.log_file_dir,
                logLevel=self.log_level)

            self.rack_location_tuple = get_physical_location(socket.gethostbyname(self.host.transport.host))
            self.sensors = {}

            sensor_manager = self.sensor_manager
            sensor_manager.sensors_clear()

            sensordict = dict()

            #This initial get_sensor_data() call needs to succeed as it populates the sensor dictionary. As such it is called until success. 
            retrievedSensors = False
            while(retrievedSensors == False):
                try:
                    sensordict = self.host.transport.get_sensor_data(
                        timeout=self.timeout)
                    retrievedSensors = True
                except Exception as e:
                    self._logger.error(
                        'Error retrieving {}s sensors on startup - {}. Waiting ten seconds and trying again'.format(self.host, e.message))
                    time.sleep(10)

            for key, value in sensordict.iteritems():
                try:
                    if isinstance(value[0], float):
                        sensortype = Corr2Sensor.float
                    elif isinstance(value[0], int):
                        sensortype = Corr2Sensor.integer
                    elif isinstance(value[0], bool):
                        sensortype = Corr2Sensor.boolean
                    elif isinstance(value[0], str):
                        sensortype = Corr2Sensor.string
                    else:
                        raise RuntimeError("Unknown datatype!")
                    self.sensors[key] = sensor_manager.do_sensor(
                        sensortype, '{}'.format(key),
                        'a generic HW sensor', unit=value[1])
                except Exception as e:
                    self.sensor_manager.logger.error(
                        'Unable to add sensor {}-{}. Skipping.'.format(key, value))
                    raise e
            self.sensors['location'] = sensor_manager.do_sensor(
                    Corr2Sensor.string,'location',
                    'Rack location of this SKARAB',
                    initial_status=Corr2Sensor.NOMINAL,unit='unitless')
            self.sensors['location'].set_value(self.rack_location_tuple[0])

            self.sensors['boot_image'] = sensor_manager.do_sensor(
                    Corr2Sensor.string,'boot-image',
                    'Currently running FPGA image',
                    initial_status=Corr2Sensor.NOMINAL,unit='unitless')

            self.sensors['device_status'] = sensor_manager.do_sensor(
                    Corr2Sensor.device_status,'device-status',
                    'Overall SKARAB health')

            self._logger.info('{} init function complete.'.format(self.host))

    def start_sensor_loop(self):
        IOLoop.current().add_callback(
            _sensor_cb_hw,
            self.executor,
            self.sensors,
            self.host,
            self.timeout,
            self._logger)

    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        return

    @request()
    @return_reply()
    def request_ping(self, sock):
        """
        Just ping the server
        :param sock:
        :return: 'ok'
        """
        return 'ok',

    @request()
    @return_reply(Str())
    def request_reset_hardware_platform(self, sock):
        """
        Reset the skarab and checks if it is in a reset state.
        :param sock:
        :return: {'ok,'fail'}
        """

        tmpLevel = self._logger.level
        self._logger.setLevel(10)  # Set logging level to info to record this reset
        self._logger.info('Reseting Skarab: {}'.format(self.host.host))
        self._logger.setLevel(tmpLevel)
        self.host.transport.reboot_fpga()
        return ('ok', 'Reset Successful')



def get_physical_location(ipAddress):
    octets = ipAddress.split('.')
    leafNo = int(octets[2])
    switchPort = int(octets[3]) // 4 + 1

    leafBaseRU = 0
    if(leafNo % 2 == 1):
        leafBaseRU = 6
    else:
        leafBaseRU = 24

    rackColumn = 'B'
    rackRow = int((leafNo - 1) // 2)
    rackUnit = leafBaseRU + switchPort
    if(switchPort > 8):
        rackUnit += 1

    hardwareLocation = '{}{:02}:{:02}'.format(rackColumn, rackRow, rackUnit)

    errorStatus = 'OK'
    if(rackColumn != 'B' or rackRow < 2 or rackRow > 10
            or rackUnit < 7 or rackUnit > 41
            or rackUnit == 15 or rackUnit == 24 or rackUnit == 33):
        errorStatus = 'ERROR'

    return (hardwareLocation, 'string', errorStatus)


def parse_boot_image_return(tuple):
    imageType = ''
    errorStatus = 'OK'
    if(tuple[0] == 1):
        imageType = 'golden_image'
        errorStatus = 'ERROR'
    elif(tuple[1] == 1):
        imageType = 'multiboot'
    else:
        imageType = 'toolflow'
    return (imageType, '', errorStatus)


def is_sensor_list_status_ok(sensors_dict):
    for key, values in sensors_dict.iteritems():
        if(values[2].upper() == 'ERROR' and key != 'device-status'):
            return False
    return True


@gen.coroutine
def _sensor_cb_hw(executor, sensors, host, timeout, logger):
    """
    Sensor call back to check all HW sensors
    :param sensors: per-host dict of sensors
    :return:
    """

    def set_failure():
        for key, sensor in sensors.iteritems():
            if(key != 'location'):
                sensor.set(status=Corr2Sensor.UNREACHABLE,
                        value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
        time.sleep(0.5)
        IOLoop.current().call_later(5, _sensor_cb_hw, executor, sensors, host, timeout, logger)

    try:
        boot_image = parse_boot_image_return(host.transport.get_virtex7_firmware_version())
        sensors['boot_image'].set(value=boot_image[0],status=Corr2Sensor.NOMINAL)
    except Exception as e:
        logger.error('Error retrieving boot image state on host {} - {}'.format(host.host, e.message))
        set_failure()
        return

    global reportRackLocation;
    if(reportRackLocation<3):
	reportRackLocation+=1
    	rack_location_tuple = get_physical_location(socket.gethostbyname(host.transport.host))
	sensors['location'].set(value=rack_location_tuple[0],status=Corr2Sensor.WARN,timestamp=time.time())
    elif(reportRackLocation==3):
        reportRackLocation+=1
        rack_location_tuple = get_physical_location(socket.gethostbyname(host.transport.host))
	sensors['location'].set(value=rack_location_tuple[0],status=Corr2Sensor.NOMINAL,timestamp=time.time())


    try:
        results = yield executor.submit(host.transport.get_sensor_data,
                                        timeout=timeout)
    except Exception as e:
        logger.error(
            'Error retrieving {}s sensors - {}. Changing sensor status to UNREACHABLE'.format(host.host, e.message))
        set_failure()
        return

    for key, value in results.iteritems():
        try:
            if ((value[2].lower() == 'ok') or (value[2].lower() == 'nominal')):
                status = Corr2Sensor.NOMINAL
            elif value[2].lower() == 'warning': 
                status = Corr2Sensor.WARN
            elif value[2].lower() == 'error': 
                status = Corr2Sensor.ERROR
                logger.error('Sensor {} reporting an error. Value: {} {}'.format(key, value[0], value[1]))
            else:
                status = Corr2Sensor.UNKNOWN
            sensors[key].set(value=value[0], status=status)
        except Exception as e:
            logger.error('Error updating {}-{} sensor - {}'.format(host.host, key, e.message))
            time.sleep(0.5)
            try:
                sensors[key].set(status=Corr2Sensor.UNREACHABLE,
                        value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensors[key].type]][1])
            except:
                pass
    try:
        if is_sensor_list_status_ok(results):
            device_value = 'ok'
            device_status = Corr2Sensor.NOMINAL
        else:
            device_value = 'fail'
            device_status = Corr2Sensor.ERROR
        sensors['device_status'].set(value=device_value, status=device_status)
    except Exception as e:
        logger.error('Error updating {}-device-status sensor - {}'.format(host.host, e.message))
    logger.debug('sensorloop ran')
    time.sleep(0.5)
    IOLoop.current().call_later(10, _sensor_cb_hw, executor, sensors, host, timeout, logger)

@gen.coroutine
def on_shutdown(ioloop, server):
    """
    Shut down the ioloop sanely.
    :param ioloop: the current tornado.ioloop.IOLoop
    :param server: a katcp.DeviceServer instance
    :return:
    """
    print('Sensor server shutting down')
    yield server.stop()
    ioloop.stop()

def main():
    parser = argparse.ArgumentParser(
        description='Start a corr2 hardware sensor server.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-p', '--port', dest='port', action='store', default=1235, type=int,
        help='bind to this port to receive KATCP messages')
    parser.add_argument(
        '--log_level', dest='loglevel', action='store', default='INFO',
        help='log level to set')
    parser.add_argument(
        '--log_format_katcp', dest='lfm', action='store_true', default=False,
        help='format log messsages for katcp')
    parser.add_argument(
        '--no_tornado', dest='no_tornado', action='store_true', default=False,
        help='do NOT use the tornado version of the Katcp server')
    parser.add_argument(
        '--host', dest='host', action='store',
        help='SKARAB hostname or IP address to connect to.')
    parser.add_argument(
        '--log_here', dest='log_here', action='store_true', default=False,
        help='Log to file here or in /var/log/skarab')
    parser.add_argument(
        '--timeout', dest='timeout', action='store', default='0.1',
        help='set the timeout, in seconds, '
             'for sensor read requests to the SKARAB')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.loglevel)
    except Exception:
        raise RuntimeError('Received nonsensical log level {}'.format(args.loglevel))

    server = Corr2HardwareSensorServer('127.0.0.1', args.port,
                                       tornado=(not args.no_tornado),
                                       skarab_host=args.host,
                                       log_here=args.log_here,
                                       log_level=log_level,
                                       timeout=float(args.timeout))
    print('Server listening on port {} '.format(args.port, end=''))

    # def boop():
    #     raise KeyboardInterrupt

    if not args.no_tornado:
        ioloop = IOLoop.current()
        signal.signal(
            signal.SIGINT,
            lambda sig, frame: ioloop.add_callback_from_signal(
                on_shutdown, ioloop, server))
        server.set_ioloop(ioloop)
        ioloop.add_callback(server.start)
        ioloop.add_callback(server.start_sensor_loop)
        # ioloop.call_later(120, boop)
        # ioloop.add_callback(send_test_informs, server)
        print('started with ioloop. Running somewhere in the ether... '
            'exit however you see fit.')
        ioloop.start()
    else:
        queue = Queue.Queue()
        server.set_restart_queue(queue)
        server.start()
        print('started with no ioloop. Running somewhere in the ether... '
            'exit however you see fit.')
        try:
            while True:
                time.sleep(0.5)
                try:
                    device = queue.get(timeout=0.5)
                except Queue.Empty:
                    device = None
                if device is not None:
                    print('Stopping...')
                    device.stop()
                    device.join()
                    print('Restarting...')
                    device.start()
                    print('Started.')
        except KeyboardInterrupt:
            print('Shutting down...')
            server.stop()
            server.join()

if __name__ == '__main__':
    main()
# end
