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

f = casperfpga.KatcpFpga('roach02081a')

PROGRAM = True

if PROGRAM:

    # f.upload_to_ram_and_program('/tmp/vacc_only_001_2016_Apr_13_1622.fpg')
    # f.upload_to_ram_and_program('/tmp/vacc_only_001_2016_Apr_14_1103.fpg')

    #f.upload_to_ram_and_program('/tmp/vacc_only_001_2016_Apr_14_1159.fpg')
    f.upload_to_ram_and_program('/home/paulp/tmp/vacc_only_001_2016_Apr_15_1633.fpg')

    # f.upload_to_ram_and_program('/tmp/test_qdr_vacc5_2016_Apr_13_1632.fpg')
    # f.upload_to_ram_and_program('/tmp/test_qdr_vacc5_2016_Apr_14_0931.fpg')
    # f.upload_to_ram_and_program('/tmp/test_qdr_vacc5_2016_Apr_14_0959.fpg')

    # f.upload_to_ram_and_program('/tmp/test_qdr_vacc5_2016_Apr_07_1408.fpg')
    # print(f.qdrs.qv_mk_qdr.qdr_cal()

    # f.upload_to_ram_and_program('/tmp/test_qdr_vacc5o_2016_Apr_14_0903.fpg')
    print(f.qdrs.sys0_vacc_qv_qdr.qdr_cal()

    f.registers.acc_len.write(reg=816)
else:
    f.get_system_information()

# reset all the TVGs
f.registers.vacctvg_control.write_int(0)

# write the constant to the data reg and enable the test data
f.registers.sys0_vacc_tvg0_write.write_int(1)
f.registers.vacctvg_control.write(data_sel=True)

# switch everything over to the constants
# f.registers.vacc_pretvg_ctrl.write(selsync=True,
#                                    seldata=True,
#                                    selvalid=True,
#                                    selflag=True,
#                                    selrben=True,
#                                    selrst=True,
#                                    # rst='pulse',
#                                    en_gating=False)
