#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
@author: paulp
"""
import logging
import argparse

logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.INFO)

from casperfpga.katcp_fpga import KatcpFpga

parser = argparse.ArgumentParser(description='Display reorder preprocess snapblock info.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store',
                    help='x-engine host')
parser.add_argument('--eof', dest='eof', action='store_true',
                    default=False,
                    help='show only eofs')
args = parser.parse_args()

xeng_host = args.host

# create the device and connect to it
xeng_fpga = KatcpFpga(xeng_host)
xeng_fpga.get_system_information()
board_id = xeng_fpga.registers.board_id.read()['data']['reg']
numchans = 4096
numx = 32
fperx = numchans / numx
frange = []
for bid in range(board_id, board_id + 4):
    fmin = bid * fperx
    fmax = fmin + fperx - 1
    frange.append((fmin, fmax))
print frange
snapdata = []
snapdata.append(xeng_fpga.snapshots.snap_unpack0_ss.read()['data'])
snapdata.append(xeng_fpga.snapshots.snap_unpack1_ss.read()['data'])
snapdata.append(xeng_fpga.snapshots.snap_unpack2_ss.read()['data'])
snapdata.append(xeng_fpga.snapshots.snap_unpack3_ss.read()['data'])
for ctr in range(0, len(snapdata[0]['eof'])):
    if (snapdata[0]['eof'][ctr] == 1) or (not args.eof):
        for bid, snap in enumerate(snapdata):
            assert snap['freq'][ctr] >= frange[bid][0]
            assert snap['freq'][ctr] <= frange[bid][1]
            print 'valid(%i) fengid(%i) eof(%i) freq(%i) time(%i) |' % (
                snap['valid'][ctr],
                snap['feng_id'][ctr],
                snap['eof'][ctr],
                snap['freq'][ctr],
                snap['time'][ctr], ),
        print ''

# handle exits cleanly
xeng_fpga.disconnect()
# end
