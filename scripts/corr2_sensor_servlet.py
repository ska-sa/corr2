#!/usr/bin/env python

import logging
import sys
import argparse
import os
import katcp
import signal
import tornado

from tornado.ioloop import IOLoop
from corr2 import sensors, fxcorrelator


class KatcpLogFormatter(logging.Formatter):
    def format(self, record):
        translate_levels = {'INFO': 'info',
                            'DEBUG': 'debug',
                            'WARNING': 'warn',
                            }
        if record.levelname in translate_levels:
            record.levelname = translate_levels[record.levelname]
        else:
            record.levelname = record.levelname.lower()
        record.msg = record.msg.replace(' ', '\_')
        return super(KatcpLogFormatter, self).format(record)


class KatcpLogEmitHandler(logging.StreamHandler):

    def __init__(self, katcp_server, stream=None):
        self.katcp_server = katcp_server
        super(KatcpLogEmitHandler, self).__init__(stream)

    def emit(self, record):
        """
        Replace a regular log emit with sending a katcp
        log message to all connected clients.
        """
        try:
            inform_msg = self.katcp_server.create_log_inform(record.levelname.lower(),
                                                             record.msg,
                                                             record.filename)
            self.katcp_server.mass_inform(inform_msg)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


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

    def initialise(self, instrument):
        """
        Setup and start sensors
        :param:
        :return:

        """
        self.instrument = instrument
        self.instrument.initialise(program=False)
        sensors.setup_sensors(instrument=self.instrument, katcp_server=self)


@tornado.gen.coroutine
def on_shutdown(ioloop, server):
    print('Shutting down')
    yield server.stop()
    ioloop.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start a corr2 sensor server.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-p', '--port', dest='port', action='store', default=1235, type=int,
                        help='bind to this port to receive KATCP messages')
    parser.add_argument('--log_level', dest='loglevel', action='store', default='INFO',
                        help='log level to set')
    parser.add_argument('--log_format_katcp', dest='lfm', action='store_true', default=False,
                        help='format log messsages for katcp')
    parser.add_argument('--config', dest='config', type=str, action='store', default='',
                        help='a corr2 config file')
    args = parser.parse_args()

    try:
        log_level = eval('logging.%s' % args.loglevel)
    except:
        raise RuntimeError('Received nonsensical log level %s' % args.loglevel)

    # set up the logger
    corr2_sensors_logger = logging.getLogger('corr2.sensors')
    corr2_sensors_logger.setLevel(log_level)
    if args.lfm or (not sys.stdout.isatty()):
        use_katcp_logging = True
    else:
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                      '%(filename)s:%(lineno)s - '
                                      '%(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        corr2_sensors_logger.addHandler(console_handler)
        use_katcp_logging = False

    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']
    if args.config == '':
        raise RuntimeError('No config file.')

    ioloop = IOLoop.current()
    sensor_server = Corr2SensorServer('127.0.0.1', args.port)
    signal.signal(signal.SIGINT, lambda sig, frame:
    ioloop.add_callback_from_signal(on_shutdown, ioloop, sensor_server))
    print 'Sensor Server listening on port %d, ' % args.port
    sensor_server.set_ioloop(ioloop)
    ioloop.add_callback(sensor_server.start)
    instrument = fxcorrelator.FxCorrelator('RTS correlator', config_source=args.config)
    ioloop.add_callback(sensor_server.initialise, instrument)
    ioloop.start()
