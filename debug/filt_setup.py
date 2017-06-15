__author__ = 'paulp'

import argparse

from casperfpga import utils as fpgautils
from casperfpga import tengbe

parser = argparse.ArgumentParser(description='Set up the simple narrowband filters.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='the config file to use')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if args.comms == 'katcp':
        HOSTCLASS = CasperFpga
else:
        HOSTCLASS = dcp_fpga.DcpFpga

import logging
log_level = 'INFO'
try:
    logging.basicConfig(level=eval('logging.%s' % log_level))
except AttributeError:
    raise RuntimeError('No such log level: %s' % log_level)
LOGGER = logging.getLogger(__name__)

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

# read the config file
configd = fpgautils.parse_ini_file(args.config)
filter_cfg = configd['filter']

# program the filter boards
filter_fpgas = []
for _f in filter_cfg['hosts']:
    filter_fpgas.append(HOSTCLASS(_f))
fpgautils.program_fpgas(filter_fpgas, progfile=filter_cfg['bitstream'], timeout=15)
THREADED_FPGA_FUNC(filter_fpgas, timeout=10, target_function='get_system_information')

# set up the fpga comms
THREADED_FPGA_OP(filter_fpgas, timeout=10,
                 target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))
THREADED_FPGA_OP(filter_fpgas, timeout=10,
                 target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=False),))
THREADED_FPGA_OP(filter_fpgas, timeout=10,
                 target_function=(lambda fpga_:
                                  fpga_.registers.control.write(status_clr='pulse',
                                                                gbe_cnt_rst='pulse',
                                                                cnt_rst='pulse'),))

# where does the filter data go?
THREADED_FPGA_OP(filter_fpgas, timeout=5,
                 target_function=(lambda fpga_:
                                  fpga_.registers.gbe_iptx0.write_int(int(
                                      tengbe.IpAddress(int(filter_cfg['pol0_destination_ip'])))),))
THREADED_FPGA_OP(filter_fpgas, timeout=5,
                 target_function=(lambda fpga_:
                                  fpga_.registers.gbe_iptx1.write_int(int(
                                      tengbe.IpAddress(int(filter_cfg['pol1_destination_ip'])))),))
THREADED_FPGA_OP(filter_fpgas, timeout=5,
                 target_function=(lambda fpga_:
                                  fpga_.registers.gbe_porttx.write_int(int(
                                      filter_cfg['destination_port'])),))

# set up the cores
feng_ip_octets = [int(bit) for bit in filter_cfg['10gbe_start_ip'].split('.')]
feng_port = int(filter_cfg['10gbe_port'])
assert len(feng_ip_octets) == 4, 'That\'s an odd IP address.'
feng_ip_base = feng_ip_octets[3]
feng_ip_prefix = '%d.%d.%d.' % (feng_ip_octets[0], feng_ip_octets[1], feng_ip_octets[2])
macprefix = filter_cfg['10gbe_macprefix']
macbase = int(filter_cfg['10gbe_macbase'])
board_id = 0
for ctr, f in enumerate(filter_fpgas):
    for gbe in f.tengbes:
        this_mac = '%s%02x' % (macprefix, macbase)
        this_ip = '%s%d' % (feng_ip_prefix, feng_ip_base)
        gbe.setup(mac=this_mac, ipaddress=this_ip,
                  port=feng_port)
        LOGGER.info('filthost(%s) gbe(%s) MAC(%s) IP(%s) port(%i) board(%i)' %
                    (f.host, gbe.name, this_mac, this_ip, feng_port, board_id))
        macbase += 1
        feng_ip_base += 1
    board_id += 1

# start tap on the f-engines
for f in filter_fpgas:
    for gbe in f.tengbes:
        gbe.tap_start(True)

# release from reset
THREADED_FPGA_OP(filter_fpgas, timeout=10,
                 target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=False),))

LOGGER.info('Subscribing to filter datasources...')
for fhost in filter_fpgas:
    LOGGER.info('\t%s:' % fhost.host)

    gbe = fhost.tengbes.gbe0
    rxaddress = '239.2.0.10'
    LOGGER.info('\t\t%s subscribing to address %s' % (gbe.name, rxaddress))
    gbe.multicast_receive(rxaddress, 0)

    gbe = fhost.tengbes.gbe1
    rxaddress = '239.2.0.11'
    LOGGER.info('\t\t%s subscribing to address %s' % (gbe.name, rxaddress))
    gbe.multicast_receive(rxaddress, 0)

    gbe = fhost.tengbes.gbe2
    rxaddress = '239.2.0.12'
    LOGGER.info('\t\t%s subscribing to address %s' % (gbe.name, rxaddress))
    gbe.multicast_receive(rxaddress, 0)

    gbe = fhost.tengbes.gbe3
    rxaddress = '239.2.0.13'
    LOGGER.info('\t\t%s subscribing to address %s' % (gbe.name, rxaddress))
    gbe.multicast_receive(rxaddress, 0)

LOGGER.info('done.')

# enable output
THREADED_FPGA_OP(filter_fpgas, timeout=10,
                 target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=True),))
LOGGER.info('Output enabled on all boards.')
