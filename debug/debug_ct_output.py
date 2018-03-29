#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Check the output of the corner turner - debugging the

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

parser.add_argument('--set_eqs', dest='set_eqs', action='store_true',
                    default=False, help='')

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

if args.set_eqs:
    print('Writing EQs'
    import os
    import corr2
    import logging
    c = corr2.fxcorrelator.FxCorrelator('rts correlator',
                                        config_source=os.environ['CORR2INI'],
                                        log_level=logging.INFO)
    c.initialise(program=False)
    eqs = [0] * 4096
    eqs[0] = 300
    corr2.fxcorrelator_fengops.feng_eq_set(c, write=True, source_name='ant0_x', new_eq=eqs)
    for src_name in ['ant0_y',
                     'ant1_x', 'ant1_y',
                     'ant2_x', 'ant2_y',
                     'ant3_x', 'ant3_y']:
        corr2.fxcorrelator_fengops.feng_eq_set(c, write=True, source_name=src_name, new_eq=0)

hostnames = ['roach020828', 'roach020815', 'roach02064a', 'roach02070f']
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

from casperfpga.memory import bin2fp
import numpy

f = fpgas[0]

num_freqs = 4096
snap_len = 2048
words_per_snap_word = 2
pols_per_snap_word = 2
packet_len = 256
num_snaps = 4

words_per_snap = snap_len * words_per_snap_word
freqs_per_snap = words_per_snap / packet_len
loops_required = num_freqs / (freqs_per_snap * num_snaps)


def read_snaps(byte_offset):
    # print('reading from offset %i' % byte_offset
    for ctr in range(0, num_snaps):
        f.snapshots['snap_ct%i_ss' % ctr].arm(offset=byte_offset)
    f.registers.ctsnap_ctrl.write_int(1)
    f.registers.ctsnap_ctrl.write_int(0)
    snapd = []
    time.sleep(1)
    for ctr in range(0, num_snaps):
        thissnapd = f.snapshots['snap_ct%i_ss' % ctr].read(arm=False,
                                                           offset=byte_offset)['data']['data']
        snapd.append(thissnapd)
    # print('Snap blocks are %i long.' % len(snapd[0])
    assert len(snapd[0]) == snap_len
    return snapd


def unpack_snapd(snaplist):
    # unpack the snapdata into signed 8.7 words per frequency
    # we get in four parallel frequencies
    _dp0 = [[], [], [], []]
    _dp1 = [[], [], [], []]
    for sctr in range(0, num_snaps):
        for dword in snaplist[sctr]:
            four_words = []
            for fwctr in range(3, -1, -1):
                raw_word = (dword >> (fwctr * 16)) & 0xffff
                raw_real = (raw_word >> 8) & 0xff
                raw_imag = raw_word & 0xff
                real = bin2fp(raw_real, 8, 7, True)
                imag = bin2fp(raw_imag, 8, 7, True)
                cplx = complex(real, imag)
                four_words.append(cplx)
            _dp0[sctr].append(four_words[0])
            _dp1[sctr].append(four_words[1])
            _dp0[sctr].append(four_words[2])
            _dp1[sctr].append(four_words[3])
    return _dp0, _dp1


def pack_freqs(p0d, p1d):
    p0_list = []
    p1_list = []
    for pkt_offset in range(0, len(p0d[0]), 256):
        for snapctr in range(0, num_snaps):
            p0data = p0d[snapctr][pkt_offset:pkt_offset+256]
            p1data = p1d[snapctr][pkt_offset:pkt_offset+256]
            p0_list.append(p0data)
            p1_list.append(p1data)
    return p0_list, p1_list


try:

    while True:

        fsums0 = []
        fsums1 = []
        p0_data = []
        p1_data = []
        offset_ctr = 0

        for offset_ctr in range(0, loops_required):
            byte_offset = offset_ctr * (2048*8)
            snapd = read_snaps(byte_offset)
            dp0, dp1 = unpack_snapd(snapd)
            per_freq0, per_freq1 = pack_freqs(dp0, dp1)
            p0_data.extend(per_freq0)
            p1_data.extend(per_freq1)

            # for packet_offset in range(0, len(dp0[0]), 256):
            #     for ctr in range(0, 4):
            #         p0dat = dp0[ctr][packet_offset:packet_offset+256]
            #         p1dat = dp1[ctr][packet_offset:packet_offset+256]
            #         p0_data.extend(p0dat)
            #         p1_data.extend(p1dat)
            #         fsums0.append(sum(numpy.abs(p0dat)))
            #         fsums1.append(sum(numpy.abs(p1dat)))
            # print('p0 data is', len(p0_data), ' points long.'

            print('Offset step %i/%i done' % (offset_ctr, loops_required)

        break

        non_zero0 = []
        non_zero1 = []
        for ctr, data in enumerate(fsums0):
            if data != 0:
                if ctr not in non_zero0:
                    non_zero0.append(ctr)
            if fsums1[ctr] != 0:
                if ctr not in non_zero1:
                    non_zero1.append(ctr)

        print('nonzeros0', non_zero0
        print('nonzeros1', non_zero1

        break

except:
    pass

import IPython
IPython.embed()

raise RuntimeError


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
