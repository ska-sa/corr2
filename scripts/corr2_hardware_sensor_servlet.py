#!/usr/bin/env python

from __future__ import print_function
import logging
import sys
import argparse
import os
import katcp
import signal
import casperfpga
from tornado.ioloop import IOLoop
import tornado.gen as gen

from corr2 import sensors
from corr2.sensors import Corr2Sensor
from corr2.utils import KatcpStreamHandler
from concurrent.futures import ThreadPoolExecutor

LOGGER = logging.getLogger(__name__)

class Corr2HardwareSensorServer(katcp.DeviceServer):
    def __init__(self, *args, **kwargs):
        super(Corr2HardwareSensorServer, self).__init__('127.0.0.1',kwargs["port"])
        self.set_concurrency_options(thread_safe=False, handler_thread=False)
        self.host = casperfpga.CasperFpga(kwargs["skarab_host"])
        self.sensor_manager = sensors.SensorManager(self, instrument=None)

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
        sensor_manager=self.sensor_manager

        ioloop = getattr(sensor_manager.instrument, 'ioloop', None)
        if not ioloop:
            ioloop = getattr(sensor_manager.katcp_server, 'ioloop', None)
        if not ioloop:
            raise RuntimeError('IOLoop-containing katcp version required. Can go '
                               'no further.')
        sensor_manager.sensors_clear()

        sensordict=self.host.transport.get_sensor_data()
        sensors={}
        for key,value in sensordict.iteritems():
            try:
                if type(value[0]) == float:
                    sensortype=Corr2Sensor.float
                elif type(value[0]) == int:
                    sensortype=Corr2Sensor.integer
                elif type(value[0]) == bool:
                    sensortype=Corr2Sensor.boolean
                elif type(value[0]) == str:
                    sensortype=Corr2Sensor.string
                else:
                    raise RuntimeError("Unknown datatype!")
                sensors[key]=sensor_manager.do_sensor(
                sensortype, '{}'.format(key),
                'a generic HW sensor',unit=value[1])
            except Exception as e:
                LOGGER.error('Unable to add sensor {}-{}. Skipping.'.format(key,value))
                raise e
        ioloop.add_callback(_sensor_cb_hw, executor, sensors, self.host)


@gen.coroutine
def _sensor_cb_hw(executor, sensors, host):
    """
    Sensor call back to check all HW sensors
    :param sensors: per-host dict of sensors
    :return:
    """
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
    try:
        results = yield executor.submit(host.transport.get_sensor_data)
    except Exception as e:
        LOGGER.error('Error retrieving %s sensors - {}'.format(host.host,e.message))
        results={}
        set_failure()
    for key,value in results.iteritems():
        try:
            status=Corr2Sensor.NOMINAL if value[2]=='OK' else Corr2Sensor.ERROR
            sensors[key].set(value=value[0],status=status)
        except Exception as e:
            LOGGER.error('Error updating {}-{} sensor '
                     '- {}'.format(host.host,key,e.message))
    LOGGER.debug('sensorloop ran')
    IOLoop.current().call_later(10, _sensor_cb_hw,
                                executor,sensors,host)

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
    except:
        raise RuntimeError('Received nonsensical log level %s' % args.loglevel)

    # set up the logger
    corr2_sensors_logger = logging.getLogger('hardware_sensors')
    corr2_sensors_logger.setLevel(log_level)
    if args.lfm or (not sys.stdout.isatty()):
        console_handler = KatcpStreamHandler(stream=sys.stdout)
        console_handler.setLevel(log_level)
        corr2_sensors_logger.addHandler(console_handler)
    else:
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                      '%(filename)s:%(lineno)s - '
                                      '%(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        corr2_sensors_logger.addHandler(console_handler)


    ioloop = IOLoop.current()
    sensor_server = Corr2HardwareSensorServer('127.0.0.1', port=args.port, skarab_host=args.host)
    signal.signal(signal.SIGINT,
                  lambda sig, frame: ioloop.add_callback_from_signal(
                      on_shutdown, ioloop, sensor_server))
    print('Hardware sensor server for %s listening on port %d:' %(args.host,args.port), end='')
    #sensor_server.initialise()
    sensor_server.set_ioloop(ioloop)
    ioloop.add_callback(sensor_server.start)
    print('started. Running somewhere in the ether... '
          'exit however you see fit.')
    ioloop.add_callback(sensor_server.initialise)
    ioloop.start()

# end
