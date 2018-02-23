#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""
import logging
import argparse
import os

from casperfpga import utils as casper_utils
from corr2 import utils, xhost_fpga
import IPython
import sys

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

snap = 'snap_vacc_in'

f = xhost_fpga.FpgaXHostVaccDebug(host_list[0], 0)
f.get_system_information()

NUM_ACCS = 1633
VEC_LEN = 64 * 40  # 2560
NUM_ADDS = VEC_LEN / 2
BANK0_START = 0
BANK1_START = 2048

# f.registers.snap_trig_val.write_int(NUM_ACCS)
# f.registers.snap_ignore_val.write_int(1)

MAN_VALID = True

# set up the write enable and trigger
f.registers.snap_control.write(
    we_sel=False,
    small_val=1632,

    es_rd_en_out=True,
    es_wr_en_out=True,
    es_wr_en_two_cycles=False,
    es_snapstop=False,
    es_rst=False,
    es_halfsel=False,
    es_rb_rd_en=False,
    es_rd_wr_sel=False,
    es_blank=False,
    es_rb_en=False,
    es_rb_done=False,
)


def analyse_data():
    """
    Look for a mistake in the snap data
    :return:
    """
    d = f.snapshots.snap_vacc_in_ss.read(man_valid=MAN_VALID,
                                         man_trig=True,
                                         circular_capture=True)['data']
    keys = d.keys()
    bank = d['addr_out'][0] >= BANK1_START
    datalen = len(d['addr_out'])
    error = False

    def show_reads():
        wrong_locs = []
        wr_d_max = -1
        last_rd = -1
        for ctr in range(0, datalen, 1):
            d12 = d['d12_out'][ctr]
            if d['wr_out'][ctr] == 1:
                if d12 > wr_d_max:
                    wr_d_max = d12
                if d12 < wr_d_max:
                    wrong_locs.append(ctr)
            rd_out = d['rd_out'][ctr]
            if rd_out == 0:
                continue
            print('{}: '.format(ctr),
            for k in keys:
                print('{}[{}] '.format(k, d[k][ctr]),
            if last_rd > -1:
                if d['addr_out'][ctr] - last_rd != 1:
                    print('READ_JUMP',
            print(''
            if rd_out == 1:
                last_rd = d['addr_out'][ctr]
        print(wrong_locs
        raise RuntimeError

    def show_writes():
        wrong_locs = []
        wr_d_max = -1
        last_rd = -1
        for ctr in range(0, datalen, 1):
            d12 = d['d12_out'][ctr]
            if d['wr_out'][ctr] == 1:
                if d12 > wr_d_max:
                    wr_d_max = d12
                if d12 < wr_d_max:
                    wrong_locs.append(ctr)
            wr_out = d['wr_out'][ctr]
            if wr_out == 0:
                continue
            print('{}: '.format(ctr),
            for k in keys:
                print('{}[{}] '.format(k, d[k][ctr]),
            if last_rd > -1:
                if d['addr_out'][ctr] - last_rd != 1:
                    print('WRITE_JUMP',
            print(''
            if wr_out == 1:
                last_rd = d['addr_out'][ctr]
        print(wrong_locs
        raise RuntimeError

    def old_style():
        keys = d.keys()

        def print_keys():
            pstr = 'ctr\t'
            for k in keys:
                pstr += '%s\t' % k
            print(pstr

        print_keys()

        wrong_locs = []
        wr_d_max = -1
        for ctr in range(datalen):
            d12 = d['d12_out'][ctr]
            if d['wr_out'][ctr] == 1:
                if d12 > wr_d_max:
                    wr_d_max = d12
                if d12 < wr_d_max:
                    wrong_locs.append(ctr)
            print(ctr, '\t',
            for k in keys:
                print(d[k][ctr], '\t',
            print(''
            # if ctr % 20 == 0:
            #     print_keys()
        print(wrong_locs
        raise RuntimeError

    def my_style():
        keys = d.keys()

        def print_keys():
            pstr = 'ctr\t'
            for k in keys:
                pstr += '%s\t' % k
            print(pstr

        print_keys()

        wrong_locs = []
        wr_d_max = -1
        for ctr in range(datalen):
            d12 = d['d12_out'][ctr]
            if d['wr_out'][ctr] == 1:
                if d12 > wr_d_max:
                    wr_d_max = d12
                if d12 < wr_d_max:
                    wrong_locs.append(ctr)

            print(ctr, '\t',
            for k in keys:

                if k != 'half_sel' and k != 'blank':
                    print('%s[%i]\t' % (k, d[k][ctr]),
            print(''
            # if ctr % 20 == 0:
            #     print_keys()
        print(wrong_locs
        raise RuntimeError

    my_style()


loopctr = 0
while True:
    try:
        analyse_data()
    except RuntimeError:
        print('ran %i times before error' % loopctr
        raise
    print('.',
    sys.stdout.flush()
    loopctr += 1
