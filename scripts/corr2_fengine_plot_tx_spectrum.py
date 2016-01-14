#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Plot the spectrum using the output snapshots on the f-engine
"""
import argparse
import os
import casperfpga
from casperfpga import spead as casperspead
from casperfpga import snap as caspersnap
from casperfpga import tengbe
from casperfpga.memory import bin2fp
from matplotlib import pyplot
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Plot the spectrum using the output snapshots on the f-engine.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    dest='host', type=str, action='store', default='',
    help='the f-engine host to query, if an int, will be taken positionally '
         'from the config file list of f-hosts')
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument(
    '--linear', dest='linear', action='store_true', default=False,
    help='plot linear, not log')
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

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']
if args.config != '':
    host_list = utils.parse_hosts(args.config, section='fengine')
else:
    host_list = []

try:
    hostname = host_list[int(args.host)]
    logging.info('Got hostname %s from config file.' % hostname)
except ValueError:
    hostname = args.host

f = casperfpga.KatcpFpga(hostname)
f.get_system_information()

FREQS_PER_X = 128
NUM_FREQ = 4096
EXPECTED_PKT_LEN = 128 + 10

ips_and_freqs = {}
spectrum_total = [[0] * NUM_FREQ, [0] * NUM_FREQ]
spectrum_count = [[0] * NUM_FREQ, [0] * NUM_FREQ]


def print_ips():
    for ipint in ips_and_freqs:
        print str(tengbe.IpAddress(ipint)), ':', len(ips_and_freqs[ipint])
    print '**********'


def b2fp(dword):
    r1 = (dword >> 8) & 0xff
    i1 = (dword >> 0) & 0xff
    r1 = bin2fp(r1, 8, 7, True)
    i1 = bin2fp(i1, 8, 7, True)
    v1 = r1**2 + i1**2
    return v1


while True:
    try:
        for ctr in range(4):
            coredata = f.snapshots['gbe%i_txs_ss' % ctr].read()['data']

            spead_processor = casperspead.SpeadProcessor(None, None, None, None)
            gbe_packets = caspersnap.Snap.packetise_snapdata(coredata, 'eof')
            gbe_data = []
            for pkt in gbe_packets:
                # check that the IP is consistent within the packet
                first_ip = pkt['ip'][0]
                for ip in pkt['ip']:
                    assert ip == first_ip

                # check the length of the packet
                if (EXPECTED_PKT_LEN > -1) and \
                        (len(pkt['data']) != EXPECTED_PKT_LEN):
                    raise RuntimeError(
                        'Gbe packet not correct length - should be {}. is '
                        '{}'.format(EXPECTED_PKT_LEN, len(pkt['data'])))

                # add the packet's contents to the list of data packets
                gbe_data.append({'data': pkt['data'], 'ip': first_ip})

            # ask the SPEAD processor to turn the GBE packets into SPEAD packets
            spead_processor.process_data(gbe_data)

            for pkt in spead_processor.packets:
                if pkt.ip not in ips_and_freqs:
                    ips_and_freqs[pkt.ip] = []
                freq = pkt.headers[0x4103]
                if freq not in ips_and_freqs[pkt.ip]:
                    ips_and_freqs[pkt.ip].append(freq)
                ips_and_freqs[pkt.ip].sort()

                for data in pkt.data:
                    v0 = b2fp((data >> 48) & 65535)
                    v1 = b2fp((data >> 32) & 65535)
                    v2 = b2fp((data >> 16) & 65535)
                    v3 = b2fp((data >> 0) & 65535)

                    spectrum_total[0][freq] += (v0 + v2)
                    spectrum_count[0][freq] += 2

                    spectrum_total[1][freq] += (v1 + v3)
                    spectrum_count[1][freq] += 2

            print_ips()

        all_freqs = True
        for ipint in ips_and_freqs:
            if len(ips_and_freqs[ipint]) != FREQS_PER_X:
                all_freqs = False
                break
        if all_freqs:
            print 'Got all frequencies for each IP.'
            break
    except KeyboardInterrupt:
        break

avg_spectrum = [[], []]
for freq in range(0, NUM_FREQ):
    for pol in [0, 1]:
        if spectrum_count[pol][freq] > 0:
            val = spectrum_total[pol][freq]
        else:
            val = 0
        avg_spectrum[pol].append(val)

pyplot.subplot(2, 1, 1)
if args.linear:
    pyplot.plot(avg_spectrum[0])
else:
    pyplot.semilogy(avg_spectrum[0])
pyplot.subplot(2, 1, 2)
if args.linear:
    pyplot.plot(avg_spectrum[1])
else:
    pyplot.semilogy(avg_spectrum[1])
pyplot.show()
