#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Start the filter boards.

@author: paulp
"""
import argparse
import os

from casperfpga import utils as fpgautils
from corr2 import utils, filthost_fpga

parser = argparse.ArgumentParser(description='Set up the filter boards, check RX and start TX.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='a corr2 config file')
parser.add_argument('--loglevel', dest='log_level', action='store', default='INFO',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

import logging
if args.log_level != '':
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)
LOGGER = logging.getLogger(__name__)

# parse the config file
cfgsrc = utils.parse_ini_file(args.config)

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']
hosts = utils.parse_hosts(args.config, section='filter')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without filter hosts.')

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

# make the FPGA objects
fpgas = []
for ctr, h in enumerate(hosts):
    _fpga = filthost_fpga.FpgaFilterHost(ctr, cfgsrc)
    fpgas.append(_fpga)

# program the boards
THREADED_FPGA_FUNC(fpgas, timeout=10, target_function=('upload_to_ram_and_program', (fpgas[0].boffile,),))

# initialise them
THREADED_FPGA_FUNC(fpgas, timeout=10, target_function=('initialise', (),))

# end
