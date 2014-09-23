#!/usr/bin/env python
"""
Deprogram one or more ROACHs.

@author: paulp
"""
import argparse

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

#allhosts = roach020958,roach02091b,roach020914,roach020922,roach020921,roach020927,roach020919,roach020925,roach02091a,roach02091e,roach020923,roach020924

parser = argparse.ArgumentParser(description='Deprogram one or more CASPER devices',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument('--class', dest='hclass', action='store', default='',
                    help='start/stop a class: fengine or xengine')
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
    HOSTCLASS = katcp_fpga.KatcpFpga
else:
    HOSTCLASS = dcp_fpga.DcpFpga

# are we doing it by class?
if args.hclass != '':
    if args.hclass == 'fengine':
        hosts = utils.parse_hosts(args.hosts, section='fengine')
    elif args.hclass == 'xengine':
        hosts = utils.parse_hosts(args.hosts, section='xengine')
    else:
        raise RuntimeError('No such host class: %s' % args.hclass)
else:
    hosts = utils.parse_hosts(args.hosts)
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# create the devices and deprogram them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 'get_system_information')
fpgautils.threaded_fpga_function(fpgas, 'deprogram')
fpgautils.threaded_fpga_function(fpgas, 'disconnect')

# end