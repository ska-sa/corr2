#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Collect the output of a post-unpack snapshot and do an FFT on it.

@author: paulp
"""
import argparse
import sys
import signal

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(description='Display a histogram of the post-coarse delay data.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store',
                    help='le host de fengine')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
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

hosts = utils.parse_hosts(args.host, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

def exit_gracefully(signal, frame):
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
snapshot_missing = []
for fpga_ in fpgas:
    if not 'snapcoarse_0_ss' in fpga_.snapshots.names():
        snapshot_missing.append(fpga_.host)
if len(snapshot_missing) > 0:
    print 'The following hosts are missing the post-unpack snapshot. Bailing.'
    print snapshot_missing
    exit_gracefully(None, None)


def get_data():
    # arm the snaps
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots.snapcoarse_0_ss.arm())
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots.snapcoarse_1_ss.arm())

    # allow them to trigger
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(snapcoarse_arm='pulse'))

    # read the data
    snapdata_p0 = fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots.snapcoarse_0_ss.read(arm=False))
    snapdata_p1 = fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots.snapcoarse_1_ss.read(arm=False))

    try:
        for key, value in snapdata_p0.items():
            if 'data' not in value.keys():
                raise RuntimeError('Did not get p0 snap data from host %s' % key)
    except:
        print snapdata_p0
        raise RuntimeError('Error getting p0 snap data')
    try:
        for key, value in snapdata_p1.items():
            if 'data' not in value.keys():
                raise RuntimeError('Did not get p1 snap data from host %s' % key)
    except:
        print snapdata_p1
        raise RuntimeError('Error getting p1 snap data')

    # unpack the data and the timestamps
    unpacked_data = {}
    for fpga in snapdata_p0.keys():
        unpacked_data[fpga] = {}
        p0_data = snapdata_p0[fpga]
        p1_data = snapdata_p1[fpga]
        packettime = (p0_data['extra_value']['data']['time36_msb'] << 4) | p1_data['extra_value']['data']['time36_lsb']
        unpacked_data[fpga]['packettime36'] = packettime
        unpacked_data[fpga]['packettime48'] = packettime << 12
        p0_unpacked = []
        p1_unpacked = []
        for ctr, dataword in enumerate(p0_data['data']['p0_80']):
            p0_80 = p0_data['data']['p0_80'][ctr]
            p1_80 = (p0_data['data']['p1_80_msb'][ctr] << 32) | p1_data['data']['p1_80_lsb'][ctr]
            p0_unpacked.append(p0_80)
            p1_unpacked.append(p1_80)
        unpacked_data[fpga]['p0'] = p0_unpacked[:]
        unpacked_data[fpga]['p1'] = p1_unpacked[:]
    return unpacked_data

import matplotlib.pyplot as pyplot
from casperfpga.memory import bin2fp
def eighty_to_ten(eighty):
    samples = []
    for offset in range(70, -1, -10):
        binnum = (eighty >> offset) & 0x3ff
        samples.append(bin2fp(binnum, 10, 9, True))
    return samples

pyplot.interactive(True)
while True:
    unpacked_data = get_data()
    for fpga, fpga_data in unpacked_data.items():
        print '%s data started at %d' % (fpga, fpga_data['packettime48']),
        # for pol_data in [(fpga_data['p0'], 0), (fpga_data['p1'], 1)]:
        for pol_data in [(fpga_data['p1'], 1)]:
            allsamples = []
            for dataword in pol_data[0]:
                samples = eighty_to_ten(dataword)
                allsamples.extend(samples)
            pyplot.cla()
            pyplot.hist(allsamples, 1024, (-0.5, 0.5))
            pyplot.draw()
        print 'and ended %d samples later. All okay.' % (len(allsamples))

# and exit
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')

# end
