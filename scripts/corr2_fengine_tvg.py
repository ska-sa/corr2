#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author: paulp
"""
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
import casperfpga.scroll as scroll
from corr2 import utils

parser = argparse.ArgumentParser(description='Display information about a MeerKAT f-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument('--prect', dest='prect', action='store_true', default=False,
                    help='turn on or off the pre corner turn TVG')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

polltime = args.polltime

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

if 'CORR2INI' in os.environ.keys() and args.hosts == '':
    args.hosts = os.environ['CORR2INI']
hosts = utils.parse_hosts(args.hosts, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 10, 'get_system_information')

# pre corner turn
if args.prect:
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(tvg_ct=True))
else:
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(tvg_ct=False))

fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
# end
