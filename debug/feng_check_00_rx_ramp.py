#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys
import time
import argparse

from casperfpga import spead as casperspead
from casperfpga import utils as casperutils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga

parser = argparse.ArgumentParser(description='Display the contents of an FPGA\'s 10Gbe buffers.',
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
                    default='rx', type=str,
                    help='tx or rx stream')
parser.add_argument('-s', '--spead', dest='spead', action='store_true',
                    default=False,
                    help='try and decode spead in this 10Gbe stream')
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

if args.comms == 'katcp':
    HOSTCLASS = katcp_fpga.KatcpFpga
else:
    HOSTCLASS = dcp_fpga.DcpFpga

# create the device and connect to it
fpga = HOSTCLASS(args.hostname, 7147)
time.sleep(0.2)
if not fpga.is_connected():
    fpga.connect()
fpga.test_connection()
fpga.get_system_information()

# list the cores we find
if args.listcores:
    cores = fpga.tengbes.names()
    numgbes = len(cores)
    print 'Found %i ten gbe core%s:' % (numgbes, '' if numgbes == 1 else 's')
    for core in cores:
        print '\t', core
    fpga.disconnect()
    sys.exit(0)

if args.direction == 'tx':
    key_order = ['led_tx', 'eof', 'valid', 'tx_full', 'tx_over', 'link_up', 'ip', 'data']
    data_key = 'data'
    ip_key = 'ip'
    eof_key = 'eof'
    coredata = fpga.tengbes[args.core].read_txsnap()
else:
    key_order = ['led_up', 'led_rx', 'valid_in', 'eof_in', 'bad_frame', 'overrun', 'ip_in', 'data_in']
    data_key = 'data_in'
    ip_key = 'ip_in'
    eof_key = 'eof_in'
    coredata = fpga.tengbes[args.core].read_rxsnap()

fpga.disconnect()

# read through the data from the core snapshot and check the ramp inside it


def unpack64_to_80(datalist):
    words80 = []
    for wordctr in range(0, len(datalist), 5):
        word64_0 = datalist[wordctr + 0]
        word64_1 = datalist[wordctr + 1]
        word64_2 = datalist[wordctr + 2]
        word64_3 = datalist[wordctr + 3]
        word64_4 = datalist[wordctr + 4]
        word80_0 = ((word64_1 & 0x000000000000ffff) << 64) | ((word64_0 & 0xffffffffffffffff) << 0)
        word80_1 = ((word64_2 & 0x00000000ffffffff) << 48) | ((word64_1 & 0xffffffffffff0000) >> 16)
        word80_2 = ((word64_3 & 0x0000ffffffffffff) << 32) | ((word64_2 & 0xffffffff00000000) >> 32)
        word80_3 = ((word64_4 & 0xffffffffffffffff) << 16) | ((word64_3 & 0xffff000000000000) >> 48)
        words80.append(word80_0)
        words80.append(word80_1)
        words80.append(word80_2)
        words80.append(word80_3)
    return words80

spead_processor = casperspead.SpeadProcessor(4, '64,48', 640, 8)
gbepackets = casperutils.packetise_snapdata(coredata, eof_key=eof_key)
print 'Found %i GBE packets.\nChecking length and decoding SPEAD.' % len(gbepackets)
gbe_data = []
for pkt in gbepackets:
    gbe_data.append(pkt[data_key])
spead_processor.process_data(gbe_data)
del gbepackets
print 'Checking packet contents.'
last_time = spead_processor.packets[0].headers[0x1600] - 8192
errors_headers = 0
errors_datatime = 0
errors_dataramp = 0
pkt_times = []
for pkt in spead_processor.packets:
    if pkt.headers[0x1600] != last_time + 8192:
        errors_headers += 1
    pkt_times.append(pkt.headers[0x1600])
    data80 = unpack64_to_80(pkt.data)
    data_tvg = []
    for word80 in data80:
        time80 = word80 >> 32
        ctr80 = (word80 & 0xffffffff) >> 1
        pol80 = word80 & 0x01
        data_tvg.append((time80, ctr80, pol80))
    del data80
    if data_tvg[0][0] != last_time + 8192:
        errors_datatime += 1
    if data_tvg[0][1] != 0:
        errors_dataramp += 1
    data_time = data_tvg[0][0] - 8
    data_ctr = data_tvg[0][1] - 1
    for ctr, data in enumerate(data_tvg):
        if data[0] != data_time + 8:
            errors_datatime += 1
        if data[1] != data_ctr + 1:
            errors_dataramp += 1
        data_time = data[0]
        data_ctr = data[1]
    last_time = pkt.headers[0x1600]

if errors_dataramp > 0 or errors_datatime > 0 or errors_headers > 0:
    unpacked = []
    for pkt in spead_processor.packets:
        data80 = unpack64_to_80(pkt.data)
        data_tvg = []
        for word80 in data80:
            time80 = word80 >> 32
            ctr80 = (word80 & 0xffffffff) >> 1
            pol80 = word80 & 0x01
            data_tvg.append((time80, ctr80, pol80))
        del data80
        unpacked.append(data_tvg)
    print unpacked
    print 'Header errors: ', errors_headers
    print 'Data time errors: ', errors_datatime
    print 'Data ramp errors: ', errors_dataramp
    raise RuntimeError('Some data was not correct.')

print 'Contents okay. Found SPEAD packets with timestamps:', pkt_times

# end
