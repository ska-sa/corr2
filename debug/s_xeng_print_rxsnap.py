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

n_xeng=16
n_freqs=4096

parser = argparse.ArgumentParser(description='Display the contents of an FPGA''s Gbe buffers.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file.')
parser.add_argument(dest='host', type=str, action='store',
                    help='the host index of the engine')
#parser.add_argument('-l', '--listcores', dest='listcores', action='store_true',
#                    default=False,
#                    help='list cores on this device')
#parser.add_argument('-c', '--core', dest='core', action='store',
#                    default='gbe0', type=str,
#                    help='the core to query')
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



configfile = args.config
if 'CORR2INI' in os.environ.keys() and configfile == '':
    configfile = os.environ['CORR2INI']
if configfile == '':
    raise RuntimeError('No good carrying on without a config file')

# create the fpgas
c=corr2.fxcorrelator.FxCorrelator('bob',config_source=configfile)
c.initialise(configure=False,program=False,require_epoch=False)
fpga = c.xhosts[int(args.host)]
configd = c.configd
n_chans=int(configd['fengine']['n_chans'])
n_xeng=int(configd['xengine']['x_per_fpga'])*len((configd['xengine']['hosts']).split(','))

#def get_fpga_data(fpga):
#    # if 'gbe_in_msb_ss' not in fpga.snapshots.names():
#    #     return get_fpga_data_new_snaps(fpga)
#    control_reg = fpga.registers.gbesnap_control
#    control_reg.write(arm=0)
#    fpga.snapshots.gbe_in_msb_ss.arm()
#    fpga.snapshots.gbe_in_lsb_ss.arm()
#    fpga.snapshots.gbe_in_misc_ss.arm()
#    control_reg.write(arm=1)
#    time.sleep(1)
#    d = fpga.snapshots.gbe_in_msb_ss.read(arm=False)['data']
#    d.update(fpga.snapshots.gbe_in_lsb_ss.read(arm=False)['data'])
#    d.update(fpga.snapshots.gbe_in_misc_ss.read(arm=False)['data'])
#    control_reg.write(arm=0)
#    return d

def get_fpga_data(fpga):
    print 'fetching data...'
    return fpga.gbes['gbe0'].read_rxsnap()

def print_snap_data(dd):
    packet_counter = 0
    data_len = len(dd[dd.keys()[0]])
    rv={'data':[],'eof':[],'src_ip':[]}
    print "IDX, PKT_IDX        64b MSB              64b                    64b                 64b LSB"
    for ctr in range(data_len):
        if dd['eof'][ctr-1]:
            packet_counter = 0
        print'%5i,%5i' % (ctr, packet_counter),
#        d64_0 = (dd['data'][ctr] >> 192) & (2 ** 64 - 1)
#        d64_1 = (dd['data'][ctr] >> 128) & (2 ** 64 - 1)
#        d64_2 = (dd['data'][ctr] >> 64 ) & (2 ** 64 - 1)
#        d64_3 = dd['data'][ctr] & (2 ** 64 - 1)
#        rv['data'].append(d64_0)
#        rv['data'].append(d64_1)
#        rv['data'].append(d64_2)
#        rv['data'].append(d64_3)
        rv['data'].append(dd['data'][ctr])
        print '0x%016X'%dd['data'][ctr],
#        print "0x%016X  0x%016X  0x%016X  0x%016X"%(d64_0,d64_1,d64_2,d64_3),
        print "[%16s]"%str(network.IpAddress(dd['ip'][ctr])),
        #print "[%16s:%i]"%(str(network.IpAddress(dd['ip_in'][ctr])),dd['dest_port'][ctr]),
        if dd['bad_frame'][ctr] == 1: print 'BAD' ,
        if not dd['led_up'][ctr]: print "[LINK_DN]",
        if dd['led_rx'][ctr]: print "[RX]",
#        if dd['led_tx']: print "[TX]",
        if dd['valid'][ctr]>0: print "[valid]",
        if dd['overrun'][ctr]: print "[RX OVERFLOW]",
        if dd['eof'][ctr]: print '[EOF]',
        rv['eof'].append(dd['eof'][ctr])
        rv['src_ip'].append(dd['ip'][ctr])
        
#            print 'EOF ',
#            for wrd in range(3):
#                rv['eof'].append(False)
#            rv['eof'].append(True)
#        else:
#            for wrd in range(4):
#                rv['eof'].append(False)
#        for wrd in range(4):
#            rv['src_ip'].append(dd['ip'][ctr])
        print('')
        packet_counter += 1
    return rv


# read and print the data
data = get_fpga_data(fpga)
print data.keys()
unpacked_data=print_snap_data(data)
pkts=[]
last_index=-1
for eof_n,eof in enumerate(unpacked_data['eof']):
    if eof:
        pkts.append(unpacked_data['data'][last_index+1:eof_n])
        print '%i-%i=Pkt len: %i'%(eof_n,last_index,eof_n-last_index)
        last_index=eof_n


spead_processor = spead.SpeadProcessor(None, None, None, None)
gbe_packets = snap.Snap.packetise_snapdata(unpacked_data)
gbe_data=[]
for pkt in gbe_packets:
#    print pkt
    gbe_data.append(pkt['data'])
#    print gbe_data[-1]
#print gbe_data
#print pkts[0:2]
spead_processor.process_data(gbe_data)
# data now in    spead_processor.packets



packet_counter = 0
print "============================================="
print ""
print ""
print "Unpacked SPEAD data:"
print ""
for pkt_cnt,pkt in enumerate(spead_processor.packets):
    exp_xeng=pkt.headers[0x4103]/(n_chans/n_xeng)
    chan_on_this_xeng=pkt.headers[0x3]/pkt.headers[0x4]
    if exp_xeng==0:
        print '%4i'%pkt_cnt,
        print '[mcnt %16i]'%pkt.headers[0x1600],
    #    print '[flags %012X]'%pkt.headers[0x4102],
        print '[heap_id 0x%012X]'%pkt.headers[0x1],
        print '[heap_size %i]'%pkt.headers[0x2],
        print '[heap_offset %6i]'%pkt.headers[0x3],
        print '[length %i]'%pkt.headers[0x4],
        print '[ant %2i]'%pkt.headers[0x4101],
        print '[dest_ip %16s]'%network.IpAddress(gbe_packets[pkt_cnt]['src_ip'][-1]),
        print '[base_freq %5i]'%pkt.headers[0x4103],
        print "Calc'd:",
        print "[Freq %5i]"%(pkt.headers[0x4103]+(pkt.headers[0x3]/pkt.headers[0x4])),
        print '[expected Xeng %3i]'%(exp_xeng),
        print '[chan on that xeng %4i]'%(chan_on_this_xeng),
        print ''





