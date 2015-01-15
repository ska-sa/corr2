#!/usr/bin/env python
"""
"""
import argparse

from casperfpga import katcp_fpga
from casperfpga import dcp_fpga

parser = argparse.ArgumentParser(description='View the reorder snap block on an x-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store',
                    help='x-engine host')
parser.add_argument('--mantrigger', dest='mantrigger', action='store_true', default=False,
                    help='Trigger all the snap blocks manually, synchronously')
parser.add_argument('--circular', dest='circular', action='store_true', default=False,
                    help='Perform a circular capture, stopping on an error')
parser.add_argument('--offset', dest='offset', action='store', type=int, default=0,
                    help='Capture at this WORD offset')
parser.add_argument('--freqoffset', dest='freqoffset', action='store', type=int, default=0,
                    help='Capture at this FREQ offset')
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
xeng_fpga = HOSTCLASS(args.host)
xeng_fpga.get_system_information()

# get the data
if args.circular:
    xeng_fpga.registers.control.write(reord_snaptrigsel=0)
    # arm
    # for xengctr in range(0, 4):
    for xengctr in range(0, 1):
        for ctr in range(0, 2):
            xeng_fpga.snapshots['snap_reord%d_%d_ss' % (ctr, xengctr)].arm()
    # trigger
    xeng_fpga.registers.control.write(reord_snaptrig='pulse')
    # read
    snapdata = []
    # for xengctr in range(0, 4):
    for xengctr in range(0, 1):
        d0 = xeng_fpga.snapshots['snap_reord%d_0_ss' % xengctr].read(circular_capture=True)['data']
        d1 = xeng_fpga.snapshots['snap_reord%d_0_ss' % xengctr].read(circular_capture=True)['data']
        d0.update(d1)
        snapdata.append(d0)
else:
    if args.mantrigger:
        xeng_fpga.registers.control.write(reord_snaptrigsel=1)
        # arm
        # for xengctr in range(0, 4):
        for xengctr in range(0, 1):
            for ctr in range(0, 2):
                xeng_fpga.snapshots['snap_reord%d_%d_ss' % (ctr, xengctr)].arm()
        # trigger
        xeng_fpga.registers.control.write(reord_snaptrig='pulse')
        # read
        snapdata = []
        for xengctr in range(0, 4):
            d0 = xeng_fpga.snapshots['snap_reord0_%d_ss' % xengctr].read(arm=False)['data']
            d1 = xeng_fpga.snapshots['snap_reord1_%d_ss' % xengctr].read(arm=False)['data']
            d0.update(d1)
            snapdata.append(d0)
    else:
        xeng_fpga.registers.control.write(reord_snaptrigsel=0)
        snapdata = []
        if args.freqoffset > 0:
            off64 = 1024 * 8 * args.freqoffset
            off32 = 1024 * 4 * args.freqoffset
        elif args.offset > 0:
            off64 = 8 * args.freqoffset
            off32 = 4 * args.freqoffset
        else:
            off64 = 0
            off32 = 0
        for xengctr in range(0, 1):
            d0 = xeng_fpga.snapshots['snap_reord0_%d_ss' % xengctr].read(offset=off64)['data']
            d1 = xeng_fpga.snapshots['snap_reord1_%d_ss' % xengctr].read(offset=off32)['data']
            d0.update(d1)
            snapdata.append(d0)

xeng_fpga.disconnect()

# print the results
for snapctr in range(0, 1):
    data = snapdata[snapctr]
    snapkeys = data.keys()
    snaplen = len(data[snapkeys[0]])
    print 'Read %d values from snapblock %d:\n' % (snaplen, snapctr)
    for ctr in range(0, snaplen):
        print '%5d:' % ctr,
        for key in snapkeys:
            print '%s(%d)\t' % (key, data[key][ctr]),
        print ''
    print 50 * '*'

# end
