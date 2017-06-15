# -*- coding: utf-8 -*-
"""
Created on Mon Apr 14 17:06:22 2014

@author: paulp
"""

from corr2.katcp_client_fpga import KatcpClientFpga
from corr2.fpgadevice import tengbe
import corr2.misc as misc

import time

hostname = 'roach02091b'

fpga = KatcpClientFpga(hostname)
fpga.get_system_information()

packet_length = 128 + 5 + 4

read_counter = 0
while True:
    coredata = fpga.tengbes.gbe0.read_txsnap()
    errors = {}
    errors['valid'] = 0
    errors['packet_length'] = 0
    errors['data_step'] = 0
    num_packets = 0
    packet_counter = 0
    packet_lengths = []
    for ctr in range(0, len(coredata[coredata.keys()[0]])):
        data = coredata['data'][ctr]
        eof = coredata['eof'][ctr]
        valid = coredata['valid'][ctr]
        if not valid:
            errors['valid']  += 1
        packet_counter += 1
        if eof:
            if packet_counter != packet_length:
                print(time.time(), 'AIIIIIIIIIIIEEEEEEEE - packet length should be %d, is actually %d - now %d errors' % (packet_length, packet_counter, errors['packet_length'])
                errors['packet_length'] += 1
            else:
                if packet_counter not in packet_lengths:
                    packet_lengths.append(packet_counter)
            packet_counter = 0
            num_packets += 1
    if read_counter % 10 == 0:
        print(read_counter,
    read_counter += 1

#    if (errors['valid'] > 0) or (errors['packet_length'] > 1):
#        packet_counter = 0
#        for ctr in range(0, len(coredata[coredata.keys()[0]])):
#            data = coredata['data'][ctr]
#            eof = coredata['eof'][ctr]
#            valid = coredata['valid'][ctr]
#            print('%3d: vld(%1d) eof(%1d)' % (packet_counter, valid, eof)
#            packet_counter += 1
#            if eof:
#                packet_counter = 0
#        print(errors
#        break
#    read_counter += 1
#    print(read_counter, num_packets, packet_lengths
