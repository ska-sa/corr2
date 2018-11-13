#!/usr/bin/env python

from __future__ import print_function
import os
import logging
import sys
import argparse
import katcp
from katcp.kattypes import request, return_reply, Float, Int, Str, Bool
import signal
from tornado import gen
from tornado.ioloop import IOLoop
import Queue
import time
import casperfpga
import socket
import math
from concurrent import futures

import corr2

from corr2 import sensors
from corr2.sensors import Corr2Sensor
from corr2.utils import parse_ini_file

from corr2.corr2LogHandlers import getKatcpLogger, set_logger_group_level
from corr2.corr2LogHandlers import get_instrument_loggers, check_logging_level
from corr2.corr2LogHandlers import check_logging_level, LOG_LEVELS
from corr2.corr2LogHandlers import LOGGING_RATIO_CASPER_CORR as LOG_RATIO

from corr2 import corr_monitoring_loop as corr_mon_loop


class Corr2HardwareSensorServer(katcp.DeviceServer):

    # Interface version information.
    VERSION_INFO = ('corr2 hardware sensor servlet', 0, 1)

    # Device server build / instance information.
    BUILD_INFO = ('corr2', 0, 1, 'alpha')

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
                log_file_dir = os.path.abspath('.')
            else:
                log_file_dir = '/var/log/skarab'

            start_time = str(time.time())
            log_filename = '{}_hardware_sensor_servlet.log'.format(kwargs['skarab_host'])

            self.sensor_manager = corr2.sensors.SensorManager(self, instrument=None,
                mass_inform_func=self.mass_inform,
                log_filename=log_filename,
                log_file_dir=log_file_dir)

            self.rack_location_tuple = get_physical_location(socket.gethostbyname(self.host.transport.host))
            self.sensors = {}

            sensor_manager = self.sensor_manager
            sensor_manager.sensors_clear()

            sensordict = self.host.transport.get_sensor_data()
            sensordict['location'] = self.rack_location_tuple
            sensordict['boot_image'] = parse_boot_image_return(self.host.transport.get_virtex7_firmware_version())
            device_status = 'OK' if (
                is_sensor_list_status_ok(sensordict)) else 'ERROR'
            sensordict['device-status'] = (0, '', device_status)


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

    def start_sensor_loop(self):
        IOLoop.current().add_callback(
            _sensor_cb_hw,
            self.executor,
            self.sensors,
            self.host,
            self.rack_location_tuple)

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
        self.host.logger.info('Reseting Skarab: {}'.format(self.host.host))
        self.host.transport.reset_fpga()
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
    #print(rackRow)
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
            return 0
    return 1


@gen.coroutine
def _sensor_cb_hw(executor, sensors, host, rack_location_tuple):
    """
    Sensor call back to check all HW sensors
    :param sensors: per-host dict of sensors
    :return:
    """
    #print('Running Loop')

    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                    value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    try:
        results = yield executor.submit(host.transport.get_sensor_data)
    except Exception as e:
        host.logger.error(
            'Error retrieving {}s sensors - {}'.format(host.host, e.message))
        results = {}
        set_failure()

    # Board Sensors
    for key, value in results.iteritems():
        try:
            status = Corr2Sensor.NOMINAL if value[2] == 'OK' else Corr2Sensor.ERROR
            sensors[key].set(value=value[0], status=status)
        except Exception as e:
            host.logger.error('Error updating {}-{} sensor '
                '- {}'.format(host.host, key, e.message))

    # Server Generated Sensors
    server_sensors_dict = {}
    server_sensors_dict['location'] = rack_location_tuple
    try:
        server_sensors_dict['boot_image'] = parse_boot_image_return(host.transport.get_virtex7_firmware_version())
    except Exception as e:
        host.logger.error('Error connecting to host {} - {}'.format(host.host, e.message))
        set_failure()
        IOLoop.current().call_later(10, _sensor_cb_hw,
            executor, sensors, host, rack_location_tuple)
        return

    onBoardSensorsOk = is_sensor_list_status_ok(results)
    serverSensorsOk = is_sensor_list_status_ok(server_sensors_dict)

    device_status = 'OK'
    if(not onBoardSensorsOk or not serverSensorsOk):
        device_status = 'ERROR'

    server_sensors_dict['device-status'] = (0, '', device_status)

    # Determine Device Status
    for key, value in server_sensors_dict.iteritems():
        try:
            status = Corr2Sensor.NOMINAL if value[2] == 'OK' else Corr2Sensor.ERROR
            sensors[key].set(value=value[0], status=status)
        except Exception as e:
            host.logger.error('Error updating {}-{} sensor '
                              '- {}'.format(host.host, key, e.message))

    host.logger.debug('sensorloop ran')
    IOLoop.current().call_later(10, _sensor_cb_hw,
            executor, sensors, host, rack_location_tuple)


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


if __name__ == '__main__':
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
        '--log_here', dest='log_here', action='store', default=True,
        help='Log to file here or in /var/log/skarab')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.loglevel)
    except Exception:
        raise RuntimeError('Received nonsensical log level {}'.format(args.loglevel))

    # set up the logger
    #root_logger = logging.getLogger()
    #root_logger.setLevel(log_level)
    # while len(root_logger.handlers) > 0:
    #     root_logger.removeHandler(root_logger.handlers[0])
    #root_logger.handlers = []
    #if args.lfm or (not sys.stdout.isatty()):
    #    console_handler = KatcpStreamHandler(stream=sys.stdout)
    #    console_handler.setLevel(log_level)
    #    root_logger.addHandler(console_handler)
    #else:
    #    console_handler = logging.StreamHandler(stream=sys.stdout)
    #    console_handler.setLevel(log_level)
    #    formatter = logging.Formatter(
    #        '%(asctime)s - %(name)s - %(filename)s:%(lineno)s - %(levelname)s - %(message)s')
    #    console_handler.setFormatter(formatter)
    #root_logger.addHandler(console_handler)

    server = Corr2HardwareSensorServer('127.0.0.1', args.port, tornado=(not args.no_tornado),
                                       skarab_host=args.host, log_here=args.log_here)
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
# end
