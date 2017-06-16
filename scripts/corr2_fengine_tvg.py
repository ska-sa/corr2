#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author: paulp
"""
import argparse

from casperfpga import utils as fpgautils
from corr2 import utils


parser = argparse.ArgumentParser(
    description='Display information about a MeerKAT F-engine.',
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

# make the fpgas
fpgas = utils.feng_script_get_fpgas(args)

# pre corner turn
fpgautils.threaded_fpga_operation(
    fpgas, 10, lambda fpga_: fpga_.registers.control.write(tvg_ct=args.prect))

fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
# end
