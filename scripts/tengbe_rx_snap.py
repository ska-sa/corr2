#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given digitiser.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys, logging, time, argparse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from corr2.katcp_client_fpga import KatcpClientFpga
from corr2.fpgadevice import tengbe

parser = argparse.ArgumentParser(description='Display information about a MeerKAT digitiser.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hostname', type=str, action='store',
                    help='the hostname of the digitiser')
parser.add_argument('-l', '--listcores', dest='listcores', action='store_true',
                    default=False,
                    help='list cores on this device')
parser.add_argument('-c', '--core', dest='core', action='store',
                    default='gbe0', type=str,
                    help='the core to query')
parser.add_argument('--spead_flavour', dest='spead_flavour', action='store',
                    default='64,48', type=str,
                    help='spead flavour to use')
parser.add_argument('--spead_length', dest='spead_length', action='store',
                    default=-1, type=int,
                    help='the 10GBE SPEAD payload length, in bytes')
args = parser.parse_args()

# create the device and connect to it
fpga = KatcpClientFpga(args.hostname, 7147)
time.sleep(0.5)
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
        return None, 'spead hdr 0x%04x: %d' % (hdr_id, hdr_data)
    else:
        return None, data

# read the snap block
spead_info = {}
packet_counter = 1
coredata = fpga.device_by_name(args.core).read_rxsnap()
for ctr in range(0, len(coredata[coredata.keys()[0]])):
    packet_length_error = False
    key_order = ['led_up', 'led_rx', 'valid_in', 'eof_in', 'bad_frame', 'overrun', 'ip_in', 'data_in']
    if coredata['eof_in'][ctr]:
        if (args.spead_length > 0) and (packet_counter != 128):
            packet_length_error = True
        packet_counter = 0
    print '%5d,%3d' % (ctr, packet_counter),
    for key in key_order:
        if key == 'ip_in':
            print '%s(%s)' % (key, tengbe.ip2str(coredata[key][ctr])), '\t',
        elif key == 'data_in':
            if args.spead_length > 0:
                new_spead_info, spead_data = process_spead(spead_info, coredata['data_in'][ctr], packet_counter)
                if new_spead_info != None:
                    spead_info = new_spead_info.copy()
                print '%s(%s)' % (key, spead_data), '\t',
            else:
                print '%s(%s)' % (key, coredata[key][ctr]), '\t',
        else:
            print '%s(%s)' % (key, coredata[key][ctr]), '\t',
    print 'PACKET LENGTH ERROR' if packet_length_error else ''
    packet_counter += 1

# end
