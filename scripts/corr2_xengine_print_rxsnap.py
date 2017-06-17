#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Print the incoming data to an x-engine.
"""
from __future__ import print_function

import sys
import time
import argparse
import signal

from casperfpga import network
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Print the x-engine RX snapshot.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    dest='host', type=str, action='store', default='',
    help='the F-engine host to query, if an int, will be taken positionally '
         'from the config file list of f-hosts')
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument(
    '--bitstream', dest='bitstream', type=str, action='store', default='',
    help='a bitstream for the f-engine hosts (Skarabs need this given '
         'if no config is found)')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='INFO',
    help='log level to use, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

# create the fpgas
fpga = utils.script_get_fpga(args, section='xengine')


def get_fpga_data(fpga):
    # if 'gbe_in_msb_ss' not in fpga.snapshots.names():
    #     return get_fpga_data_new_snaps(fpga)
    control_reg = fpga.registers.gbesnap_control
    control_reg.write(arm=0)
    fpga.snapshots.gbe_in_msb_ss.arm()
    fpga.snapshots.gbe_in_lsb_ss.arm()
    fpga.snapshots.gbe_in_misc_ss.arm()
    control_reg.write(arm=1)
    time.sleep(0.1)
    d = fpga.snapshots.gbe_in_msb_ss.read(arm=False)['data']
    d.update(fpga.snapshots.gbe_in_lsb_ss.read(arm=False)['data'])
    d.update(fpga.snapshots.gbe_in_misc_ss.read(arm=False)['data'])
    control_reg.write(arm=0)
    return d


def print_snap_data(dd):
    data_len = len(dd[dd.keys()[0]])
    for ctr in range(data_len):
        print('%5i' % ctr, end='')
        d64_0 = dd['d_msb'][ctr] >> 64
        d64_1 = dd['d_msb'][ctr] & (2 ** 64 - 1)
        d64_2 = dd['d_lsb'][ctr] >> 64
        d64_3 = dd['d_lsb'][ctr] & (2 ** 64 - 1)
        raw_dv = dd['valid_raw'][ctr]
        eof_str = 'EOF ' if dd['eof'][ctr] == 1 else ''
        badframe_str = 'BAD ' if dd['badframe'][ctr] == 1 else ''
        overrun_str = 'OR ' if dd['overrun'][ctr] == 1 else ''
        src_ip = network.IpAddress(dd['src_ip'][ctr])
        dest_ip = network.IpAddress(dd['dest_ip'][ctr])
        src_ip_str = '%s:%i' % (str(src_ip), dd['src_port'][ctr])
        dest_ip_str = '%s:%i' % (str(dest_ip), dd['dest_port'][ctr])
        print('%20x %20x %20x %20x rawdv(%2i) src(%s) dest(%s) %s%s%s' % (
            d64_0, d64_1, d64_2, d64_3, raw_dv, src_ip_str, dest_ip_str,
            eof_str, badframe_str, overrun_str))


def exit_gracefully(sig, frame):
    print(sig)
    print(frame)
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGHUP, exit_gracefully)

# read and print the data
data = get_fpga_data(fpga)
print_snap_data(data)

exit_gracefully(None, None)

# end
