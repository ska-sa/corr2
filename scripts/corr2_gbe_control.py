#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Control the 10gbe cores on the hosts in the instrument

@author: paulp
"""
import argparse
import os

from casperfpga import utils as fpgautils

from corr2 import fxcorrelator

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


parser = argparse.ArgumentParser(
    description='Control the 10Gbe interfaces on the hosts in the instrument.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store',
    default='', help='corr2 config file')
parser.add_argument(
    '--ipython', dest='ipython', action='store_true', default=False,
    help='start an ipython session after completion/error')
parser.add_argument(
    '--loglevel', dest='log_level', action='store',
    default='INFO',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']

# make the correlator object and send the metadata
c = fxcorrelator.FxCorrelator('corr', config_source=args.config)
c.standard_log_config()

hosts = c.fhosts[:]
hosts.extend(c.xhosts[:])

hosts = c.xhosts[:]

THREADED_FPGA_FUNC(hosts, 10, 'get_system_information')

THREADED_FPGA_FUNC(hosts, 10, 'gbe_tx_disable')

# for h in hosts:
#     print h.host, '-', h.tengbes
#
#     h.gbe_tx_disable()

if args.ipython:
    import IPython
    IPython.embed()

# end
