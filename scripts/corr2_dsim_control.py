#!/usr/bin/env python

import argparse
import sys
import os

from corr2 import utils
from corr2.dsimhost_fpga import FpgaDsimHost

parser = argparse.ArgumentParser(
    description='Control the dsim-engine (fake digitiser.)',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--config', type=str, action='store', help=
                    'corr2 config file. (default: Use CORR2INI env var)')
parser.add_argument('--program', dest='program', action='store_true',
                    default=False, help='(re)program the fake digitiser')
parser.add_argument('--deprogram', dest='deprogram', action='store_true',
                    default=False, help='deprogram the fake digitiser')
parser.add_argument('--start', dest='start', action='store_true', default=False,
                    help='start the fake digitiser transmission')
parser.add_argument('--status', dest='status', action='store_true', default=False,
                    help='Checks the status of digitiser transmission')
parser.add_argument('--pulse', action='store_true', default=False, help=
                    'Send a pulse of fake packets. Does nothing if digitiser '
                    'is already transmitting, use --stop first. It will only '
                    'work once until the dsim-engine is reset, e.g using '
                    '--resync which can be used with --pulse (--resync will '
                    'be applied first).')
parser.add_argument('--pulse-packets', action='store', default=100, type=int,
                    help='Send out out this many data packets per polarisation'
                         ' if --pulse is specified (default: %(default)d.')
parser.add_argument('--resync', action='store_true', default=False,
                    help='Restart digitiser time and then sync')
parser.add_argument('--stop', dest='stop', action='store_true', default=False,
                    help='stop the fake digitiser transmission')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, '
                         'DEBUG, ERROR')
parser.add_argument('--ipython', action='store_true', default=False,
                    help='Launch an embedded ipython shell once all is said '
                         'and done')
parser.add_argument('--sine-source', action='append', default=[], nargs=3,
                    help='Choose which sine to source, sin_0 or sin_1. '
                         'Set Scale and Frequency')
parser.add_argument('--noise-source', action='append', default=[], nargs=2,
                    help='Choose which Noise to source, noise_0 or noise_1. '
                    'Set noise scale.')
parser.add_argument('--output-type', action='append', default=[], nargs=2,
                    help='Choose which Output to source from, Output_0 or '
                         'Output_1. Output types, choose from signal or '
                         'test_vectors.')
parser.add_argument('--output-scale', action='append', default=[], nargs=2,
                    help='Choose which Output to source from, Output 0 or '
                         'Output 1. Output Scale, choose between 0 - 1.')
parser.add_argument('--zeros-sine', action='store_true', default=False,
                    help='Sets all sine sources to 0 scale and 0 Frequency.')
parser.add_argument('--zeros-noise', action='store_true', default=False,
                    help='Sets all  noise sources to 0 scale.')
parser.add_argument('--pulsar-source', action='append', default=[], nargs=3,
                    help='Choose which pulsar source, pulsar_0 or pulsar_1. '
                    ' Set Scale and Frequency')
parser.add_argument('--repeat-sine', action='append', default=[], nargs=2,
                    help='Force a sin source to repeat exactly every N '
                         'samples. Setting N to 0 disables repeating. '
                         'Arguments: sin_name, N. E.g --repeat-sin sin_0 4096')
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
        raise RuntimeError('No config file speficied and environment var '
                           '"CORR2INI" not defined')

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

# TODO HACK
if 'cwg0_en' in dhost.registers.names():
    dhost.registers.cwg0_en.write(en=1)
    dhost.registers.cwg1_en.write(en=1)
# /HACK

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

if args.status:
    # start tx
    sys.stdout.flush()
    if dhost.check_tx_raw():
        print 'Digitiser tx raw data success.'
    else:
        print 'Digitiser tx raw data failed.'
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

if args.sine_source:
    for sine_name, xscale_s, yfreq_s in args.sine_source:
        xscale = float(xscale_s)
        yfreq = float(yfreq_s)
        try:
            sine_source = getattr(dhost.sine_sources, 'sin_{}'.format(
                sine_name))
        except AttributeError:
            print "You can only select between sine sources: {}".format([
                ss.name for ss in dhost.sine_sources])
            sys.exit(1)
        try:
            sine_source.set(scale=xscale, frequency=yfreq)
        except ValueError:
            print "\nError, verify your inputs for sin_%s" % sine_source.name
            print "Max Frequency should be {}MHz".format(
                sine_source.max_freq/1e6)
            print "Scale should be between 0 and 1"
            sys.exit(1)
        print ""
        print "sine source:", sine_source.name
        print "scale:", sine_source.scale
        print "frequency:", sine_source.frequency
    something_happened = True

if args.zeros_sine:
    """Set all sine sources to zeros"""
    sources_names = dhost.sine_sources.names()
    for source in sources_names:
        try:
            sine_source = getattr(dhost.sine_sources, '{}'.format(source))
            sine_source.set(0, 0)
            print "sine source {}, set to {}.".format(sine_source.name,
                                                      sine_source.scale)
        except:
            print "An error occured."
            sys.exit(1)
    something_happened = True

if args.noise_source:
    for noise_sources, noise_scale_s in args.noise_source:
        noise_scale = float(noise_scale_s)
        try:
            source_from = getattr(dhost.noise_sources, 'noise_{}'.format(
                noise_sources))
        except AttributeError:
            print "You can only select between:", dhost.noise_sources.names()
            sys.exit(1)
        try:
            source_from.set(scale=noise_scale)
        except ValueError:
            print "Valid scale input is between 0 - 1."
            sys.exit(1)
        print ""
        print "noise source:", source_from.name
        print "noise scale:", source_from.scale
    something_happened = True

if args.zeros_noise:
    """Set all sine sources to zeros"""
    sources_names = dhost.noise_sources.names()
    for source in sources_names:
        try:
            noise_source = getattr(dhost.noise_sources, '{}'.format(source))
            noise_source.set(0)
            print "noise source {}, set to {}.".format(noise_source.name,
                                                       noise_source.scale)
        except:
            print "An error occured."
            sys.exit(1)
    something_happened = True

if args.pulsar_source:
    for pulsar_source, xscale_s, yfreq_s in args.pulsar_source:
        xscale = float(xscale_s)
        yfreq = float(yfreq_s)
        try:
            pulsar_sources = getattr(dhost.pulsar_sources, 'pulsar_{}'.format(
                pulsar_source))
        except AttributeError:
            print "You can only select between pulsar sources: {}".format([
                ss.name for ss in dhost.pulsar_sources])
            sys.exit(1)
        try:
            pulsar_sources.set(scale=xscale, frequency=yfreq)
        except ValueError:
            print "\nError, verify your inputs for pulsar_{}".format(
                str(pulsar_sources.name))
            print "Max Frequency should be {}MHz".format(
                pulsar_sources.max_freq/1e6)
            print "Scale should be between 0 and 1"
            sys.exit(1)
        print ""
        print "pulsar source:", pulsar_sources.name
        print "scale:", pulsar_sources.scale
        print "frequency:", pulsar_sources.frequency
        # print 'Initialising data '
        # pulsar_sources.initialise_data()
        # print 'Add pulsar (this takes time)'
        # pulsar_sources.add_pulsar(duty_cycle=0.05)
        # print 'Write file'
        # pulsar_sources.write_file('test_2', path_name=path)
    something_happened = True

if args.output_type:
    for output_type, output_type_s in args.output_type:
        try:
            type_from = getattr(dhost.outputs, 'out_{}'.format(output_type))
        except AttributeError:
            print "You can only select between, Output_0 or Output_1."
            sys.exit(1)
        try:
            type_from.select_output(output_type_s)
        except ValueError:
            print "Valid output_type values: 'test_vectors' and 'signal'"
            sys.exit(1)
        print ""
        print "output selected:", type_from.name
        print "output type:", type_from.output_type
    something_happened = True
# ---------------------------------------------
if args.output_scale:
    for output_scale, output_scale_s in args.output_scale:
        scale_value = float(output_scale_s)
        try:
            scale_from = getattr(dhost.outputs, 'out_{}'.format(output_scale))
        except AttributeError:
            print "You can only select between, %s" % dhost.outputs.names()
            sys.exit(1)
        try:
            scale_from.scale_output(scale_value)
        except ValueError:
            print "Valid scale input is between 0 - 1."
            sys.exit(1)
        """Check if it can read what was written to it!"""
        print ""
        print "output selected:", scale_from.name
        print "output scale:", scale_from.scale_register.read()['data']['scale']
    something_happened = True

if args.repeat_sine:
    something_happened = True
    for sine_name, repeat in args.repeat_sine:
        try:
            sine = getattr(dhost.sine_sources, 'sin_{}'.format(sine_name))
        except AttributeError:
            print "You can only select between sine sources: {}".format([
                ss.name for ss in dhost.sine_sources])
            sys.exit(1)
        try:
            sine.set(repeatN=int(repeat))
        except NotImplementedError:
            print ("Source repeat not implemented for source '{sine_name}'."
                   .format(**locals()))
            sys.exit(1)

if args.ipython:
    # Embedding ipython for debugging
    import IPython
    IPython.embed()
    something_happened = True

if not something_happened:
    parser.print_help()
# dhost.disconnect()
