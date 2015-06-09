__author__ = 'paulp'

import argparse
import sys
import time
import os
import ConfigParser

from casperfpga import tengbe

from corr2 import utils

from corr2.dsimhost_fpga import FpgaDsimHost

parser = argparse.ArgumentParser(description='Control the dsim-engine (fake digitiser.)',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--config', type=str, action='store', help=
                    'corr2 config file. (default: Use CORR2INI env var)')
parser.add_argument('--program', dest='program', action='store_true', default=False,
                    help='(re)program the fake digitiser')
parser.add_argument('--deprogram', dest='deprogram', action='store_true', default=False,
                    help='deprogram the fake digitiser')
parser.add_argument('--start', dest='start', action='store_true', default=False,
                    help='start the fake digitiser transmission')
parser.add_argument('--pulse', action='store_true', default=False, help=
                    'Send a pulse of fake packets. Does nothing if digitiser is '
                    'already transmitting, use --stop first. It will only work '
                    'once until the dsim-engine is reset, e.g using --resync '
                    'which can be used with --pulse (--resync will be applied first).')
parser.add_argument('--pulse-packets', action='store', default=100, help=
                    'Send out out this many data packets per polarisation if --pulse '
                    'is specified (default: %(default)d.')
parser.add_argument('--resync', action='store_true', default=False,
                    help='Restart digitiser time and then sync')
parser.add_argument('--stop', dest='stop', action='store_true', default=False,
                    help='stop the fake digitiser transmission')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
parser.add_argument('--ipython', action='store_true', default=False, help=
                    'Launch an embedded ipython shell once all is said and done')
parser.add_argument('--sine-source', nargs=3, default=False, help=
                    'Choose which sine to source, sin_0 or sin_1.\
                    Set Scale and Frequency')
parser.add_argument('--noise-source', nargs=2, default=False, help=
                    'Choose which Noise to source, noise_0 or noise_1.\
                    Set noise scale.')
parser.add_argument('--select-output', nargs=3, default=False, help=
                    'Choose which Output to source from, Output_0 or Output_1.\
                     Output Scale, choose between 0 - 1.\
                     Output types, choose from signal or test_vectors.')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if args.config:
    config_filename = args.config
else:
    try:
        config_filename = os.environ['CORR2INI']
    except KeyError:
        raise RuntimeError(
            'No config file speficied and environment var "CORR2INI" not defined')

corr_conf = utils.parse_ini_file(config_filename, ['dsimengine'])
dsim_conf = corr_conf['dsimengine']
dig_host = dsim_conf['host']

dhost = FpgaDsimHost(dig_host, config=dsim_conf)
print 'Connected to %s.' % dhost.host

if args.start and args.stop:
    raise RuntimeError('Start and stop? You must be crazy!')

something_happened = False
if args.program:
    dhost.initialise()
    something_happened = True
else:
    dhost.get_system_information()

if args.deprogram:
    dhost.deprogram()
    something_happened = True
    print 'Deprogrammed %s.' % dhost.host

if args.resync:
    print 'Reset digitiser timer and sync timer'
    dhost.data_resync()
    something_happened = True

if args.start:
    # start tx
    print 'Starting TX on %s' % dhost.host,
    sys.stdout.flush()
    dhost.enable_data_output(enabled=True)
    dhost.registers.control.write(gbe_txen=True)
    print 'done.'
    sys.stdout.flush()
    something_happened = True

if args.stop:
    dhost.enable_data_output(enabled=False)
    print 'Stopped transmission on %s.' % dhost.host
    something_happened = True

if args.pulse:
    dhost.pulse_data_output(args.pulse_packets)
    print 'Pulsed {} packets per polarisation'.format(args.pulse_packets)
    something_happened = True

if args.ipython:
    """Embedding ipython for debugging"""
    import IPython
    IPython.embed()
    something_happened = True

if args.sine_source:
    """Sine source selection field, including source ,scale and frequency"""
    sine_source = args.sine_source[0]
    xscale = float(args.sine_source[1])
    yfreq = float(args.sine_source[2])
    try:
        sinesource = getattr(dhost.sine_sources, 'sin_{}'.format(sine_source))
        maxfreq = "{}MHz".format( sinesource.max_freq / 1e6 )
        sinesource.set(scale=xscale, frequency=yfreq)
        print "Sine Source:", sinesource.name
        print "Scale:", sinesource.scale
        print "Frequency:", sinesource.frequency        
    except AttributeError:
        print "You can only select between, sin_0 or sin_1"
        sys.exit(1)
    except ValueError:
        print "Error, verify your inputs"
        sys.exit(1)
    something_happened = True

if args.noise_source:
    """Noise selection, selectiong source of noise and scale"""
    noisesource = args.noise_source[0]
    noisescale = float(args.noise_source[1])
    try:
        source_from = getattr(dhost.noise_sources, 'noise_{}'.format(noisesource))
        source_from.set(scale=noisescale)
        print "Noise Source:", source_from.name
        print "Noise Scale:", source_from.scale
    except AttributeError:
        print "You can only select between:", dhost.noise_sources.names()
        sys.exit(1)
    except ValueError:
        print "Valid scale input is between 0 - 1."
        sys.exit(1)
    something_happened = True

if args.select_output:
    output_select = int(args.select_output[0])
    output_scale = float(args.select_output[1])
    output_type = args.select_output[2]   
    try:
        output_from = getattr(dhost.outputs, 'out_{}'.format(output_select))
        output_from.select_output(output_type)
        output_from.scale_output(output_scale)
        """Check if it can read what was written to it!"""
        print "Output Selected:", output_from.name
        print "Output Scale:",  output_from.scale_register.read()['data']['scale']
        print "Output Type:", output_from.output_type
    except AttributeError:
        print "You can only select between, Output_0 or Output_1'."
        sys.exit(1)
    except ValueError:
        print "Valid output_type values: 'test_vectors' and 'signal'"
        sys.exit(1)
    something_happened = True
#---------------------------------------------
if not something_happened:
    parser.print_help()
#dhost.disconnect()
