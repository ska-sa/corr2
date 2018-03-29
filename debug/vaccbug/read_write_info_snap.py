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

f.registers.snap_trig_val.write_int(NUM_ACCS - 1)

MAN_VALID = False


def analyse_data():
    """
    Look for a mistake in the snap data
    :return:
    """
    d = f.snapshots.snap_vacc_in_ss.read(man_valid=MAN_VALID)['data']
    keys = d.keys()
    bank = d['addr'][0] >= BANK1_START
    datalen = len(d['addr'])
    error = False

    startpos = -1
    for ctr in range(0, datalen, 1):
        if d['d32'][ctr] == 1633:
            startpos = ctr
            break
    if startpos == -1:
        raise RuntimeError('No start pos found')
    endpos = startpos
    for ctr in range(startpos, datalen, 1):
        if d['d32'][ctr] != 1633:
            endpos = ctr
            break
    if startpos == endpos:
        raise RuntimeError('No end pos found')

    if endpos - startpos != VEC_LEN:
        for ctr in range(startpos - 10, startpos + VEC_LEN + 10, 1):
        # for ctr in range(0, datalen, 1):
            print('{}: '.format(ctr),
            for k in keys:
                print('{}[{}] '.format(k, d[k][ctr]),
            print(''
        print(startpos, endpos
        raise RuntimeError
    return

    for ctr in range(0, datalen, 2):
        addr0 = d['addr'][ctr]
        data0 = d['d32'][ctr]
        addr1 = d['addr'][ctr+1]
        data1 = d['d32'][ctr+1]
        if data0 != data1:
            print('%i: DATA ERROR: addr0[%i] addr1[%i] data0[%i] data1[%i]' % (
                ctr, addr0, addr1, data0, data1)
            error = True
        if addr1 != addr1:
            print('%i: ADDR ERROR: addr0[%i] addr1[%i] data0[%i] data1[%i]' % (
                ctr, addr0, addr1, data0, data1)
            error = True

        # print('{}: we[{}] addr0[{}] addr1[{}] data0[{}] data1[{}]'.format(
        #     ctr, d['wren'][ctr], addr0, addr1, data0, data1
        # )

    if error:
        IPython.embed()
        raise RuntimeError

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
