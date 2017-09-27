#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check the SPEAD error counter and valid counter in the 
unpack section of the F-engines.

@author: paulp
"""
import os
import logging
import time

from casperfpga import utils as fpgautils, tengbe
from casperfpga import spead as casperspead, snap as caspersnap
from casperfpga import skarab_fpga
from corr2 import utils

logging.basicConfig(level=logging.INFO)

program_skarab = True
setup_skarab = True

f = skarab_fpga.SkarabFpga(os.environ['SKARAB_DSIM'])

if program_skarab:
    res = f.upload_to_ram_and_program(os.environ['SKARAB_DSIM_FPG'], attempts=5)
    if not res:
        print('Could not program SKARAB.')
        import sys
        sys.exit(0)
    print('Done programming SKARAB.')
else:
    f.get_system_information(os.environ['SKARAB_DSIM_FPG'])

if setup_skarab:
    f.registers.receptor_id.write(pol0_id=0, pol1_id=1)

    # ramp 80 or ramp 64?
    f.registers.test_control.write(sel_ramp80=True, rst_ramp80='pulse')

    f.registers.control.write(mrst='pulse')
    f.registers.control.write(msync='pulse')
    if f.gbes[0].get_port() != 30000:
        f.gbes[0].set_port(30000)
    f.registers.gbe_porttx.write(reg=30000)
    ip = tengbe.IpAddress('10.99.1.1')
    ip = tengbe.IpAddress(os.environ['CORR2UUT'])
    for ctr in range(4):
        f.registers['gbe_iptx%i' % ctr].write(reg=ip.ip_int)
    f.registers.control.write(gbe_rst='pulse')
    f.registers.gbecontrol.write_int(15)
    print('Done setting up SKARAB.')

f.registers.speadsnap_control.write_int(0)
f.snapshots.spead_snap0_ss.arm()
f.snapshots.spead_detail_ss.arm()
f.registers.speadsnap_control.write_int(1)

time.sleep(1)

d0 = f.snapshots.spead_snap0_ss.read(arm=False)['data']
d1 = f.snapshots.spead_detail_ss.read(arm=False)['data']

d0.update(d1)

last_eof = -1
for ctr in range(len(d0['d64'])):
    prtstr = '%4i %i %i %i' % (
        ctr, d0['we'][ctr], d0['eof'][ctr], d0['d64'][ctr])
    if d0['eof'][ctr]:
        prtstr += 'EOF(%i)' % (ctr - last_eof)
        last_eof = ctr
    print(prtstr)


import IPython
IPython.embed()

# end
