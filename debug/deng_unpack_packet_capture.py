#!/usr/bin/env python

import time
import sys
import logging
import argparse

import dpkt
import bitstring

import numpy as np

from corr2.utils import AdcData

logger = logging.getLogger()

parser = argparse.ArgumentParser(
    description="""
    Unpack a raw digitiser SPEAD stream to adc samples. Assumes that all the
    packets are for a single polarisation.

    Capture packets using a standard packet capture tool. You need to ensure
    that your capture solution is fast enough to keep up! You also need to
    ensure that the digitiser is set up to transmit it's data to the machine and
    interface used to capture the packets, or if multicast is used you must
    ensure that the capture interface is subscribed to the multicast group in
    question. Also make sure only one polarisation is directed at the capture
    machine.

    An example using the fake digitiser's "pulse" mode and wireshark's dumpcap
    tool. Assuming you are capturing polarisation 0. Also assumes the
    environment variable CORR2INI is set to a configuration file with a
    [dsimengine] section that configures the fake digitiser to send the pol0
    data to the capture machine interface and 10gbe_port = 8888. Assumes that
    the capture interface is "eth2" You'll need two separate shell sessions:

    (shell 1) $ corr2_dsim_control --program
    (shell 1) $ corr2_dsim_control --sine-source 0 0.5 100e6 --output-type 0 signal \\
                   --output-scale 0 0.5
    (shell 2) $ dumpcap -P -i eth2 -B 100 -f 'udp port 8888' -w digitiser.pcap
    (shell 1) $ corr2_dsim_control --resync --pulse
    (shell 2) Push ctrl-C
    (shell 2) $ deng_unpack_packet_capture.py digitiser.pcap output.csv
    """,

    formatter_class=argparse.RawDescriptionHelpFormatter
    )

parser.add_argument(dest='pcap', type=str, action='store',
                    help='Name of pcap file with captured digitiser packets. '
                    'Expected in libpcap, not pcap-ng format. Your packet '
                    'capture tool might need command line parameters to force '
                    'this.')
parser.add_argument(dest='csv', type=str, action='store',
                    help='Name of output csv file with sample data.')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')

args = parser.parse_args()

if args.log_level != '':
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)


header_list = ['HEAP ID','HEAP Size','HEAP Offset','HEAP Payload','Timestamp',
               'Digitiser ID','Digitiser Status','Reserved']

pcap_reader = dpkt.pcap.Reader(open(args.pcap))
data_blocks = {}                # Data blocks keyed by timestamp

for i, (ts, pkt) in enumerate(pcap_reader):
    # WARNING (NM, 2015-05-29): Stuff stolen from simonr, now idea how he determined the
    # various hard-coded constants below, though I assume it involved studying the
    # structure of a SPEAD packet.
    enc = pkt.encode('hex_codec')
    header_line = enc[84:228]
    bs = bitstring.BitString(hex='0x' + header_line[22:32])
    timestamp = bs.unpack('uint:40')[0]
    data_line = enc[228:]
    if len(data_line) != 10240:
        print "Error reading packet for ts {}. Expected 10240 but got {}.".format(
            timestamp, len(data_line))
        continue

    datalist = []
    for x in range(0, len(data_line),16):
        datalist.append(int(data_line[x:x+16], 16))
    words80 = AdcData.sixty_four_to_eighty(datalist)
    words10 = AdcData.eighty_to_ten(words80)

    assert timestamp not in data_blocks
    data_blocks[timestamp] = words10

print "Packets decoded"
sorted_time_keys = np.array(sorted(data_blocks.keys()))
data = np.hstack(data_blocks[ts] for ts in sorted_time_keys)
print "Data shuffled"
samples_per_pkt = 4096
time_jumps = sorted_time_keys[1:] - sorted_time_keys[:-1]

if not np.all(time_jumps == samples_per_pkt):
    print "It looks like gaps exist in captured data -- were packets dropped?"

print 'Data checked'

# NM (2015-07-09) Note, numpy.savetxt is horrendously slow, the pandas module
# has much faster csv handling code but I don't want to introduce more
# dependencies just yet
np.savetxt(args.csv, data, delimiter=',')

