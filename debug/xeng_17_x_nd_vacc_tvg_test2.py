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

vals = [10, 20, 30, 40]

# and enable it and route the valid line
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(valid_sel=True, pulse_en=False), )

# and enable it and route the valid line
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(sync_sel=True),)

# and enable it and route the valid line
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(reset='pulse'), )

# set up the valid pulse generator
for ctr in range(4):
    _pref = 'sys%i_vacc_tvg0' % ctr

    regname = '%s_n_pulses' % _pref
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers[regname].write_int(777777), )

    regname = '%s_n_per_group' % _pref
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers[regname].write_int(64), )

    regname = '%s_group_period' % _pref
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers[regname].write_int(1024), )

#     _regname = '%s_ins_vect_loc' % _pref
#     fpgautils.threaded_fpga_operation(
#         fpgas, 10,
#         lambda fpga_: fpga_.registers[_regname].write_int(100), )
#
#     _regname = '%s_ins_vect_val' % _pref
#     fpgautils.threaded_fpga_operation(
#         fpgas, 10,
#         lambda fpga_: fpga_.registers[_regname].write_int(vals[ctr]), )
#
# fpgautils.threaded_fpga_operation(
#     fpgas, 10,
#     lambda fpga_: fpga_.registers.vacctvg_control.write(vector_en=True), )

# and enable it and route the valid line
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(valid_sel=True, pulse_en=True), )

