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
fpga = c.fhosts[int(args.host)]
configd = c.configd
n_chans=int(configd['fengine']['n_chans'])
n_xeng=int(configd['xengine']['x_per_fpga'])*len((configd['xengine']['hosts']).split(','))


#def get_fpga_data(fpga):
#    # if 'gbe_in_msb_ss' not in fpga.snapshots.names():
#    #     return get_fpga_data_new_snaps(fpga)
#    control_reg = fpga.registers.x_setup
#    control_reg.write(snap_arm=0)
#    #fpga.snapshots.gbe_in_msb_ss.arm(man_valid=True)
#    #fpga.snapshots.gbe_in_lsb_ss.arm(man_valid=True)
#    #fpga.snapshots.gbe_in_misc_ss.arm(man_valid=True)
#    fpga.snapshots.gbe_in_msb_ss.arm()
#    fpga.snapshots.gbe_in_lsb_ss.arm()
#    fpga.snapshots.gbe_in_misc_ss.arm()
#    control_reg.write(snap_arm=1)
#    time.sleep(0.1)
#    d = fpga.snapshots.gbe_in_msb_ss.read(arm=False)['data']
#    d.update(fpga.snapshots.gbe_in_lsb_ss.read(arm=False)['data'])
#    d.update(fpga.snapshots.gbe_in_misc_ss.read(arm=False)['data'])
#    control_reg.write(snap_arm=0)
#    return d

def get_fpga_data(fpga):
    print 'fetching data...'
    return fpga.gbes['gbe0'].read_txsnap()

#def print_snap_data(dd):
#    data_len = len(dd[dd.keys()[0]])
#    print(" IDX          64b MSB              64b                    64b                 64b LSB")
#    for ctr in range(data_len):
#        print('%5i' % ctr, end='')
#        d64_0 = dd['d_msb'][ctr] >> 64
#        d64_1 = dd['d_msb'][ctr] & (2 ** 64 - 1)
#        d64_2 = dd['d_lsb'][ctr] >> 64
#        d64_3 = dd['d_lsb'][ctr] & (2 ** 64 - 1)
#        raw_dv = dd['valid_raw'][ctr]
#        eof_str = 'EOF ' if dd['eof'][ctr] == 1 else ''
#        src_ip = network.IpAddress(dd['src_ip'][ctr])
#        src_ip_str = '%s:%i' % (str(src_ip), dd['src_port'][ctr])
#        print('%20x %20x %20x %20x rawdv(%2i) src(%s) %s' % (
#            d64_0, d64_1, d64_2, d64_3, raw_dv, src_ip_str, eof_str))
#
def print_snap_data(dd):
    packet_counter = 0 
    data_len = len(dd[dd.keys()[0]])
    rv={'data':[],'eof':[],'dest_ip':[]}
    print "IDX, PKT_IDX        64b MSB              64b                    64b                 64b LSB"
    for ctr in range(data_len):
        if dd['eof'][ctr-1]:
            packet_counter = 0 
        print'%5i,%5i' % (ctr, packet_counter),
        d64_0 = (dd['data'][ctr] >> 192) & (2 ** 64 - 1)
        d64_1 = (dd['data'][ctr] >> 128) & (2 ** 64 - 1)
        d64_2 = (dd['data'][ctr] >> 64 ) & (2 ** 64 - 1)
        d64_3 = dd['data'][ctr] & (2 ** 64 - 1)
        rv['data'].append(d64_0)
        rv['data'].append(d64_1)
        rv['data'].append(d64_2)
        rv['data'].append(d64_3)
        print "0x%016X  0x%016X  0x%016X  0x%016X"%(d64_0,d64_1,d64_2,d64_3),
        print "[%16s]->"%str(network.IpAddress(dd['ip'][ctr])),
#        print "[%16s:%i]"%(str(network.IpAddress(dd['dest_ip'][ctr])),dd['dest_port'][ctr]),
        if not dd['link_up'][ctr]: print "[LINK_DN]",
        if dd['led_tx']: print "[TX]",
        if dd['valid'][ctr]: print "[valid]",
        if dd['tx_over'][ctr]: print "[OVERFLOW]",
        if dd['tx_full'][ctr]: print "[AFULL]",
        if dd['eof'][ctr] == 1:  
            print 'EOF ',
            for wrd in range(3):
                rv['eof'].append(False)
            rv['eof'].append(True)
        else:
            for wrd in range(4):
                rv['eof'].append(False)
        for wrd in range(4):
            rv['dest_ip'].append(dd['ip'][ctr])
        print('')
        packet_counter += 1
    return rv

def exit_gracefully(sig, frame):
    print(sig)
    print(frame)
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGHUP, exit_gracefully)


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
    print "[Freq %5i]"%(pkt.headers[0x4103]+(pkt.headers[0x3]/pkt.headers[0x4])),
    print '[expected Xeng %3i]'%(pkt.headers[0x4103]/(n_chans/n_xeng)),
    print '[chan on that xeng %4i]'%(pkt.headers[0x3]/pkt.headers[0x4]),
    print ''


exit_gracefully(None, None)

