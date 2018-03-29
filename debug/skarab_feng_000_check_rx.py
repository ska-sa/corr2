#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check the SPEAD error counter and valid counter in the 
unpack section of the F-engines.

@author: paulp
"""
import sys
import IPython
import time
import argparse
import os
import logging

from casperfpga import utils as fpgautils, tengbe
from casperfpga import spead as casperspead, snap as caspersnap
from casperfpga import skarab_fpga
from corr2 import utils

logging.basicConfig(level=logging.INFO)

# import scipy.io as sio
# import numpy as np
# data = range(100)
# data = np.array(data, dtype=np.uint32)
# data.shape = (100, 1)
# simin_d0 = {'time': [], 'signals': {'dimensions': np.uint32(1), 'values': data}}
# sio.savemat('/tmp/mat.mat', {'simin_d0': simin_d0})
# sys.exit()

if os.environ['CORR2UUT'].strip() == '' or os.environ['CORR2UUT'].strip() == '':
    print('CORR2UUT or CORR2FUT environment variables not found.'
    sys.exit(0)

f = skarab_fpga.SkarabFpga(os.environ['CORR2UUT'])
f.get_system_information(os.environ['CORR2FUT'])

if f.gbes[0].get_port() != 30000:
    f.gbes[0].set_port(30000)


def read_gbe_snaps():
    f.registers.control.write(gbesnap_arm=0,
                              gbesnap_wesel=0, gbesnap_we=0,
                              gbesnap_trigsel=0, gbesnap_trig=0,)
    f.snapshots.rxsnap0_ss.arm()
    f.snapshots.rxsnap1_ss.arm()
    f.snapshots.rxsnap2_ss.arm()
    f.registers.control.write(gbesnap_arm=1,
                              gbesnap_wesel=0, gbesnap_we=0,
                              gbesnap_trigsel=0, gbesnap_trig=0, )
    time.sleep(1)
    d0 = f.snapshots.rxsnap0_ss.read(arm=False)['data']
    d1 = f.snapshots.rxsnap1_ss.read(arm=False)['data']
    d2 = f.snapshots.rxsnap2_ss.read(arm=False)['data']
    for ctr in range(len(d2['eof'])):
        if ((d2['eof'][ctr] == 0) and (d2['rawdv'][ctr] != 15)) or (
                    (d2['eof'][ctr] == 1) and (d2['rawdv'][ctr] != 1)):
            print('DV_ERROR(%i,%i,%i)' % (ctr, d2['rawdv'][ctr],
                                          d2['eof'][ctr]),
    return d0, d1, d2


def read_barrel_snaps(man_valid=False):
    f.registers.control.write(barrelsnap_arm=0, gbesnap_arm=0,
                              gbesnap_wesel=0, gbesnap_we=0,
                              gbesnap_trigsel=0, gbesnap_trig=0,)
    f.snapshots.barrelsnap0_ss.arm(man_valid=man_valid)
    f.snapshots.barrelsnap1_ss.arm(man_valid=man_valid)
    f.snapshots.barrelsnap2_ss.arm(man_valid=man_valid)
    f.registers.control.write(barrelsnap_arm=1, gbesnap_arm=0,
                              gbesnap_wesel=0, gbesnap_we=0,
                              gbesnap_trigsel=0, gbesnap_trig=0, )
    time.sleep(1)
    d0 = f.snapshots.barrelsnap0_ss.read(arm=False)['data']
    d1 = f.snapshots.barrelsnap1_ss.read(arm=False)['data']
    d2 = f.snapshots.barrelsnap2_ss.read(arm=False)['data']
    d0.update(d1)
    d0.update(d2)
    return d0


def read_spead_snaps():
    f.registers.control.write(barrelsnap_arm=0, gbesnap_arm=0,
                              gbesnap_wesel=0, gbesnap_we=0,
                              gbesnap_trigsel=0, gbesnap_trig=0,
                              speadsnap_arm=0,)
    f.snapshots.speadsnap0_ss.arm()
    f.snapshots.speadsnap1_ss.arm()
    f.snapshots.speadsnap2_ss.arm()
    f.registers.control.write(barrelsnap_arm=0, gbesnap_arm=0,
                              gbesnap_wesel=0, gbesnap_we=0,
                              gbesnap_trigsel=0, gbesnap_trig=0,
                              speadsnap_arm=1,)
    time.sleep(1)
    d0 = f.snapshots.speadsnap0_ss.read(arm=False)['data']
    d1 = f.snapshots.speadsnap1_ss.read(arm=False)['data']
    d2 = f.snapshots.speadsnap2_ss.read(arm=False)['data']
    d0.update(d1)
    d0.update(d2)
    return d0


def check_ramps(spead_packets):
    last_hdr_time = 0
    errors = False
    for ctr, packet in enumerate(spead_packets):
        print(ctr, packet.headers[0x1600], \
            packet.headers[0x1600] - last_hdr_time,
        last_hdr_time = packet.headers[0x1600]
        if packet.headers[0x1600] != packet.headers[0x1]:
            print('ID_ERROR',
            errors = True
        if packet.data != range(640):
            print('DATA_ERROR',
            errors = True
        print(''
    return errors

# read the data straight out of the 40gbe core
d0, d1, d2 = read_gbe_snaps()

ips = []
ports = []
destips = []
destports = []
for ctr in range(len(d2['port'])):
    if d2['port'][ctr] not in ports:
        ports.append(d2['port'][ctr])
    if d2['ip'][ctr] not in ips:
        ips.append(d2['ip'][ctr])
    if d2['destip'][ctr] not in destips:
        destips.append(d2['destip'][ctr])
    if d2['destport'][ctr] not in destports:
        destports.append(d2['destport'][ctr])

print('IPS:',
for ip in ips:
    print(str(tengbe.IpAddress(ip)),
print(''
print('PORTS:', ports
print('DEST_IPS:',
for ip in destips:
    print(str(tengbe.IpAddress(ip)),
print(''
print('DEST_PORTS:', destports

# interleave the four 64-bit words
d0.update(d1)
d0.update(d2)
d64 = []
eofs = []
for ctr in range(len(d0['d0'])):
    if d0['eof'][ctr] == 1:
        d64.append(d0['d3'][ctr])
        eofs.append(1)
    else:
        d64.append(d0['d3'][ctr])
        d64.append(d0['d2'][ctr])
        d64.append(d0['d1'][ctr])
        d64.append(d0['d0'][ctr])
        eofs.extend([0, 0, 0, 0])
d = {'data': d64, 'eof': eofs}
del d1, d2, d0

# break it up into packetses and process SPEAD data
gbe_packets = caspersnap.Snap.packetise_snapdata(d, 'eof')
spead_processor = casperspead.SpeadProcessor()
spead_processor.process_data(gbe_packets)

# check the packets for the ramp
if check_ramps(spead_processor.packets):
    IPython.embed()

# # save the output of the barrelsnaps to matlab .mat files
# rawdata = read_barrel_snaps(True)
# import scipy.io as sio
# import numpy as np
# d32 = {ctr: [] for ctr in range(8)}
# for ctr in range(len(rawdata['d0'])):
#     d32[0].append(rawdata['d3'][ctr] & (2 ** 32 - 1))
#     d32[1].append(rawdata['d3'][ctr] >> 32)
#     d32[2].append(rawdata['d2'][ctr] & (2 ** 32 - 1))
#     d32[3].append(rawdata['d2'][ctr] >> 32)
#     d32[4].append(rawdata['d1'][ctr] & (2 ** 32 - 1))
#     d32[5].append(rawdata['d1'][ctr] >> 32)
#     d32[6].append(rawdata['d0'][ctr] & (2 ** 32 - 1))
#     d32[7].append(rawdata['d0'][ctr] >> 32)
# for ctr in range(8):
#     d32[ctr] = ([0] * 100) + d32[ctr]
# rawdata['eof'] = ([0] * 100) + rawdata['eof']
# rawdata['we'] = ([0] * 100) + rawdata['we']
# datadict = {
#     'simin_d%i' % ctr: {
#         'time': [], 'signals': {
#             'dimensions': 1, 'values': np.array(d32[ctr], dtype=np.uint32)
#         }
#     } for ctr in range(8)
# }
# for ctr in range(8):
#     datadict['simin_d%i' % ctr]['signals']['values'].shape = \
#         (len(rawdata['d0']) + 100, 1)
# datadict['simin_dv'] = {
#     'time': [], 'signals': {
#         'dimensions': 1, 'values': np.array(rawdata['we'], dtype=np.uint32)
#     }
# }
# datadict['simin_dv']['signals']['values'].shape = (len(rawdata['d0']) + 100, 1)
# datadict['simin_eof'] = {
#     'time': [], 'signals': {
#         'dimensions': 1, 'values': np.array(rawdata['eof'], dtype=np.uint32)
#     }
# }
# datadict['simin_eof']['signals']['values'].shape = (len(rawdata['d0']) + 100, 1)
# sio.savemat('/tmp/mat.mat', datadict)
# sys.exit(0)

# now check the barrel snaps
rawdata = read_barrel_snaps()
d64 = []
eofs = []
for ctr in range(len(rawdata['d0'])):
    d64.append(rawdata['d3'][ctr])
    d64.append(rawdata['d2'][ctr])
    d64.append(rawdata['d1'][ctr])
    d64.append(rawdata['d0'][ctr])
    if rawdata['eof'][ctr] == 1:
        eofs.extend([0, 0, 0, 1])
    else:
        eofs.extend([0, 0, 0, 0])
d = {'data': d64, 'eof': eofs}

# break it up into packetses and process SPEAD data
try:
    gbe_packets = caspersnap.Snap.packetise_snapdata(d, 'eof')
    spead_processor = casperspead.SpeadProcessor()
    spead_processor.process_data(gbe_packets)
    if check_ramps(spead_processor.packets):
        IPython.embed()
except Exception as exc:
    print(exc.message
    IPython.embed()

# process the SPEAD data
rawdata = read_spead_snaps()
gbe_packets = caspersnap.Snap.packetise_snapdata(rawdata, 'eof')
lasttime = rawdata['timestamp'][0]
lastheapid = rawdata['heapid'][0]
if lastheapid != lasttime:
    print('HEAP_ID DOES NOT MATCH TIMESTAMP?!'
    IPython.embed()
spead_errors = 0
packet_jumps = []
for ctr, packet in enumerate(gbe_packets[1:]):
    errstr = ''
    d = [0] * 640
    d[0:640:4] = packet['d0']
    d[1:640:4] = packet['d1']
    d[2:640:4] = packet['d2']
    d[3:640:4] = packet['d3']
    if d != range(640):
        spead_errors += 1
        errstr += 'PACKET_DATA_ERROR '
    packettime = packet['timestamp'][0]
    packetheapid = packet['heapid'][0]
    if packettime != packetheapid:
        spead_errors += 1
        errstr += 'HEAP_ID!=TIMESTAMP '
    if len(packet['timestamp']) != 160:
        spead_errors += 1
        errstr += 'PACKET_LEN!=160(%i)' % len(packet['timestamp'])
    for pktctr in range(len(packet['timestamp'])):
        print(packet['timestamp'][pktctr], packet['heapid'][pktctr], \
            packet['polid'][pktctr], packet['dv'][pktctr], \
            packet['eof'][pktctr], \
            '%4i' % packet['d3'][pktctr], '%4i' % packet['d2'][pktctr], \
            '%4i' % packet['d1'][pktctr], '%4i' % packet['d0'][pktctr],
        if packet['timestamp'][pktctr] != packettime:
            spead_errors += 1
            print('TIME_ERROR',
        if packet['heapid'][pktctr] != packetheapid:
            spead_errors += 1
            print('HEAP_ERROR',
        if packet['eof'][pktctr] == 1:
            timediff = packettime - lasttime
            if timediff not in packet_jumps:
                packet_jumps.append(timediff)
            print('EOF(%i)' % timediff,
            lasttime = packettime
        print(''
    print(errstr
print('spead_errors:', spead_errors
print('spead packet jumps:', packet_jumps

IPython.embed()

# end
