#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import memory
from corr2 import utils
import casperfpga

TRIG_COMBO = 0
TRIG_NEWACC = 1
TRIG_PKTRDY = 2
TRIG_VALID = 3
TRIG_RBDONE = 4
TRIG_FETCH = 5
TRIG_MANUAL = 6

DV_COMBO = 0
DV_NEWACC = 1
DV_PKTRDY = 2
DV_VALID = 3
DV_RBDONE = 4
DV_FETCH = 5

MAN_VALID = False

f = casperfpga.KatcpFpga('roach02081a')
f.get_system_information()

# set the dv and trigger sources
f.registers.snapctrl.write(ctrdv_sel=1, dv_sel=DV_NEWACC, trigsel=TRIG_MANUAL)

# arm the snaps, select man_valid above
f.snapshots.vacc_snap0_ss.arm(man_valid=MAN_VALID)
f.snapshots.vacc_snap1_ss.arm(man_valid=MAN_VALID)

# reset the counter
f.registers.snapctrl.write(rst_ctr='pulse')

#f.registers.snapctrl.write(trig_vacc='pulse')

# switch to the selected trigger selection
f.registers.snapctrl.write(trigsel=TRIG_NEWACC)

# read the snaps
d = f.snapshots.vacc_snap0_ss.read(arm=False)['data']
d1 = f.snapshots.vacc_snap1_ss.read(arm=False)['data']
d.update(d1)

# print(the info

last_ctr = 0

diffs = {}

for ctr in range(len(d[d.keys()[0]])):
    print(ctr,
    for k in d.keys():
        print('{}({})'.format(k, d[k][ctr]),
    if d['rdbone'][ctr] == 1:
        diff = d['ctr32'][ctr] - last_ctr
        if diff < 0:
            diff += 2**32
        if diff not in diffs:
            diffs[diff] = 0
        diffs[diff] += 1
        print('cdiff({})'.format(diff),
        last_ctr = d['ctr32'][ctr]
    print(''

print(diffs
