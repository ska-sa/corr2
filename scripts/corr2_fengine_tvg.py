#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author: paulp
"""
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from corr2 import utils

fpga_throps = fpgautils.threaded_fpga_operation
fpga_thrfunc = fpgautils.threaded_fpga_function

parser = argparse.ArgumentParser(
    description='Display information about a MeerKAT f-engine.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument(
    '--prect', dest='prect', action='store_true', default=False,
    help='turn on or off the pre corner turn TVG')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='',
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

if 'CORR2INI' in os.environ.keys() and args.hosts == '':
    args.hosts = os.environ['CORR2INI']
hosts = utils.parse_hosts(args.hosts, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(katcp_fpga.KatcpFpga, hosts)
fpga_thrfunc(fpgas, 10, 'get_system_information')

# pre corner turn
fpga_throps(fpgas, 10,
            lambda fpga_: fpga_.registers.control.write(tvg_ct=args.prect))

fpga_thrfunc(fpgas, 10, 'disconnect')
# end
