#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""
import logging
import argparse
import os

from casperfpga import utils as casper_utils
from corr2 import utils, xhost_fpga

logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser(
    description='Set up the TVG on a x-engine VACC.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file, will use $CORR2INI if none given')
args = parser.parse_args()

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']
if args.config != '':
    host_list = utils.parse_hosts(args.config, section='xengine')
else:
    host_list = []

fpgas = []
for host_ctr, host in enumerate(host_list):
    f = xhost_fpga.FpgaXHostVaccDebug(host, host_ctr)
    f.get_system_information()
    fpgas.append(f)

casper_utils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga: fpga.tvg_data_value(1))

print(casper_utils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga: fpga.tvg_control(data_sel=1, inj_vector=0))

# _pref = 'sys0_vacc_tvg0'
#
# regname = '%s_n_pulses' % _pref
# fpga.registers[regname].write_int(10240)
#
# regname = '%s_n_per_group' % _pref
# fpga.registers[regname].write_int(40)
#
# regname = '%s_group_period' % _pref
# fpga.registers[regname].write_int(80)

# reset the ctrs