#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Print the incoming data to an x-engine.
"""
#from __future__ import print_function

import os
import sys
import time
import argparse
import signal
import logging
from casperfpga import network,snap,spead
from corr2 import utils
import corr2
import numpy
from IPython import embed
import pylab

parser = argparse.ArgumentParser(
    description='Print the x-engine RX snapshot.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    dest='host', type=str, action='store', default='',
    help='the F-engine host to query, an int, taken positionally '
         'from the config file list of f-hosts')
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument(
    '--bitstream', dest='bitstream', type=str, action='store', default='',
    help='a bitstream for the f-engine hosts (Skarabs need this given '
         'if no config is found)')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='INFO',
    help='log level to use, options INFO, DEBUG, ERROR')
parser.add_argument(
    '--plot_freq', dest='plot_freq', action='store', default='2000',
    help='Plot this frequency channel, if found.')
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
plot_freq = int(args.plot_freq)
print 'Stopping on freq: ',plot_freq

# create the fpgas
c=corr2.fxcorrelator.FxCorrelator('bob',config_source=configfile)
c.initialise(configure=False,program=False,require_epoch=False)
fpga = c.fhosts[int(args.host)]
configd = c.configd
n_chans=int(configd['fengine']['n_chans'])
n_xeng=int(configd['xengine']['x_per_fpga'])*len((configd['xengine']['hosts']).split(','))

def get_fpga_data(fpga):
    print 'fetching data...'
    return fpga.gbes['gbe0'].read_txsnap()

def print_snap_data(dd,print_output=False):
    packet_counter = 0 
    data_len = len(dd[dd.keys()[0]])
    rv={'data':[],'eof':[],'dest_ip':[]}
    if print_output: print dd.keys()
    if print_output: print "IDX, PKT_IDX        64b MSB              64b                    64b                 64b LSB"
    for ctr in range(data_len):
        if dd['eof'][ctr-1]:
            packet_counter = 0 
        rv['data'].append(dd['data'][ctr])
        if print_output: 
            print'%5i,%5i' % (ctr, packet_counter),
            #print "0x%016X  0x%016X  0x%016X  0x%016X"%(d64_0,d64_1,d64_2,d64_3),
            print '0x%016X'%dd['data'][ctr],
#['led_tx', 'eof', 'ip', 'valid', 'tx_full', 'data', 'tx_over', 'link_up']
            print "[%16s]"%str(network.IpAddress(dd['ip'][ctr])),
            if not dd['link_up'][ctr]: print "[LINK_DN]",
            if dd['led_tx']: print "[TX]",
            if dd['valid'][ctr]: print "[valid]",
            if dd['tx_over'][ctr]: print "[OVERFLOW]",
            if dd['tx_full'][ctr]: print "[AFULL]",
            if dd['eof'][ctr]: print '[EOF]',
            print('')
        rv['eof'].append(dd['eof'][ctr])
        rv['dest_ip'].append(dd['ip'][ctr])
        packet_counter += 1
    return rv

def exit_gracefully(sig, frame):
    print(sig)
    print(frame)
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGHUP, exit_gracefully)

found = False

while not found:
    # read and print the data
    data = get_fpga_data(fpga)
    unpacked_data=print_snap_data(data)
    last_index=-1
    for eof_n,eof in enumerate(unpacked_data['eof']):
        if eof: 
            print '%i-%i=Pkt len: %i'%(eof_n/4,last_index,eof_n/4-last_index)
            last_index=eof_n/4

    spead_processor = spead.SpeadProcessor(None, None, None, None)
    gbe_packets = snap.Snap.packetise_snapdata(unpacked_data)
    gbe_data=[]
    for pkt in gbe_packets:
        gbe_data.append(pkt['data'])
    spead_processor.process_data(gbe_data)
    # data now in    spead_processor.packets

    packet_counter = 0 
    print "============================================="
    print ""
    print ""
    print "Unpacked SPEAD data:"
    print ""
    for pkt_cnt,pkt in enumerate(spead_processor.packets):
        powerx=0
        powery=0
        for d in pkt.data:
            powerx+=(numpy.abs((d&0xff00000000000000)>>56)+numpy.abs((d&0x00ff000000000000)>>48)+numpy.abs((d&0x0000000000ff0000)>>16)+numpy.abs((d&0x00000000ff000000)>>24))
            powery+=(numpy.abs((d&0x0000ff0000000000)>>40)+numpy.abs((d&0x000000ff00000000)>>32)+numpy.abs((d&0x000000000000ff00)>>8)+ numpy.abs((d&0x00000000000000ff)))
        freq=pkt.headers[0x4103]+(pkt.headers[0x3]/pkt.headers[0x4])
        print '%4i'%pkt_cnt,
        print '[mcnt %16i]'%pkt.headers[0x1600],
    #    print '[flags %012X]'%pkt.headers[0x4102],
        print '[heap_id 0x%012X]'%pkt.headers[0x1],
        print '[heap_size %i]'%pkt.headers[0x2],
        print '[heap_offset %6i]'%pkt.headers[0x3],
        print '[length %i]'%pkt.headers[0x4],
        print '[ant %2i]'%pkt.headers[0x4101],
        print '[dest_ip %16s]'%network.IpAddress(gbe_packets[pkt_cnt]['dest_ip'][-1]),
        print '[base_freq %5i]'%pkt.headers[0x4103],
        print "Calc'd:",
        print "[Freq %5i]"%(freq),
        print '[expected Xeng %3i]'%(pkt.headers[0x4103]/(n_chans/n_xeng)),
        print '[chan on that xeng %4i]'%(pkt.headers[0x3]/pkt.headers[0x4]),
        print 'Power X: %8i; Power Y: %8i'%(powerx,powery)
        if freq==plot_freq:
        #if True:
            print 'found freq %i!'%freq
            x=[] 
            y=[] 
            for d in pkt.data:
                x.append(numpy.int8((d&0xff00000000000000)>>56) + 1j*numpy.int8((d&0x00ff000000000000)>>48))
                y.append(numpy.int8((d&0x0000ff0000000000)>>40) + 1j*numpy.int8((d&0x000000ff00000000)>>32))
                x.append(numpy.int8((d&0x00000000ff000000)>>24) + 1j*numpy.int8((d&0x0000000000ff0000)>>16))
                y.append(numpy.int8((d&0x000000000000ff00)>>8) + 1j*numpy.int8((d&0x00000000000000ff)>>0))
            embed()
            found = True
        


exit_gracefully(None, None)

