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
from fpgadevice import tengbe

parser = argparse.ArgumentParser(description='Display information about a MeerKAT digitiser.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hostname', type=str, action='store',
                    help='the hostname of the digitiser')
parser.add_argument('-l', '--listcores', dest='listcores', action='store_true',
                    default=False,
                    help='list cores on this device')
parser.add_argument('-s', '--payloadsize', dest='payloadsize', action='store',
                    default=5120, type=int,
                    help='the 10GBE SPEAD payload size, in bytes')
parser.add_argument('-c', '--core', dest='core', action='store',
                    default='gbe0', type=str,
                    help='the core to query')
args = parser.parse_args()

num_spead_headers = 4
bytes_per_packet = args.payloadsize + (num_spead_headers*8)

# create the device and connect to it
fpga = KatcpClientFpga(args.hostname, 7147)
time.sleep(0.5)
if not fpga.is_connected():
    fpga.connect()
fpga.test_connection()
fpga.get_system_information()

# list the cores we find
if args.listcores:
    numgbes = len(fpga.dev_tengbes)
    print 'Found %i ten gbe core%s:' % (numgbes, '' if numgbes == 1 else 's')
    for core in fpga.dev_tengbes:
        print '\t', core
    fpga.disconnect()
    sys.exit(0)

# read the snap block
coredata = fpga.devices[args.core].read_rxsnap()
for ctr in range(0, len(coredata[coredata.keys()[0]])):
    print '%5d' % ctr,
    key_order = ['led_up', 'led_rx', 'valid_in', 'eof_in', 'bad_frame', 'overrun', 'ip_in', 'data_in']
    for key in key_order:
        if key == 'ip_in':
            print '%s(%s)' % (key, tengbe.ip2str(coredata[key][ctr])), '\t',
        else:
            print '%s(%d)' % (key, coredata[key][ctr]), '\t',
    print ''

# end
