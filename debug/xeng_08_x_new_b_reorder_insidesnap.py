#!/usr/bin/env python
"""
"""
import argparse


parser = argparse.ArgumentParser(description='View the reorder snap block on an x-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store',
                    help='x-engine host')
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
    HOSTCLASS = CasperFpga
else:
    HOSTCLASS = dcp_fpga.DcpFpga

# create the device and connect to it
xeng_fpga = HOSTCLASS(args.host)
xeng_fpga.get_system_information()

snapdata = xeng_fpga.snapshots.snap_inreord0_ss.read(man_valid=True, circular_capture=True)['data']
#snapdata = xeng_fpga.snapshots.snap_inreord0_ss.read(man_valid=True)['data']
#snapdata = xeng_fpga.snapshots.snap_inreord0_ss.read()['data']
snapkeys = snapdata.keys()
snaplen = len(snapdata[snapkeys[0]])
print('Read %d values from snapblock\n' % snaplen
for ctr in range(0, snaplen):
    print('%5d:' % ctr,
    for key in snapkeys:
        if (snapdata['oc_rden'][ctr] == 1) and (snapdata['out_recv'][ctr] == 0):
            missingpainahfuck = True
        else:
            missingpainahfuck = False
        print('%s(%d)  ' % (key, snapdata[key][ctr]),
    print('%s' % 'MISSING PAIN AH FUCK' if missingpainahfuck == True else 'A-OKAY'
print(50 * '*'

xeng_fpga.disconnect()

# end
