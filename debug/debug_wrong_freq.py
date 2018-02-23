#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the contents of a TenGBE RX or TX snapblock.

@author: paulp
"""
import time
import argparse

from casperfpga import spead as casperspead
from casperfpga import snap as caspersnap
from casperfpga.casperfpga import CasperFpga

parser = argparse.ArgumentParser(description='Display the contents of an FPGA''s 10Gbe buffers.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hostname', type=str, action='store',
                    help='the hostname of the digitiser')
parser.add_argument('-l', '--listcores', dest='listcores', action='store_true',
                    default=False,
                    help='list cores on this device')
parser.add_argument('-c', '--core', dest='core', action='store',
                    default='gbe0', type=str,
                    help='the core to query')
parser.add_argument('-d', '--direction', dest='direction', action='store',
                    default='tx', type=str,
                    help='tx or rx stream')

parser.add_argument('-s', '--spead', dest='spead', action='store_true',
                    default=False,
                    help='try and decode spead in this 10Gbe stream')
parser.add_argument('--spead_check', dest='spead_check', action='store_true',
                    default=False, help='Check SPEAD packet format against '
                                        'supplied values.')
parser.add_argument('--spead_version', dest='spead_version', action='store',
                    default=4, type=int, help='SPEAD version to use')
parser.add_argument('--spead_flavour', dest='spead_flavour', action='store',
                    default='64,48', type=str, help='SPEAD flavour to use')
parser.add_argument('--spead_packetlen', dest='spead_packetlen', action='store',
                    default=640, type=int,
                    help='SPEAD packet length (data portion only) to expect')
parser.add_argument('--spead_numheaders', dest='spead_numheaders', action='store',
                    default=8, type=int, help='number of SPEAD headers to expect')

parser.add_argument('--hex', dest='hex', action='store_true',
                    default=False,
                    help='show numbers in hex')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

hostnames = ['roach020828','roach020815','roach02064a','roach02070f']
fpgas = []
for host in hostnames:
    fpgas.append(CasperFpga(host, 7147))
time.sleep(1)
packet_data = {}
ip_list = []
freq_list = []
for f in fpgas:
    f.test_connection()
    f.get_system_information()

while True:

    for fpga in fpgas:

        for core in ['gbe0', 'gbe1', 'gbe2', 'gbe3']:

            # read the snap block based on the direction chosen
            if args.direction == 'tx':
                key_order = ['led_tx', 'eof', 'valid', 'tx_full', 'tx_over', 'link_up', 'ip', 'data']
                data_key = 'data'
                ip_key = 'ip'
                eof_key = 'eof'
                coredata = fpga.tengbes[core].read_txsnap()
            else:
                key_order = ['led_up', 'led_rx', 'valid_in', 'eof_in', 'bad_frame', 'overrun', 'ip_in', 'data_in']
                data_key = 'data_in'
                ip_key = 'ip_in'
                eof_key = 'eof_in'
                coredata = fpga.tengbes[core].read_rxsnap()
            # fpga.disconnect()

            if args.spead:
                if args.spead_check:
                    spead_processor = casperspead.SpeadProcessor(args.spead_version,
                                                                 args.spead_flavour,
                                                                 args.spead_packetlen,
                                                                 args.spead_numheaders)
                    expected_packet_length = args.spead_packetlen + args.spead_numheaders + 1
                else:
                    spead_processor = casperspead.SpeadProcessor(None, None, None, None)
                    expected_packet_length = -1

                gbe_packets = caspersnap.Snap.packetise_snapdata(coredata, eof_key)
                gbe_data = []
                for pkt in gbe_packets:
                    if (expected_packet_length > -1) and \
                            (len(pkt[data_key]) != expected_packet_length):
                        raise RuntimeError('Gbe packet not correct length - '
                                           'should be {}. is {}'.format(expected_packet_length,
                                                                        len(pkt[data_key])))
                    gbe_data.append(pkt[data_key])
                spead_processor.process_data(gbe_data)
                spead_data = []
                for spead_pkt in spead_processor.packets:
                    spead_data.extend(spead_pkt.get_strings())
                coredata[data_key] = spead_data

            packet_counter = 0
            packet_zeros = 0

            from casperfpga.tengbe import IpAddress

            # loop throug the packets
            for ctr in range(0, len(coredata[data_key])):
                if coredata[eof_key][ctr-1]:
                    last_pkt_ip = str(IpAddress(coredata[ip_key][ctr-1]))
                    last_pkt_time = coredata[data_key][ctr-130]
                    last_pkt_freq = coredata[data_key][ctr-131]
                    last_pkt_freq = last_pkt_freq.split(': ')[1]
                    last_pkt_time = last_pkt_time.split(': ')[1]
                    if packet_zeros != 128:
                        if last_pkt_ip not in packet_data:
                            packet_data[last_pkt_ip] = {}

                        if last_pkt_freq not in packet_data[last_pkt_ip]:
                            packet_data[last_pkt_ip][last_pkt_freq] = []
                        packet_data[last_pkt_ip][last_pkt_freq].append(128 - packet_zeros)
                    else:
                        print('ip(%s) freq(%s) zeros(%i)' % (last_pkt_ip, last_pkt_freq, packet_zeros)
                    packet_zeros = 0
                    packet_counter = 0
                # print('%5d,%3d' % (ctr, packet_counter),
                for key in key_order:
                    if key == ip_key:
                        if key == 'ip':
                            display_key = 'dst_ip'
                        elif key == 'ip_in':
                            display_key = 'src_ip'
                        else:
                            raise RuntimeError('Unknown IP key?')
                        # print('%s(%s)' % (display_key, str(tengbe.IpAddress(coredata[key][ctr]))), '\t',
                    elif (key == data_key) and args.spead:
                        if coredata[data_key][ctr].count('header') <= 0:
                            if coredata[data_key][ctr] == '0':
                                packet_zeros += 1
                        # print('%s(%s)' % (key, coredata[data_key][ctr]), '\t',
                #     else:
                #         if args.hex:
                #             print('%s(0x%X)' % (key, coredata[key][ctr]), '\t',
                #         else:
                #             print('%s(%s)' % (key, coredata[key][ctr]), '\t',
                # print(''
                packet_counter += 1

    for ip in packet_data:
        print('%s:' % ip
        for freq in packet_data[ip]:
            print('\t%s: ' % freq, packet_data[ip][freq]
    print(''

# end
