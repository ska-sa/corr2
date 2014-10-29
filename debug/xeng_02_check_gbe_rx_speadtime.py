#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given digitiser.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys
import signal
import time
import argparse

from casperfpga import tengbe
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga

SPEAD_EXPECTED_VERSION = 4
SPEAD_EXPECTED_FLAVOUR = '64,48'

parser = argparse.ArgumentParser(description='Check that the incoming times from the f-engines have the correct'
                                             'time steps and formatting.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hostname', type=str, action='store',
                    help='the hostname of the digitiser')
parser.add_argument('--timestep', dest='timestep', action='store', default=2**21, type=long,
                    help='the expected time step between packets')
parser.add_argument('--zerobits', dest='zerobits', action='store', default=12, type=int,
                    help='how many lsbs of the timestamp should be zero?')
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


def find_spead_header(speaddata, expected_version, expected_flavour):
    for __ctr, dataword in enumerate(speaddata):
        decoded = decode_spead_header(dataword)
        if (decoded['magic_number'] == 83) and (decoded['reserved'] == 0) and \
           (decoded['version'] == expected_version) and (decoded['flavour'] == expected_flavour):
            return __ctr
    return -1


def decode_item_pointer(address_bits, id_bits, header_data):
    hdr_id = header_data >> address_bits
    # if the top bit is set, it's immediate addressing so clear the top bit
    if hdr_id & pow(2, id_bits - 1):
        hdr_id &= pow(2, id_bits - 1) - 1
    hdr_data = header_data & (pow(2, address_bits) - 1)
    return hdr_id, hdr_data


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
            'address_bits': spead_addr_width * 8,
            'reserved': reserved,
            'num_headers': num_headers,
            'flavour': '%s,%s' % ((spead_addr_width * 8) + (spead_id_width * 8), (spead_addr_width * 8))}


def process_spead_word(current_spead_info, data, pkt_counter):
    if pkt_counter == 1:
        spead_header = decode_spead_header(data)
        if len(current_spead_info) == 0:
            current_spead_info = spead_header
        rv_string = 'spead %s, %d headers to come' % (spead_header['flavour'], spead_header['num_headers'])
        if current_spead_info['num_headers'] != spead_header['num_headers']:
            rv_string += ', ERROR: num spead hdrs changed from %d to %d?!' %\
                         (current_spead_info['num_headers'], spead_header['num_headers'])
        return spead_header, rv_string
    elif (pkt_counter > 1) and (pkt_counter <= 1 + current_spead_info['num_headers']):
        hdr_id, hdr_data = decode_item_pointer(current_spead_info['address_bits'], current_spead_info['id_bits'], data)
        if hdr_id == 0x0004:
            # the SPEAD packet length is in BYTES! we're counting 64-bit words, so divide by 8
            current_spead_info['packet_length'] = current_spead_info['num_headers'] + (hdr_data / 8)

        if hdr_id == 0x1600:
            global First_time
            global Time_errors
            global Time_steps
            global Time_stepped

            # check the lsbs
            if hdr_data & (2**args.zerobits - 1) != 0:
                print 'spead 0x1600 time lsb error: %i' % hdr_data
                sys.stdout.flush()

            if First_time == -1:
                First_time = hdr_data
            else:
                if hdr_data != First_time and not Time_stepped:
                    Time_steps += 1
                    timediff = hdr_data - First_time
                    if timediff != args.timestep:
                        Time_errors += 1
                    print 'spead 0x1600 time diff: %i -> %i = %i' % (First_time, hdr_data, timediff), \
                        '-', 'okay' if timediff == args.timestep else 'ERROR',\
                        '%i steps, %i errors' % (Time_steps, Time_errors)
                    sys.stdout.flush()
                    Time_stepped = True

        string_data = 'spead hdr 0x%04x: ' % hdr_id + ('%d' % hdr_data if not args.hex else '0x%X' % hdr_data)
        return current_spead_info if hdr_id == 0x0004 else None, string_data
    else:
        # data = '%d, %d, %d, %d' % (data >> 48, (data >> 32) & 0xffff, (data >> 16) & 0xffff, (data >> 0) & 0xffff)
        return None, data


def packetise_snapdata(data, eof_key='eof'):
    _current_packet = {}
    _packets = []
    for _ctr in range(0, len(data[eof_key])):
        for key in data.keys():
            if key not in _current_packet.keys():
                _current_packet[key] = []
            _current_packet[key].append(data[key][_ctr])
        if _current_packet[eof_key][-1]:
            _packets.append(_current_packet)
            _current_packet = {}
    return _packets


def gbe_to_spead(gbedata):
    pkt_counter = 1
    _current_packet = {'headers': {}, 'data': []}
    for wordctr in range(0, len(gbedata)):
        if pkt_counter == 1:
            spead_header = decode_spead_header(gbedata[wordctr])
            _current_packet['headers'][0] = spead_header
        elif (pkt_counter > 1) and (pkt_counter <= 1 + _current_packet['headers'][0]['num_headers']):
            hdr_id, hdr_data = decode_item_pointer(_current_packet['headers'][0]['address_bits'],
                                                    _current_packet['headers'][0]['id_bits'],
                                                    gbedata[wordctr])
            # the SPEAD packet length is in BYTES! we're counting 64-bit words, so divide by 8
            if hdr_id == 0x0004:
                _current_packet['headers'][0]['packet_length'] = _current_packet['headers'][0]['num_headers'] + \
                                                                 (hdr_data / 8)
            if hdr_id in _current_packet['headers'].keys():
                raise RuntimeError('Header ID 0x%04x already exists in packet!' % hdr_id)
            _current_packet['headers'][hdr_id] = hdr_data
        else:
            _current_packet['data'].append(gbedata[wordctr])
        pkt_counter += 1
    if _current_packet['headers'][0]['packet_length'] + 1 != len(gbedata):
        raise ValueError('SPEAD header packet length %d does not match GBE packet length %d') % \
              (_current_packet['headers'][0]['packet_length'] + 1, len(gbedata))
    return _current_packet


def exit_gracefully(_, __):
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

Time_errors = 0
Time_steps = 0

while True:
    key_order = ['led_up', 'led_rx', 'valid_in', 'eof_in', 'bad_frame', 'overrun', 'ip_in', 'data_in']
    data_key = 'data_in'
    ip_key = 'ip_in'
    eof_key = 'eof_in'
    coredata = fpga.tengbes.gbe0.read_rxsnap()

    First_time = -1
    Time_stepped = False

    # read the snap block
    spead_info = {}
    packet_counter = 1
    for ctr in range(0, len(coredata[coredata.keys()[0]])):
        packet_length_error = False
        if coredata[eof_key][ctr]:
            if packet_counter != spead_info['packet_length'] + 1:
                packet_length_error = True
            packet_counter = 0
        # print '%5d,%3d' % (ctr, packet_counter),
        for key in key_order:
            if key == ip_key:
                if key == 'ip':
                    display_key = 'dst_ip'
                elif key == 'ip_in':
                    display_key = 'src_ip'
                else:
                    raise RuntimeError('Unknown IP key?')
                # print '%s(%s)' % (display_key, tengbe.ip2str(coredata[key][ctr])), '\t',
            elif key == data_key:
                new_spead_info, spead_stringdata = process_spead_word(spead_info, coredata[data_key][ctr], packet_counter)
                if new_spead_info is not None:
                    spead_info = new_spead_info.copy()
                # print '%s(%s)' % (key, spead_stringdata), '\t',
            # else:
            #     if args.hex:
            #         print '%s(0x%X)' % (key, coredata[key][ctr]), '\t',
            #     else:
            #         print '%s(%s)' % (key, coredata[key][ctr]), '\t',
        if packet_length_error:
            print 'PACKET LENGTH ERROR'
        packet_counter += 1

# end
