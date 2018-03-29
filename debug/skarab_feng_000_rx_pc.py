#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check the SPEAD error counter and valid counter in the 
unpack section of the F-engines.

@author: paulp
"""
import logging
import socket
import struct

from casperfpga import spead as casperspead

logging.basicConfig(level=logging.INFO)

# open a RX socket and bind to the port
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(1)
sock.bind(('', 30000))
# receive a bunch of packets and save them in a list
pkts = []
try:
    for ctr in range(100):
        pkts.append(sock.recvfrom(10000))
except socket.timeout:
    raise RuntimeError('ERROR: socket timed out waiting for '
                       'packets from TX FPGA.')
finally:
    sock.close()

for ctr, pkt in enumerate(pkts):
    print(ctr, len(pkt[0]))

pkt_len = len(pkts[0][0])

# format the packets into gbe_packets
gbe_packets = []
for pkt in pkts:
    pkt64_wrong = struct.unpack('>%iQ' % (pkt_len/8), pkt[0])
    pkt64 = []
    for ctr in range(0, len(pkt64_wrong), 4):
        tmp = [pkt64_wrong[ctr+3], pkt64_wrong[ctr+2],
               pkt64_wrong[ctr+1], pkt64_wrong[ctr+0]]
        pkt64.extend(tmp)
    gbe_packets.append(pkt64)

# process SPEAD
spead_processor = casperspead.SpeadProcessor()
spead_processor.process_data(gbe_packets)

# sort the packets
sorted_packets = [spead_processor.packets[0]]
for ctr, packet in enumerate(spead_processor.packets[1:]):
    for ctr2, sp in enumerate(sorted_packets):
        if packet.headers[0x1600] <= sp.headers[0x1600]:
            break
    sorted_packets = sorted_packets[0:ctr2] + [packet] + sorted_packets[ctr2:]

# check the packets for the ramp
last_hdr_time = 0
for ctr, packet in enumerate(sorted_packets):
    prtstr = '%5i' % ctr
    prtstr += ' %16i' % packet.headers[0x1600]
    prtstr += ' %10i' % (packet.headers[0x1600] - last_hdr_time)
    prtstr += ' pol%1i' % packet.headers[0x3101]
    last_hdr_time = packet.headers[0x1600]
    if packet.headers[0x1600] != packet.headers[0x1]:
        prtstr += ' ID_ERROR'
    if packet.data != range(640):
        prtstr += ' DATA_ERROR'
    print(prtstr)
    import IPython
    IPython.embed()

import IPython
IPython.embed()

# end
