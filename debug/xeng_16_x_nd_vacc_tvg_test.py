#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import memory
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Set up the x-engine VACCs.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store',
                    default='', help='comma-delimited list of x-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
parser.add_argument('--comms', dest='comms', action='store', default='katcp',
                    type=str, help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, '
                         'DEBUG, ERROR')
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
hosts = utils.parse_hosts(args.hosts, section='xengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# create the devices and connect to them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')

print(fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.read()['data'], )

# write nothing to the tvg control reg
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write_int(0), )

# reset all the TVGs
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(ctr_en=False, sync_sel=False,
                                              valid_sel=False, data_sel=False,
                                              reset='pulse'), )

# write the constant to the data reg
# CLUDGE
# for ctr in range(1):
for ctr in range(4):
    regname = 'sys%i_vacc_tvg0_write' % ctr
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers[regname].write_int(1), )

# and enable the constant instead of the real data
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(data_sel=True), )

# fpgautils.threaded_fpga_operation(
#     fpgas, 10,
#     lambda fpga_:
#         fpga_.registers.vacc_pretvg_ctrl.write(en_gating=False), )
