#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Plot the spectrum using the 40G core's TX snapshots on the F-engine
"""
import argparse

from casperfpga import spead as casperspead
from casperfpga import snap as caspersnap
from casperfpga.network import IpAddress
from casperfpga.memory import bin2fp
from matplotlib import pyplot
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Plot the spectrum using the output snapshots on the F-engine.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    dest='host', type=str, action='store', default='',
    help='the F-engine host to query, if an int, will be taken positionally '
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

# make the FPGA
fpga = utils.feng_script_get_fpga(args)

# read the config
config = utils.parse_ini_file(args.config)
n_chans = int(config['fengine']['n_chans'])
n_xhost = len(config['xengine']['hosts'].split(','))
x_per_host = int(config['xengine']['x_per_fpga'])
NUM_FREQ = n_chans
FREQS_PER_X = NUM_FREQ / (n_xhost * x_per_host)
EXPECTED_PKT_LEN = 128 + 12

ips_and_freqs = {}
spectrum_total = [[0] * NUM_FREQ, [0] * NUM_FREQ]
spectrum_count = [[0] * NUM_FREQ, [0] * NUM_FREQ]


def print_ips():
    print 'Unique frequencies received for each destination IP address:'
    for ipint in ips_and_freqs:
        numfreqs = len(ips_and_freqs[ipint])
        print('{ip}: {numfreq}'.format(ip=str(IpAddress(ipint)),
                                       numfreq=numfreqs))
    print("********** - press ctrl-c to quit and plot what we've received so far, or wait for %i fchans on each IP address." % FREQS_PER_X)


def b2fp(dword):
    r1 = (dword >> 8) & 0xff
    i1 = (dword >> 0) & 0xff
    r1 = bin2fp(r1, 8, 7, True)
    i1 = bin2fp(i1, 8, 7, True)
    return r1**2 + i1**2


allfreqs = {}
gbe = fpga.gbes.keys()[0]
gbe = fpga.gbes[gbe]

while True:
    try:
        coredata = gbe.read_txsnap()
        #for n in range(10):
        #    print '%016X'%coredata['data'][n]
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

        # for pkt in spead_processor.packets:
        #     freq = pkt.headers[0x4103]
        #     # print pkt.headers
        #     if freq not in allfreqs:
        #         allfreqs[freq] = 1
        # print allfreqs.keys()

        for pkt in spead_processor.packets:
            if pkt.ip not in ips_and_freqs:
                ips_and_freqs[pkt.ip] = []
            freq_base = pkt.headers[0x4103]
            freq_offset = pkt.headers[0x0003]>>(8-1+3)
            timestamp = pkt.headers[0x1600]
            freq = freq_base + freq_offset
            #print 'Got freq %i.'%freq
            #print 'offset: ',freq_offset
            #print 'time %i, freq: %i '%(timestamp,freq)
            if freq not in ips_and_freqs[pkt.ip]:
                ips_and_freqs[pkt.ip].append(freq)
            ips_and_freqs[pkt.ip].sort()
            pkt_words = 0
            for data in pkt.data:
                pwr = [b2fp((data >> 48) & 0xffff),
                       b2fp((data >> 32) & 0xffff),
                       b2fp((data >> 16) & 0xffff),
                       b2fp((data >> 0)  & 0xffff)]
                #print('freq({})'.format(freq))
                #for p in pwr:
                #    print('\t{}'.format(p))
                #print('')
                # if (pwr1 != 0) or (pwr3 != 0):
                #     raise RuntimeError('pol1 isnt zero?')
                spectrum_total[0][freq] += (pwr[0] + pwr[2])
                spectrum_count[0][freq] += 2
                spectrum_total[1][freq] += (pwr[1] + pwr[3])
                spectrum_count[1][freq] += 2
                pkt_words += 2
            if pkt_words != 256:
                print('WARNING: packet for freq(%i) had %i words?' %
                      (freq, pkt_words))
        print_ips()
        all_freqs = True
        for ipint in ips_and_freqs:
            if len(ips_and_freqs[ipint]) < FREQS_PER_X:
                all_freqs = False
                break
        if all_freqs:
            print('Got all frequencies for each IP.')
            break
    except KeyboardInterrupt:
        break

avg_spectrum = [[0] * NUM_FREQ, [0] * NUM_FREQ]
for pol in [0, 1]:
    for freq in range(0, NUM_FREQ):
        if spectrum_count[pol][freq] > 0:
            val = spectrum_total[pol][freq] / spectrum_count[pol][freq]
        else:
            val = 0
        avg_spectrum[pol][freq] = val

#import IPython
#IPython.embed()

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
