# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given digitiser.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys, logging, time, argparse

sys.path.insert(0, '/home/paulp/code/corr2.github/src')
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from katcp_client_fpga import KatcpClientFpga

parser = argparse.ArgumentParser(description='Print any snapblock(s) on a FPGA.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hostname', type=str, action='store',
                    help='the hostname of the digitiser')
parser.add_argument('-l', '--listsnaps', dest='listsnaps', action='store_true',
                    default=False,
                    help='list snap blocks on this device')
parser.add_argument('-n', '--numrows', dest='numrows', action='store',
                    default=-1, type=int,
                    help='the number of rows to print, -1 for all')
parser.add_argument('-s', '--snap', dest='snap', action='store',
                    default='', type=str,
                    help='the snap to query, all for ALL of them!')
args = parser.parse_args()

# create the device and connect to it
fpga = KatcpClientFpga(args.hostname, 7147)
time.sleep(0.2)
if not fpga.is_connected():
    fpga.connect()
fpga.test_connection()
fpga.get_system_information()

# list the cores we find
if args.listsnaps:
    numsnaps = len(fpga.dev_snapshots)
    print 'Found %i snapshot%s:' % (numsnaps, '' if numsnaps == 1 else 's')
    for snap in fpga.dev_snapshots:
        print '\t', snap
    fpga.disconnect()
    sys.exit(0)

# read the snap block
snapdata = fpga.devices[args.snap].read(man_valid=True, man_trig=True)
for ctr in range(0, len(snapdata[snapdata.keys()[0]])):
    print '%5d' % ctr,
    for key in snapdata.keys():
        print '%s(%d)' % (key, snapdata[key][ctr]), '\t',
    print ''
    if ctr == args.numrows:
        break

fpga.disconnect()
# end
