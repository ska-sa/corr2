#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""
import sys
import signal
import time
import argparse
import os
import logging

from casperfpga import utils as fpgautils
import casperfpga.scroll as scroll
from corr2 import utils
from corr2 import xhost_fpga
from corr2 import fxcorrelator

logging.basicConfig(level=logging.INFO)

c = fxcorrelator.FxCorrelator('vacctest', config_source='/home/paulp/code/corr2.ska.github/debug/fxcorr_labrts.ini')

c.initialise(program=False)

# vacc sel is 6-bits wide
# vacc_status = c.xhosts[0].registers.tvg_control.read()['data']['vacc']


def decode_vacc_ctrl(vacc_ctrl):
    return {
        'rst':          (vacc_ctrl >> 5) & 0x01,
        'inj_ctr':      (vacc_ctrl >> 4) & 0x01,
        'inj_vector':   (vacc_ctrl >> 3) & 0x01,
        'valid_sel':    (vacc_ctrl >> 2) & 0x01,
        'data_sel':     (vacc_ctrl >> 1) & 0x01,
        'enable':       (vacc_ctrl >> 0) & 0x01,
    }


def reset(fpga, highlow):
    old_val = fpga.registers.tvg_control.read()['data']['vacc']
    if highlow == 0:
        old_val &= int('011111', 2)
    else:
        old_val |= (0x01 << 5)
    fpga.registers.tvg_control.write(vacc=old_val)


def enable_pulses(fpga, enable):
    old_val = fpga.registers.tvg_control.read()['data']['vacc']
    if enable == 0:
        old_val &= int('111110', 2)
    else:
        old_val |= (0x01 << 0)
    fpga.registers.tvg_control.write(vacc=old_val)


def enable_counter(fpga):
    old_val = fpga.registers.tvg_control.read()['data']['vacc']
    old_val |= (0x01 << 4)
    fpga.registers.tvg_control.write(vacc=old_val)


def disable_counter(fpga):
    old_val = fpga.registers.tvg_control.read()['data']['vacc']
    old_val &= int('101111', 2)
    fpga.registers.tvg_control.write(vacc=old_val)


def enable_vector(fpga):
    old_val = fpga.registers.tvg_control.read()['data']['vacc']
    old_val |= (0x01 << 3)
    fpga.registers.tvg_control.write(vacc=old_val)


def disable_vector(fpga):
    old_val = fpga.registers.tvg_control.read()['data']['vacc']
    old_val &= int('110111', 2)
    fpga.registers.tvg_control.write(vacc=old_val)


def valid_select(fpga, valid_sel):
    old_val = fpga.registers.tvg_control.read()['data']['vacc']
    if valid_sel == 0:
        old_val &= int('111011', 2)
    else:
        old_val |= (0x01 << 2)
    fpga.registers.tvg_control.write(vacc=old_val)

N_PULSES = (128 * 40)-1

N_PULSES = (2**32)-1

N_PER_GROUP = 40
GROUP_PERIOD = 100

# fpgautils.threaded_fpga_operation(c.xhosts, 10, lambda fpga_: fpga_.registers.acc_len.write_int(1))

for ctr in range(0, 4):
    fpgautils.threaded_fpga_operation(c.xhosts, 10, lambda fpga_: fpga_.registers['sys%i_vacc_tvg0_n_pulses' % ctr].write_int(N_PULSES))
    fpgautils.threaded_fpga_operation(c.xhosts, 10, lambda fpga_: fpga_.registers['sys%i_vacc_tvg0_n_per_group' % ctr].write_int(N_PER_GROUP))
    fpgautils.threaded_fpga_operation(c.xhosts, 10, lambda fpga_: fpga_.registers['sys%i_vacc_tvg0_group_period' % ctr].write_int(GROUP_PERIOD))

fpgautils.threaded_fpga_operation(c.xhosts, 10, valid_select, 0)
fpgautils.threaded_fpga_operation(c.xhosts, 10, enable_pulses, 0)
fpgautils.threaded_fpga_operation(c.xhosts, 10, reset, 0)
fpgautils.threaded_fpga_operation(c.xhosts, 10, reset, 1)
fpgautils.threaded_fpga_operation(c.xhosts, 10, reset, 0)
fpgautils.threaded_fpga_operation(c.xhosts, 10, enable_counter)

print fpgautils.threaded_fpga_operation(c.xhosts, 10,
                                        lambda fpga_:
                                        decode_vacc_ctrl(fpga_.registers.tvg_control.read()['data']['vacc']))

# fpgautils.threaded_fpga_operation(c.xhosts, 10, enable_pulses, 1)

# print ''
# print fpgautils.threaded_fpga_operation(c.xhosts, 10,
#                                         lambda fpga_:
#                                         decode_vacc_ctrl(fpga_.registers.tvg_control.read()['data']['vacc']))
#
# fpgautils.threaded_fpga_operation(c.xhosts, 10, valid_select, 0)
# fpgautils.threaded_fpga_operation(c.xhosts, 10, disable_counter)