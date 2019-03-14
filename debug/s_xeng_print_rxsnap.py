#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the contents of am FX correlator's X-engine's TenGBE RX, or an F-engine's TX snapblock. Decode and print SPEAD data.

@author: paulp, jmanley
"""
import sys
import time
import argparse
import casperfpga
import corr2
import os

from casperfpga import network
from casperfpga import spead
from casperfpga import snap
from casperfpga import spead as casperspead
from casperfpga import snap as caspersnap

n_xeng = 16
n_freqs = 4096

parser = argparse.ArgumentParser(
    description='Display the contents of an FPGA'
    's Gbe buffers.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file.')
parser.add_argument(dest='host', type=str, action='store',
                    help='the host index of the engine')
# parser.add_argument('-l', '--listcores', dest='listcores', action='store_true',
#                    default=False,
#                    help='list cores on this device')
# parser.add_argument('-c', '--core', dest='core', action='store',
#                    default='gbe0', type=str,
#                    help='the core to query')
parser.add_argument(
    '--loglevel',
    dest='log_level',
    action='store',
    default='',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

configfile = args.config
if 'CORR2INI' in os.environ.keys() and configfile == '':
    configfile = os.environ['CORR2INI']
if configfile == '':
    raise RuntimeError('No good carrying on without a config file')

# create the fpgas
c = corr2.fxcorrelator.FxCorrelator('bob', config_source=configfile)
c.initialise(configure=False, program=False, require_epoch=False)
fpga = c.xhosts[int(args.host)]
configd = c.configd
n_chans = int(configd['fengine']['n_chans'])
n_xeng = int(configd['xengine']['x_per_fpga']) * \
    len((configd['xengine']['hosts']).split(','))


def get_fpga_data(fpga):
    print 'fetching data...'
    gbe = fpga.gbes.keys()[0]
    return fpga.gbes[gbe].read_rxsnap()


def print_snap_data(dd):
    packet_counter = 0
    data_len = len(dd[dd.keys()[0]])
    rv = {'data': [], 'eof': [], 'src_ip': []}
    print "IDX, PKT_IDX        64b MSB              64b                    64b                 64b LSB"
    for ctr in range(data_len):
        if dd['eof'][ctr - 1]:
            packet_counter = 0
        print'%5i,%5i' % (ctr, packet_counter),
        rv['data'].append(dd['data'][ctr])
        print '0x%016X' % dd['data'][ctr],
        print "[%16s]" % str(network.IpAddress(dd['src_ip'][ctr])),
        if dd['bad_frame'][ctr] == 1:
            print 'BAD',
        if not dd['led_up'][ctr]:
            print "[LINK_DN]",
        if dd['led_rx'][ctr]:
            print "[RX]",
        if dd['valid'][ctr] > 0:
            print "[valid]",
        if dd['overrun'][ctr]:
            print "[RX OVERFLOW]",
        if dd['eof'][ctr]:
            print '[EOF]',
        rv['eof'].append(dd['eof'][ctr])
        rv['src_ip'].append(dd['src_ip'][ctr])
        packet_counter += 1
        print ''
    return rv


# read and print the data
data = get_fpga_data(fpga)
print data.keys()
unpacked_data = print_snap_data(data)
pkts = []
last_index = -1
for eof_n, eof in enumerate(unpacked_data['eof']):
    if eof:
        pkts.append(unpacked_data['data'][last_index + 1:eof_n])
        print '%i-%i=Pkt len: %i' % (eof_n, last_index, eof_n - last_index)
        last_index = eof_n

spead_processor = spead.SpeadProcessor(None, None, None, None)
gbe_packets = snap.Snap.packetise_snapdata(unpacked_data)
gbe_data = []
for pkt in gbe_packets:
    gbe_data.append(pkt['data'])
spead_processor.process_data(gbe_data)

packet_counter = 0
print "============================================="
print ""
print ""
print "Unpacked SPEAD data:"
print ""
for pkt_cnt, pkt in enumerate(spead_processor.packets):
    #from IPython import embed; embed()
    #print pkt
    exp_xeng = pkt.headers[0x4103] / (n_chans / n_xeng)
    chan_on_this_xeng = pkt.headers[0x3] / pkt.headers[0x4]
    # if exp_xeng==0:
    if True:
        print '%4i' % pkt_cnt,
        print '[mcnt %012x]' % pkt.headers[0x1600],
        print '[heap_id 0x%012X]' % pkt.headers[0x1],
        print '[heap_size %i]' % pkt.headers[0x2],
        print '[heap_offset 0x%06X]' % pkt.headers[0x3],
        print '[length %i]' % pkt.headers[0x4],
        print '[ant %2i]' % pkt.headers[0x4101],
        print '[dest_ip %16s]' % network.IpAddress(
            gbe_packets[pkt_cnt]['src_ip'][-1]),
        print '[base_freq %5i]' % pkt.headers[0x4103],
        print "Calc'd:",
        print "[Freq %5i]" % (pkt.headers[0x4103] +
                              (pkt.headers[0x3] / pkt.headers[0x4])),
        print '[expected Xeng %3i]' % (exp_xeng),
        print '[chan on that xeng %4i]' % (chan_on_this_xeng),
        print ''
