#!/usr/bin/env python

from __future__ import print_function

import os, sys, logging
import signal, time
import traceback2 as traceback
import tornado.gen

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from katcp import DeviceServer
from tornado.ioloop import IOLoop

from corr2 import sensors_periodic
from corr2.fxcorrelator import FxCorrelator
from corr2.sensors import SensorManager
from corr2.utils import parse_ini_file
from corr2.corr2LogHandlers import getKatcpLogger, reassign_log_handlers, \
                                    create_katcp_and_file_handlers

import IPython

_DEFAULT_LOG_DIR = '/var/log/corr'

class Corr2SensorServer(DeviceServer):

    def __init__(self, *args, **kwargs):
        try:
            self.config_filename = kwargs.pop('config', None)
            self.instrument_name = kwargs.pop('iname', 'snsrs')

            config_file_dict = parse_ini_file(self.config_filename)
            self.log_file_dir = config_file_dict.get('FxCorrelator').get('log_file_dir', _DEFAULT_LOG_DIR)
            assert os.path.isdir(self.log_file_dir)
            
            start_time_str = str(time.time())
            if 'ini' in os.path.basename(self.config_filename):
                self.config_filename = os.path.basename(self.config_filename).rsplit('.', 1)[0]
            # else: Continue!
            self.log_filename = '{}_{}_sensor_servlet.log'.format(
                                    os.path.basename(self.config_filename), start_time_str)
            self.log_level = kwargs.pop('log_level', logging.WARN)

            super(Corr2SensorServer, self).__init__(*args, **kwargs)

            # Rename DeviceServer._logger
            self._logger.name = '{}_{}'.format(self.instrument_name, self._logger.name)
            create_katcp_and_file_handlers(self._logger, self.mass_inform,
                                            self.log_filename, self.log_file_dir,
                                            self.log_level)
            
            self.set_concurrency_options(thread_safe=False, handler_thread=False)
            self.instrument = None
        except AssertionError as ex:
            stack_trace = traceback.format_exc()
            errmsg = 'Logging directory does not exist: {}'.format(self.log_file_dir)
            self._log_stacktrace(stack_trace, errmsg)
        except Exception as ex:
            # Oh dear
            stack_trace = traceback.format_exc()
            self._log_stacktrace(stack_trace, 'Failed to start sensor_servlet')


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
        
        self._logger.error(message)

        return 'fail', message

    def _log_stacktrace(self, stack_trace, msg=''):
        """
        Log a stack_trace and return fail
        :param stack_trace: String formatted using traceback2 utility
        :param msg: the error message to log
        :return:
        """
        log_message = '{} \n {}'.format(msg, stack_trace)
        self._logger.error(log_message)

        return 'fail', log_message

    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        pass

    def _set_log_level(self, log_level):
        """
        Sets the log level, not implemented properly, do not use if you dont know what you are doing
        """
        self.log_level = log_level;

    def initialise(self, config):
        """
        Setup and start sensors
        :param config: the config to use when making the instrument
        :return:

        """
        try:
            self.instrument = FxCorrelator(
                              self.instrument_name, config_source=config,
                              mass_inform_func=self.mass_inform, getLogger=getKatcpLogger,
                              log_filename=self.log_filename, log_file_dir=self.log_file_dir)
            self.instrument.initialise(program=False, configure=False, require_epoch=False,
                                        mass_inform_func=self.mass_inform,
                                        getLogger=getKatcpLogger,
                                        log_filename=self.log_filename,
                                        log_file_dir=self.log_file_dir,
                                        logLevel=self.log_level)
            
            # Disable manually-issued sensor update informs (aka 'kcs' sensors):
            sensor_manager_inst = SensorManager(self, self.instrument,
                                                kcs_sensors=False,
                                                mass_inform_func=self.mass_inform,
                                                log_filename=self.log_filename,
                                                log_file_dir=self.log_file_dir,
                                                logLevel=self.log_level)

            self.instrument.set_sensor_manager(sensor_manager_inst)
            sensors_periodic.setup_sensors(self.instrument.sensor_manager)

            # Function created to reassign all non-conforming log-handlers
            loggers_changed = reassign_log_handlers(mass_inform_func=self.mass_inform, 
                                                    log_filename=self.log_filename, 
                                                    log_file_dir=self.log_file_dir,
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
    parser = ArgumentParser(
        description='Start a corr2 sensor server.',
        formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('-p', '--port', dest='port', action='store',
                        default=1236, type=int,
                        help='bind to this port to receive KATCP messages')
    parser.add_argument('--log_level', dest='log_level', action='store',
                        default='WARN', help='log level to set')
    parser.add_argument('--config', dest='config', type=str, action='store',
                        default=None, help='a corr2 config file')
    parser.add_argument('-n', '--name', dest='name', action='store',
                        default=None, help='a name for the instrument')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.log_level)
        if(args.log_level.upper() == "WARN"):
            log_level = logging.WARN;
        elif(args.log_level.upper() == "DEBUG"):
            log_level = logging.DEBUG;
        elif(args.log_level.upper() == "INFO"):
            log_level = logging.INFO;
        elif(args.log_level.upper() == "ERROR"):
            log_level = logging.ERROR;
    except:
        print("Log level not understood. Defaulting to WARN.")
        log_level = logging.WARN;

    # def boop():
    #     raise KeyboardInterrupt
    
    if 'CORR2INI' in os.environ.keys() and args.config is None:
        args.config = os.environ['CORR2INI']
    elif args.config is None:
        raise RuntimeError('No config file.')

    if args.name is None:
        # default to config file name?
        args.name = os.path.basename(args.config).rsplit('.', 1)[0]
        
    ioloop = IOLoop.current()
    sensor_server = Corr2SensorServer('127.0.0.1', args.port, config=args.config,
                                      iname=args.name, log_level=args.log_level)
    sensor_server._set_log_level(log_level)
    signal.signal(signal.SIGINT,
                  lambda sig, frame: ioloop.add_callback_from_signal(
                      on_shutdown, ioloop, sensor_server))
    print('Sensor server listening on port %d:' % args.port, end='')
    sensor_server.set_ioloop(ioloop)
    ioloop.add_callback(sensor_server.start)
    print('started. Running somewhere in the ether... '
          'exit however you see fit.')
    ioloop.add_callback(sensor_server.initialise, args.config)
    #ioloop.call_later(2, boop)
    ioloop.start()

# end
