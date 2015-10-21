#!/usr/bin/env python

import time
import sys
import logging
import argparse

import dpkt
import bitstring

import numpy as np

from corr2.utils import UnpackDengPacketCapture

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


unpacker = UnpackDengPacketCapture(args.pcap)
_, data = unpacker.decode()

# NM (2015-07-09) Note, numpy.savetxt is horrendously slow, the pandas module
# has much faster csv handling code but I don't want to introduce more
# dependencies just yet
logger.info('Writing csv file')
np.savetxt(args.csv, data, delimiter=',')

