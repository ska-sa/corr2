#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check the SPEAD error counter and valid counter in the 
unpack section of the F-engines.

@author: paulp
"""
import os
import logging
import IPython

from casperfpga import casperfpga
from casperfpga import spead as casperspead
from casperfpga import snap as caspersnap

from corr2.utils import AdcData

logging.basicConfig(level=logging.INFO)

DENG = False

if DENG:
    f = casperfpga.CasperFpga(os.environ['SKARAB_DSIM'])
    f.get_system_information(os.environ['SKARAB_DSIM_FPG'])
else:
    f = casperfpga.CasperFpga('skarab020306-01')
    f.get_system_information('/srv/bofs/feng/s_c856m4k_2018-02-01_1538.fpg')

gbe_name = f.gbes.keys()[0]
gbe = f.gbes[gbe_name]
expected_packet_length = -1
eof_key = 'eof'
data_key = 'data'


def get_spead_packets():
    if DENG:
        coredata = gbe.read_txsnap()
    else:
        coredata = gbe.read_rxsnap()
    spead_processor = casperspead.SpeadProcessor(None, None, None, None)
    gbe_packets = caspersnap.Snap.packetise_snapdata(coredata, eof_key)
    gbe_data = []
    for pkt in gbe_packets:
        if (expected_packet_length > -1) and \
                (len(pkt[data_key]) != expected_packet_length):
            raise RuntimeError(
                'Gbe packet not correct length - should be {}. is {}'.format(
                    expected_packet_length, len(pkt[data_key])))
        gbe_data.append(pkt[data_key])
    spead_processor.process_data(gbe_data)
    return spead_processor.packets[:]


def check_timestamps(packets):
    start = 0
    while packets[start].headers[1] != packets[start + 1].headers[1]:
        start += 1
    num_pkts = len(packets)
    last_time = packets[start].headers[1] - 4096
    time_errors = False
    for ctr in range(start, num_pkts-start, 2):
        pktp0 = packets[ctr]
        pktp1 = packets[ctr+1]
        if pktp0.headers[1] != pktp1.headers[1]:
            msg = 'time error between polarisations'
            print(msg)
            print(pktp0.headers)
            print(pktp1.headers)
            IPython.embed()
            raise RuntimeError(msg)
        this_time = pktp0.headers[1]
        time_diff = this_time - last_time
        if time_diff != 4096:
            msg = 'time diff is %i != 4096' % time_diff
            IPython.embed()
            raise RuntimeError(msg)
        last_time = this_time


def check_pols(packets):
    start = 0
    while packets[start].headers[1] != packets[start + 1].headers[1]:
        start += 1
    num_pkts = len(packets)
    for ctr in range(start, num_pkts-start, 2):
        pktp0 = packets[ctr]
        pktp1 = packets[ctr+1]
        d80p0 = AdcData.sixty_four_to_eighty_skarab(pktp0.data)
        d80p1 = AdcData.sixty_four_to_eighty_skarab(pktp1.data)
        for d in d80p0[1:]:
            if (d >> 79) != 0:
                msg = 'pol0 data MSB wrong'
                print(msg)
                print(pktp0.headers)
                print(pktp1.headers)
                IPython.embed()
                raise RuntimeError(msg)
        for d in d80p1[1:]:
            if (d >> 79) != 1:
                msg = 'pol1 data MSB wrong'
                print(msg)
                print(pktp0.headers)
                print(pktp1.headers)
                IPython.embed()
                raise RuntimeError(msg)
        for dctr in range(len(d80p0)):
            if (d80p0[dctr] & ((2**79)-1)) != (d80p1[dctr] & ((2**79)-1)):
                msg = 'pols do not agree'
                print(msg)
                print(pktp0.headers)
                print(pktp1.headers)
                IPython.embed()
                raise RuntimeError(msg)


def check_counter80(packets):
    start = 0
    while packets[start].headers[1] != packets[start + 1].headers[1]:
        start += 1
    num_pkts = len(packets)
    last_cnt = None
    for ctr in range(start, num_pkts - start, 2):
        # print('DOING PKT', ctr, last_cnt)
        pkt = packets[ctr]
        d80 = AdcData.sixty_four_to_eighty_skarab(pkt.data)
        if pkt.headers[1] != d80[0]:
            msg = 'timestamp in data does not match SPEAD header'
            print(pkt.headers[1])
            print(d80[0])
            print(msg)
            IPython.embed()
            raise RuntimeError(msg)
        for d80ctr in range(len(d80)):
            d80[d80ctr] = d80[d80ctr] & ((2**79)-1)
        if last_cnt is None:
            last_cnt = d80[1] - 2
        if d80[1] != last_cnt + 2:
            msg = 'break in the count at the first word'
            print(ctr)
            print(packets[ctr-1].headers)
            print(pkt.headers)

            d80_0 = AdcData.sixty_four_to_eighty_skarab(packets[ctr - 1].data)
            d80_1 = AdcData.sixty_four_to_eighty_skarab(packets[ctr].data)
            d80_2 = AdcData.sixty_four_to_eighty_skarab(packets[ctr + 1].data)

            print([(d & ((2 ** 79) - 1)) for d in d80_0[0:5]])
            print([(d & ((2 ** 79) - 1)) for d in d80_1[0:5]])
            print([(d & ((2 ** 79) - 1)) for d in d80_2[0:5]])

            print(d80[1])
            print(last_cnt)
            print(msg)
            IPython.embed()
            raise RuntimeError(msg)
        last_cnt = d80[1] - 1
        for dword in d80[1:]:
            if dword != last_cnt + 1:
                msg = 'break in the count'
                print(dword)
                print(last_cnt)
                print(msg)
                IPython.embed()
                raise RuntimeError(msg)
            last_cnt += 1


# for main_ctr in range(100):
main_ctr = 0
while True:
    packets = get_spead_packets()
    print(main_ctr)
    check_timestamps(packets)
    check_pols(packets)
    check_counter80(packets)
    main_ctr += 1


# end
