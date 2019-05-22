#!/usr/bin/env python

from __future__ import print_function
import logging
import traceback2 as traceback
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
from corr2.corr2LogHandlers import getKatcpLogger, reassign_log_handlers
from corr2.utils import parse_ini_file


class Corr2SensorServer(katcp.DeviceServer):

    def __init__(self, *args, **kwargs):
        super(Corr2SensorServer, self).__init__(*args, **kwargs)
        self.set_concurrency_options(thread_safe=False, handler_thread=False)
        self.instrument = None

    def _log_excep(self, excep, msg=''):
        """
        Log an error and return fail
        :param excep: the exception that caused us to fail
        :param msg: the error message to log
        :return:
        """
        message = msg
        if excep is not None:
            template = '\nAn exception of type {0} occured. Arguments: {1!r}'
            message += template.format(type(excep).__name__, excep.args)
        if self.instrument:
            self.instrument.logger.error(message)
        else:
            logging.error(message)
        return 'fail', message

    def _log_stacktrace(self, stack_trace, msg=''):
        """
        Log a stack_trace and return fail
        :param stack_trace: String formatted using traceback2 utility
        :param msg: the error message to log
        :return:
        """
        log_message = '{} \n {}'.format(msg, stack_trace)
        if self.instrument:
            self.instrument.logger.error(log_message)
        else:
            logging.error(log_message)
        return 'fail', log_message

    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        pass

    def initialise(self, config, name):
        """
        Setup and start sensors
        :param config: the config to use when making the instrument
        :param name: a name for the instrument
        :return:

        """
        try:
            _default_log_dir = '/var/log/corr'
            config_file_dict = parse_ini_file(config)
            log_file_dir = config_file_dict.get('FxCorrelator').get('log_file_dir', _default_log_dir)
            assert os.path.isdir(log_file_dir)
            
            start_time = str(time.time())
            ini_filename = os.path.basename(config)
            log_filename = '{}_{}_sensor_servlet.log'.format(ini_filename, start_time)

            self.instrument = fxcorrelator.FxCorrelator(
                                'snsrs', config_source=config,
                                mass_inform_func=self.mass_inform, getLogger=getKatcpLogger,
                                log_filename=log_filename, log_file_dir=log_file_dir)
            self.instrument.initialise(program=False, configure=False, require_epoch=False,
                                    mass_inform_func=self.mass_inform, getLogger=getKatcpLogger,
                                    log_filename=log_filename, log_file_dir=log_file_dir)
            
            #disable manually-issued sensor update informs (aka 'kcs' sensors):
            sensor_manager = sensors.SensorManager(self, self.instrument,kcs_sensors=False,
                                                    mass_inform_func=self.mass_inform,
                                                    log_filename=log_filename,
                                                    log_file_dir=log_file_dir)
            self.instrument.sensor_manager = sensor_manager
            sensors_periodic.setup_sensors(sensor_manager)

            # Function created to reassign all non-conforming log-handlers
            loggers_changed = reassign_log_handlers(mass_inform_func=self.mass_inform, 
                                                    log_filename=log_filename, 
                                                    log_file_dir=log_file_dir,
                                                    instrument_name=self.instrument.descriptor)
            
        except Exception as exc:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed to initialise sensor_servlet.')

    
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

@tornado.gen.coroutine
def boop():
    """
    Shut down the ioloop sanely.
    :param ioloop: the current tornado.ioloop.IOLoop
    :param server: a katcp.DeviceServer instance
    :return:
    """
    print('Boop a bop')
    startTime = tornado.ioloop.time.time()
    nextTime = tornado.ioloop.time.time() + 2
    IOLoop.current().call_at(nextTime,boop)

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
    parser.add_argument('-n', '--name', dest='name', action='store',
                        default='', help='a name for the instrument')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.loglevel)
    except AttributeError:
        raise RuntimeError('Received nonsensical log level %s' % args.loglevel)

    # def boop():
    #     raise KeyboardInterrupt

    
    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']
    if args.config == '':
        raise RuntimeError('No config file.')

    if args.name == '':
        # default to config file name?
        try:
            #whole path
            args.name = args.config
            #last part
            args.name = args.name.split('/')[-1]
            #remove extension, if present
            args.name = args.name.split('.')[-2]
        except IndexError:
            pass

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
    ioloop.add_callback(sensor_server.initialise, args.config, args.name)
    #ioloop.call_later(2, boop)
    ioloop.start()

# end
