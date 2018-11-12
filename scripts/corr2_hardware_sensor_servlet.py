#!/usr/bin/env python

from __future__ import print_function
import logging
import sys
import argparse
import katcp
import signal
import casperfpga
import socket
import math
from tornado.ioloop import IOLoop
import tornado.gen as gen

from corr2 import sensors
from corr2.sensors import Corr2Sensor
from concurrent.futures import ThreadPoolExecutor

LOGGER = logging.getLogger(__name__)


class Corr2HardwareSensorServer(katcp.DeviceServer):
    def __init__(self, *args, **kwargs):
        super(
            Corr2HardwareSensorServer,
            self).__init__(
            '127.0.0.1',
            kwargs["port"])
        self.set_concurrency_options(thread_safe=False, handler_thread=False)
        self.host = casperfpga.CasperFpga(kwargs["skarab_host"])
        self.sensor_manager = sensors.SensorManager(self, instrument=None)
        self.rack_location_tuple = get_physical_location(
            socket.gethostbyname(self.host.transport.host))

    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        return

    def initialise(self):
        """
        Setup and start sensors
        :return:

        """
        executor = ThreadPoolExecutor(max_workers=1)
        sensor_manager = self.sensor_manager

        ioloop = getattr(sensor_manager.instrument, 'ioloop', None)
        if not ioloop:
            ioloop = getattr(sensor_manager.katcp_server, 'ioloop', None)
        if not ioloop:
            raise RuntimeError(
                'IOLoop-containing katcp version required. Can go '
                'no further.')
        sensor_manager.sensors_clear()

        sensordict = self.host.transport.get_sensor_data()
        sensordict['location'] = self.rack_location_tuple
        print('***********',self.rack_location_tuple,'************')
        device_status = 'OK' if (
            is_sensor_list_status_ok(sensordict)) else 'ERROR'
        sensordict['device-status'] = (0, '', device_status)
        sensors = {}
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
                sensors[key] = sensor_manager.do_sensor(
                    sensortype, '{}'.format(key),
                    'a generic HW sensor', unit=value[1])
            except Exception as e:
                LOGGER.error(
                    'Unable to add sensor {}-{}. Skipping.'.format(key, value))
                raise e
        ioloop.add_callback(
            _sensor_cb_hw,
            executor,
            sensors,
            self.host,
            self.rack_location_tuple)


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
    rackRow = int((leafNo-1) // 2)
    print(rackRow)
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
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    try:
        results = yield executor.submit(host.transport.get_sensor_data)
    except Exception as e:
        LOGGER.error(
            'Error retrieving %s sensors - {}'.format(host.host, e.message))
        results = {}
        set_failure()



    # Board Sensors
    for key, value in results.iteritems():
        try:
            status = Corr2Sensor.NOMINAL if value[2] == 'OK' else Corr2Sensor.ERROR
            sensors[key].set(value=value[0], status=status)
        except Exception as e:
            LOGGER.error('Error updating {}-{} sensor '
                         '- {}'.format(host.host, key, e.message))

    # Server Generated Sensors
    server_sensors_dict = {}
    server_sensors_dict['location'] = rack_location_tuple

    onBoardSensorsOk=is_sensor_list_status_ok(results);
    serverSensorsOk=is_sensor_list_status_ok(server_sensors_dict);

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
            LOGGER.error('Error updating {}-{} sensor '
                         '- {}'.format(host.host, key, e.message))

    LOGGER.debug('sensorloop ran')
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
    parser.add_argument('-p', '--port', dest='port', action='store',
                        default=1235, type=int,
                        help='bind to this port to receive KATCP messages')
    parser.add_argument('--log_level', dest='loglevel', action='store',
                        default='FATAL', help='log level to set')
    parser.add_argument('--log_format_katcp', dest='lfm', action='store_true',
                        default=False, help='format log messsages for katcp')
    parser.add_argument('--host', dest='host', action='store',
                        help='SKARAB hostname or IP address to connect to.')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.loglevel)
    except BaseException:
        raise RuntimeError('Received nonsensical log level %s' % args.loglevel)

    ioloop = IOLoop.current()
    sensor_server = Corr2HardwareSensorServer(
        '127.0.0.1', port=args.port, skarab_host=args.host)
    signal.signal(signal.SIGINT,
                  lambda sig, frame: ioloop.add_callback_from_signal(
                      on_shutdown, ioloop, sensor_server))
    print('Hardware sensor server for %s listening on port %d:' % (args.host, args.port), end='')
    # sensor_server.initialise()
    sensor_server.set_ioloop(ioloop)
    ioloop.add_callback(sensor_server.start)
    print('started. Running somewhere in the ether... '
          'exit however you see fit.')
    ioloop.add_callback(sensor_server.initialise)
    ioloop.start()

# end

