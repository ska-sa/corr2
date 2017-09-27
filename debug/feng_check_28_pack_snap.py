#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given xengine.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import argparse


parser = argparse.ArgumentParser(
    description='Read a post-pack snapshot from an fengine.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='the host from which to read')
parser.add_argument(
    '--wesel', dest='wesel', action='store', type=int, default=0,
    help='write-enable select: 0 for window start, 1 for data_valid to SPEAD')
parser.add_argument(
    '--offset', dest='offset', action='store', type=int, default=-1,
    help='apply a read offset to the snapshot')
parser.add_argument(
    '--timestep', dest='timestep', action='store_true', default=False,
    help='search for a time boundary crossing')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.timestep and args.wesel==0:
    raise RuntimeError('Waiting for a timestep and write-enable '
                       'on window start does not make sense.')

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

# create the devices and connect to them
fpga = HOSTCLASS(args.host)
fpga.get_system_information()
if 'wintime_snap_ss' not in fpga.snapshots.names():
    print(fpga.snapshots
    fpga.disconnect()
    raise RuntimeError('The host %s does not have the necessary snapshot, %s.' % (fpga.host, 'wintime_snap_ss'))

fpga.registers.control.write(wintime_snap_wesel=args.wesel)
got_time_step = False
while (args.timestep and (not got_time_step)) or (not args.timestep):
    snapdata = fpga.snapshots.wintime_snap_ss.read(offset=args.offset)['data']
    lasttime = snapdata['time36'][0]
    lastfreq_ctr = -1
    lastfreq = snapdata['freqid0'][0] - 128
    for ctr in range(0, len(snapdata['time36'])):
        this_freq = snapdata['freqid0'][ctr]
        this_feng = snapdata['fengid'][ctr]
        this_time = snapdata['time36'][ctr]
        ending = ''
        freqdiff = False
        timediff = False
        if this_freq != lastfreq:
            ending += ' freqdiff(%5d, %5d)' % (this_freq - lastfreq, ctr - lastfreq_ctr)
            lastfreq = this_freq
            lastfreq_ctr = ctr
            freqdiff = True
        if this_time != lasttime:
            ending += ' timediff(%5d)' % (this_time - lasttime)
            timediff = True
            got_time_step = True
        if timediff and not freqdiff:
            if args.wesel == 1:
                ending += ' !!!!!!!!!!!!!!!!!!ERROR!!!!!!!!!!!!!!!!!!!'
            else:
                if this_time - lasttime != 512:  # 2^9 - 2^8 from the corner turn and 2^1 from 4k PFB needing 8k samples
                    ending += ' !!!!!!!!!!!!!!!!!!ERROR!!!!!!!!!!!!!!!!!!!'
        print('%5d: freq(%5d) feng(%3d) time(%15d)%s' % (ctr, this_freq, this_feng, this_time, ending)
        lasttime = this_time
    if not args.timestep:
        break
fpga.disconnect()
# end
