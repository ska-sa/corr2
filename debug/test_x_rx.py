#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""

Test the data received by an X-engine.

"""
import sys, logging, time, argparse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from corr2.katcp_client_fpga import KatcpClientFpga
from corr2.fpgadevice import tengbe

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
args = parser.parse_args()

# create the device and connect to it
fpga = KatcpClientFpga(args.hostname, 7147)
time.sleep(0.2)
if not fpga.is_connected():
    fpga.connect()
fpga.test_connection()
fpga.get_system_information()

verbose = False

# list the cores we find
if args.listcores:
    cores = fpga.tengbes.names()
    numgbes = len(cores)
    print 'Found %i ten gbe core%s:' % (numgbes, '' if numgbes == 1 else 's')
    for core in cores:
        print '\t', core
    fpga.disconnect()
    sys.exit(0)

def decode_item_pointer(current_spead_info, header_data):
    hdr_id = header_data >> current_spead_info['addr_bits']
    hdr_data = header_data & (pow(2, current_spead_info['addr_bits']) - 1)
    return (hdr_id, hdr_data)

def decode_spead_header(header_data):
    magic_number = header_data >> 56
    spead_version = (header_data >> 48) & 0xff
    spead_id_width = (header_data >> 40) & 0xff
    spead_addr_width = (header_data >> 32) & 0xff
    reserved = (header_data >> 16) & 0xffff
    num_headers = header_data & 0xffff
    return {'magic_number': magic_number,
            'version': spead_version,
            'id_bits': spead_id_width * 8,
            'addr_bits': spead_addr_width * 8,
            'reserved': reserved,
            'num_headers': num_headers,
            'flavour': '%s,%s' % ((spead_addr_width * 8) + (spead_id_width * 8), (spead_addr_width * 8))}

def process_spead(current_spead_info, data, packet_counter):
    global current_fchan
    global discovered_fchans
    if packet_counter == 1:
        spead_header = decode_spead_header(data)
        if len(current_spead_info) == 0:
            current_spead_info = spead_header
        rv_string = 'spead %s, %d headers to come' % (spead_header['flavour'], spead_header['num_headers'])
        if current_spead_info['num_headers'] != spead_header['num_headers']:
            rv_string += ', ERROR: num spead hdrs changed from %d to %d?!' % (current_spead_info['num_headers'], spead_header['num_headers'])
        return spead_header, rv_string
    elif (packet_counter > 1) and (packet_counter <= 1 + current_spead_info['num_headers']):
        hdr_id, hdr_data = decode_item_pointer(current_spead_info, data)
        if hdr_id == 0x004:
            current_spead_info['packet_length'] = current_spead_info['num_headers'] + hdr_data
        if hdr_id == 0x4103:
            if hdr_data not in discovered_fchans:
                discovered_fchans.append(hdr_data)
            current_fchan = hdr_data
        return current_spead_info if hdr_id == 0x0004 else None, 'spead hdr 0x%04x: %d' % (hdr_id, hdr_data)
    else:
        p0_0 = (data >> 48) & 0xffff
        p1_0 = (data >> 32) & 0xffff
        p0_1 = (data >> 16) & 0xffff
        p1_1 = (data >> 0)  & 0xffff
        data = '%d, %d, %d, %d' % (p0_0, p1_0, p0_1, p1_1)
        if current_fchan != -1:
            if (p0_0 != current_fchan) or (p0_1 != current_fchan) or (p1_0 != current_fchan + 4096) or (p1_1 != current_fchan + 4096):
                print 'hdr says fchan %d, data in that packet says %d, %d, %d, %d. Issue.' % (current_fchan, p0_0, p1_0, p0_1, p1_1)
        data = '%d, %d, %d, %d' % (p0_0, p1_0, p0_1, p1_1)
        return None, data

if args.direction == 'tx':
    key_order = ['led_tx', 'eof', 'valid', 'tx_full', 'tx_over', 'link_up', 'ip', 'data']
    data_key = 'data'
    ip_key = 'ip'
    eof_key = 'eof'
    coredata = fpga.device_by_name(args.core).read_txsnap()
else:
    key_order = ['led_up', 'led_rx', 'valid_in', 'eof_in', 'bad_frame', 'overrun', 'ip_in', 'data_in']
    data_key = 'data_in'
    ip_key = 'ip_in'
    eof_key = 'eof_in'
    coredata = fpga.device_by_name(args.core).read_rxsnap()

# read the snap block
spead_info = {}
packet_counter = 1
discovered_fchans = []
for ppp in range(0,1000):
    current_fchan = -1
    coredata = fpga.device_by_name(args.core).read_rxsnap()
    print '.',
    sys.stdout.flush()
    for ctr in range(0, len(coredata[coredata.keys()[0]])):
        packet_length_error = False
        if coredata[eof_key][ctr]:
            if args.spead and (packet_counter != spead_info['packet_length'] + 1):
                packet_length_error = True
            packet_counter = 0
        if verbose:
            print '%5d,%3d' % (ctr, packet_counter),
        for key in key_order:
            if key == ip_key:
                if verbose:
                    print '%s(%s)' % (key, tengbe.ip2str(coredata[key][ctr])), '\t',
            elif (key == data_key) and args.spead:
                new_spead_info, spead_stringdata = process_spead(spead_info, coredata[data_key][ctr], packet_counter)
                if new_spead_info != None:
                    spead_info = new_spead_info.copy()
                if verbose:
                    print '%s(%s)' % (key, spead_stringdata), '\t',
            else:
                if verbose:
                    print '%s(%s)' % (key, coredata[key][ctr]), '\t',
        if verbose:
            print 'PACKET LENGTH ERROR' if packet_length_error else ''
        packet_counter += 1

discovered_fchans.sort()
print discovered_fchans


# end
