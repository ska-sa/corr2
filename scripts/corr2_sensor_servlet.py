#!/usr/bin/env python

from __future__ import print_function
import logging
import sys
import argparse
import os
import katcp
import signal
from tornado.ioloop import IOLoop
import tornado.gen
import time
from ConfigParser import ConfigParser

from corr2 import sensors, sensors_periodic, fxcorrelator
from corr2.utils import KatcpStreamHandler


class Corr2SensorServer(katcp.DeviceServer):

    def __init__(self, *args, **kwargs):
        super(Corr2SensorServer, self).__init__(*args, **kwargs)
        self.set_concurrency_options(thread_safe=False, handler_thread=False)
        self.instrument = None

    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        pass

    def initialise(self, config):
        """
        Setup and start sensors
        :param config: the config to use when making the instrument
        :return:

        """
        instrument = fxcorrelator.FxCorrelator(
            'dummy fx correlator for sensors', config_source=config)
        self.instrument = instrument
        self.instrument.initialise(program=False, configure=False,
                                   require_epoch=False)
        #disable manually-issued sensor update informs (aka 'kcs' sensors):
        sensor_manager = sensors.SensorManager(self, self.instrument,kcs_sensors=False)
        self.instrument.sensor_manager = sensor_manager
        sensors_periodic.setup_sensors(sensor_manager,enable_counters=False)


@tornado.gen.coroutine
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
        description='Start a corr2 sensor server.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-p', '--port', dest='port', action='store',
                        default=1235, type=int,
                        help='bind to this port to receive KATCP messages')
    parser.add_argument('--log_level', dest='loglevel', action='store',
                        default='WARN', help='log level to set')
    parser.add_argument('--log_format_katcp', dest='lfm', action='store_true',
                        default=False, help='format log messsages for katcp')
    parser.add_argument('--config', dest='config', type=str, action='store',
                        default='', help='a corr2 config file')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.loglevel)
    except AttributeError:
        raise RuntimeError('Received nonsensical log level %s' % args.loglevel)

    # def boop():
    #     raise KeyboardInterrupt

    # set up the logger
    corr2_sensors_logger = logging.getLogger('corr2.sensors')
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

    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']
    if args.config == '':
        raise RuntimeError('No config file.')

    # Always log to file.
    cp = ConfigParser()
    cp.read(args.config)
    iname = os.path.basename(args.config)
    start_time = str(time.time())
    logfiles_path = cp.get('FxCorrelator', 'log_file_dir')
    assert os.path.isdir(logfiles_path)
    log_filename = '{}/{}_{}_sensor_servlet.log'.format(logfiles_path,
        iname.strip().replace(' ', '_'), start_time)
    file_handler = logging.FileHandler("{}".format(log_filename))
    file_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                '%(filename)s:%(lineno)s - '
                                '%(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    corr2_sensors_logger.addHandler(file_handler)

    ioloop = IOLoop.current()
    sensor_server = Corr2SensorServer('127.0.0.1', args.port)
    signal.signal(signal.SIGINT,
                  lambda sig, frame: ioloop.add_callback_from_signal(
                      on_shutdown, ioloop, sensor_server))
    print('Sensor server listening on port %d:' % args.port, end='')
    sensor_server.set_ioloop(ioloop)
    ioloop.add_callback(sensor_server.start)
    print('started. Running somewhere in the ether... '
          'exit however you see fit.')
    ioloop.add_callback(sensor_server.initialise, args.config)
    # ioloop.call_later(10, boop)
    ioloop.start()

# end
