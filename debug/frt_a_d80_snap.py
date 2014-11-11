#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
@author: paulp
"""
import sys
import signal
import argparse

from casperfpga import katcp_fpga
from casperfpga import dcp_fpga

parser = argparse.ArgumentParser(description='Read raw incoming data on the f-engines.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store',
                    help='f-engine host')
parser.add_argument('--eof', dest='eof', action='store_true',
                    default=False,
                    help='show only eofs')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
parser.add_argument('--verbose', dest='verbose', action='store_true', default=False,
                    help='Be verbose!')
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
fpga = HOSTCLASS(args.host)
fpga.get_system_information()


def exit_gracefully(signal, frame):
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

while True:
    # arm them
    fpga.snapshots.p0_data_ss.arm()
    fpga.snapshots.p1_data_ss.arm()

    # trigger them snap
    fpga.registers.control.write(unpack_arm='pulse')

    # read the snaps without arming them
    p0d = fpga.snapshots.p0_data_ss.read(arm=False)
    p1d = fpga.snapshots.p1_data_ss.read(arm=False)

    time_msb = p0d['extra_value']['data']['time36_msb']
    time_lsb = p1d['extra_value']['data']['time36_lsb']
    time36 = (time_msb << 4) | time_lsb
    p0d = p0d['data']
    p0d.update(p1d['data'])

    p0time_from_data = p0d['p0_80'][0] >> 44
    if not p0time_from_data == time36:
        print 'ERROR: timestamp does NOT match tvg time in the data! %d != %d' % (p0d['p0_80'][0], time36)
    else:
        print 'Time matches okay - %d.' % time36

    if args.verbose:
        for ctr in range(0, len(p0d['p0_80'])):
            print ctr, ':',
            for key in p0d.keys():
                if key == 'p0_80':
                    print '%s(%d)\t' % (key, p0d[key][ctr] >> 44),
                else:
                    print '%s(%d)\t' % (key, p0d[key][ctr]),
            print ''

fpga.disconnect()
# end
