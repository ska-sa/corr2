#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
@author: paulp
"""
import argparse


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
fpga = HOSTCLASS(args.host)
fpga.get_system_information()

#snapdata = fpga.snapshots.unpack_output_ss.read(man_trig=True, man_valid=True)['data']
snapdata = fpga.snapshots.unpack_output_ss.read(man_valid=True)['data']

#snapdata = fpga.snapshots.syncgen_output_ss.read()['data']

for ctr in range(0, len(snapdata['dv'])):
    for key in snapdata.keys():
        print('%s(%d)\t' % (key, snapdata[key][ctr]),
    print(''

# handle exits cleanly
fpga.disconnect()
# end
