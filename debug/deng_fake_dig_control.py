__author__ = 'paulp'

import argparse
import sys
import signal


parser = argparse.ArgumentParser(description='Control a TVG digitiser on a ROACH2.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store', default='', help='the host to use')
parser.add_argument('--reset_ctrs', dest='rst_ctrs', action='store_true', default=False,
                    help='reset counters on the fake dig')
parser.add_argument('--output_select', dest='output_select', action='store', default=0, type=int,
                    help='select the fake dig output: 0(tvg), 1(tvg), 2(grng)')
parser.add_argument('--loglevel', dest='log_level', action='store', default='INFO',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)
    LOGGER = logging.getLogger(__name__)

def exit_gracefully(signal, frame):
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

# make the fake dig
fpga = CasperFpga(args.host)
fpga.get_system_information()

# do stuff
if args.rst_ctrs:
    if LOGGER:
        LOGGER.info('Pulsing counter reset line')
    fpga.registers.control.write(clr_status='pulse')

current_dsel = fpga.registers.control.read()['data']['tvg_select0']
if args.output_select != current_dsel:
    fpga.registers.control.write(tvg_select0=args.output_select)
LOGGER.info('Output select set to %i' % args.output_select)

fpga.disconnect()
