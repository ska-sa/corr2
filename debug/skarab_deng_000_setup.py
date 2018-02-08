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

from casperfpga import casperfpga, network

logging.basicConfig(level=logging.INFO)

program_skarab = True
setup_skarab = True

f = casperfpga.CasperFpga(os.environ['SKARAB_DSIM'])

if program_skarab:
    res = f.upload_to_ram_and_program(os.environ['SKARAB_DSIM_FPG'])
    if not res:
        print('Could not program SKARAB.')
        import sys
        sys.exit(0)
    print('Done programming SKARAB.')
else:
    f.get_system_information(os.environ['SKARAB_DSIM_FPG'])

if setup_skarab:

    f.registers.gbe_control.write_int(0)
    f.registers.receptor_id.write(pol0_id=0, pol1_id=1)

    f.registers.control.write(tvg_select0=1, tvg_select1=1)

    # ramp 80 or ramp 64?
    f.registers.ramp_control.write(sel_ramp80=0, rst_ramp80='pulse',
                                   sel_munge=0, sel_insert_time=0)

    f.registers.pol_tx_always_on.write(pol0_tx_always_on=1, pol1_tx_always_on=1)
    f.registers.src_sel_cntrl.write(src_sel_0=1, src_sel_1=1)

    f.registers.control.write(mrst='pulse')
    f.registers.control.write(msync='pulse')
    f.registers.control.write(gbe_rst=0, gbe_txen=1)

    gbe = f.gbes.keys()[0]
    gbe = f.gbes[gbe]
    # if gbe.get_port() != 30000:
    #     gbe.set_port(30000)
    # f.registers.gbe_porttx.write(reg=30000)
    # ip = network.IpAddress('10.99.1.1')
    # ip = network.IpAddress(os.environ['CORR2UUT'])
    # ip = network.IpAddress('10.100.101.111')
    # for ctr in range(4):
    #     f.registers['gbe_iptx%i' % ctr].write(reg=ip.ip_int)

    if gbe.get_port() != 7148:
        gbe.set_port(7148)
    f.registers.gbe_porttx.write(reg=7148)
    f.registers['gbe_iptx0'].write(reg=int(network.IpAddress('239.2.0.64')))
    f.registers['gbe_iptx1'].write(reg=int(network.IpAddress('239.2.0.65')))
    f.registers['gbe_iptx2'].write(reg=int(network.IpAddress('239.2.0.66')))
    f.registers['gbe_iptx3'].write(reg=int(network.IpAddress('239.2.0.67')))

    # f.registers.control.write(gbe_rst='pulse')
    f.registers.gbe_control.write_int(15)
    # f.registers.gbe_control.write_int(1)
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
pktlen_errors = 0
for ctr in range(len(d0['d64'])):
    prtstr = '%6i %20i %20i %20x' % (
        ctr, d0['we'][ctr], d0['eof'][ctr], d0['d64'][ctr])
    if d0['eof'][ctr]:
        pktlen = (ctr - last_eof)
        prtstr += ' EOF(%i)' % pktlen
        if pktlen != 649:
            prtstr += ' ERROR'
            pktlen_errors += 1
        last_eof = ctr
    print(prtstr)
    if d0['eof'][ctr]:
        print('-' * 100)

print 'PKTLEN_ERRORS:', pktlen_errors

# import IPython
# IPython.embed()

# end
