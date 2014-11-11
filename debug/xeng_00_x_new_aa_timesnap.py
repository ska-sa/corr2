#!/usr/bin/env python
"""
"""
import argparse

from casperfpga import katcp_fpga
from casperfpga import dcp_fpga

parser = argparse.ArgumentParser(description='Display reorder preprocess timesnap block - to figure '
                                             'out what timestamps are being used.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store',
                    help='x-engine host')
parser.add_argument('-feng1', dest='feng1', type=str, action='store', default='0,0,17',
                    help='feng_num,freq1,freq2')
parser.add_argument('-feng2', dest='feng2', type=str, action='store', default='1,1,18',
                    help='feng_num,freq1,freq2')
parser.add_argument('-verbose', dest='verbose', action='store_true', default=False,
                    help='Output verbose data')
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

feng1 = [int(f) for f in args.feng1.split(',')]
feng2 = [int(f) for f in args.feng2.split(',')]

# set up the debug
xeng_fpga.registers.snaptime_setup1.write(feng_id1=feng1[0], freq1=feng1[1], freq2=feng1[2],
                                          feng_id2=feng2[0], freq3=feng2[1], freq4=feng2[2])

xeng_fpga.registers.snaptime_setup2.write(feng_id1=feng1[0], freq1=feng1[1], freq2=feng1[2],
                                          feng_id2=feng2[0], freq3=feng2[1], freq4=feng2[2])

# arm the snapblock
xeng_fpga.snapshots.snaptime_x0_f1_fr1_ss.arm()
xeng_fpga.snapshots.snaptime_x0_f1_fr2_ss.arm()
xeng_fpga.snapshots.snaptime_x1_f1_fr1_ss.arm()
xeng_fpga.snapshots.snaptime_x1_f1_fr2_ss.arm()
xeng_fpga.snapshots.snaptime_x2_f1_fr1_ss.arm()
xeng_fpga.snapshots.snaptime_x2_f1_fr2_ss.arm()
xeng_fpga.snapshots.snaptime_x3_f1_fr1_ss.arm()
xeng_fpga.snapshots.snaptime_x3_f1_fr2_ss.arm()

# trigger
xeng_fpga.registers.control.write(snap_trigger='pulse')

# read
snapdata1 = xeng_fpga.snapshots.snaptime_x0_f1_fr1_ss.read(arm=False)['data']['time']
snapdata2 = xeng_fpga.snapshots.snaptime_x0_f1_fr2_ss.read(arm=False)['data']['time']
snapdata3 = xeng_fpga.snapshots.snaptime_x1_f1_fr1_ss.read(arm=False)['data']['time']
snapdata4 = xeng_fpga.snapshots.snaptime_x1_f1_fr2_ss.read(arm=False)['data']['time']
snapdata5 = xeng_fpga.snapshots.snaptime_x2_f1_fr1_ss.read(arm=False)['data']['time']
snapdata6 = xeng_fpga.snapshots.snaptime_x2_f1_fr2_ss.read(arm=False)['data']['time']
snapdata7 = xeng_fpga.snapshots.snaptime_x3_f1_fr1_ss.read(arm=False)['data']['time']
snapdata8 = xeng_fpga.snapshots.snaptime_x3_f1_fr2_ss.read(arm=False)['data']['time']

xeng_fpga.disconnect()

starttime = []
endtime = []
for snapdata in [snapdata1, snapdata2, snapdata3, snapdata4,
                 snapdata5, snapdata6, snapdata7, snapdata8]:
    oldtime = snapdata[0]-1
    oldctr = -128
    starttime.append(oldtime)
    for ctr, newtime in enumerate(snapdata):
        if newtime != oldtime:
            if args.verbose:
                print oldtime,
            assert newtime == oldtime + 1, '%d, %d' % (newtime, oldtime)
            assert ctr == oldctr + 128, '%d, %d' % (ctr, oldctr)
            oldtime = newtime
            oldctr = ctr
    if args.verbose:
        print ''
    endtime.append(oldtime)
    print 'All times increased monotonically. Check the starts and stops across f-engines and frequencies.'
print starttime
print endtime

# end
