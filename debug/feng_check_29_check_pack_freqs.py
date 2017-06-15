#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given xengine.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys
import argparse

from corr2 import utils

parser = argparse.ArgumentParser(description='Read a post-pack snapshot from an fengine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store',
                    help='the host from which to read')
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging. %s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if args.comms == 'katcp':
    HOSTCLASS = CasperFpga
else:
    HOSTCLASS = dcp_fpga.DcpFpga

# read the config
config = utils.parse_ini_file(args.config)

EXPECTED_FREQS = int(config['fengine']['n_chans'])

# create the devices and connect to them
fpga = HOSTCLASS(args.host)
fpga.get_system_information()
if 'wintime_snap_ss' not in fpga.snapshots.names():
    print(fpga.snapshots
    fpga.disconnect()
    raise RuntimeError('The host %s does not have the necessary snapshot, %s.' % (fpga.host, 'wintime_snap_ss'))

fpga.registers.control.write(wintime_snap_wesel=1)

import signal
def signal_handler(sig, frame):
    print(sig, frame
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)

# determine the snap length
snapdata = fpga.snapshots.wintime_snap_ss.read(offset=0)['data']
SNAPLEN = len(snapdata['freqid0'])  # 64-bit (8-byte) words

successes = 0
while True:
    WORDS_PER_FREQ = 256 / 2
    freqs_per_snap = SNAPLEN / WORDS_PER_FREQ
    freqs_per_link = EXPECTED_FREQS / 4
    iterations = freqs_per_link / freqs_per_snap
    expected_freqs = []
    for ctr in range(0, 128, 4):
        a = range(ctr, EXPECTED_FREQS, WORDS_PER_FREQ)
        expected_freqs.extend(a)
    for ctr in range(0, iterations):
        offset = ctr * SNAPLEN * 8
        freq_offset = ctr * freqs_per_snap
        snapdata = fpga.snapshots.wintime_snap_ss.read(offset=offset)['data']
        print('Read snapshot at offset %d.' % offset
        sys.stdout.flush()
        # want WORDS_PER_FREQ of every channel
        target_freq = -1
        for wordctr in range(0, len(snapdata['time36'])):
            if wordctr % WORDS_PER_FREQ == 0:
                target_freq += 1
            this_freq = snapdata['freqid0'][wordctr]
            this_feng = snapdata['fengid'][wordctr]
            this_time = snapdata['time36'][wordctr]
            if this_freq != expected_freqs[freq_offset + target_freq]:
                print(50*'#'
                print('Iteration ctr:', ctr
                print('Read offset:', offset
                print('Freq offset:', freq_offset
                print('Word ctr:', wordctr
                print('Snap freq:', this_freq
                print('Expected freq:', expected_freqs[freq_offset + target_freq]
                print('Target freq', target_freq
                print(expected_freqs
                print(50*'#'
                raise RuntimeError('Something was wrong. Check the debug data above.')
    successes += 1
    print('Run %d passes okay.' % successes
    sys.stdout.flush()

fpga.disconnect()
