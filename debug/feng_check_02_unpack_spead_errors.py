# -*- coding: utf-8 -*-
"""
Created on Thu May 22 13:35:29 2014

This script pulls a snapshot from the unpack block on the f-engine and examines the spead data inside it
to see if it matches D-engine TVG data.

@author: paulp
"""

import numpy
import argparse
import os

from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(description='Check the SPEAD error counter and valid counter in the '
                                             'unpack section of the F-engines.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
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

if 'CORR2INI' in os.environ.keys() and args.hosts == '':
    args.hosts = os.environ['CORR2INI']
hosts = utils.parse_hosts(args.hosts, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

fpga = HOSTCLASS(hosts[0])
fpga.get_system_information()
snaps = fpga.snapshots.names()
if snaps.count('unpack_spead0_ss') == 0:
    fpga.disconnect()
    raise RuntimeError('The f-engine does not have the required snapshot, unpack_spead0_ss, compiled into it.')

# get the snapshot data from the FPGA.
snapdata = fpga.snapshots.unpack_spead0_ss.read(man_trig=True,circular_capture=True)['data']
fpga.disconnect()

# check the data
lastval = snapdata['dramp'][0] - 1
errors = False
for ctr, val in enumerate(snapdata['dramp']):
    if val == 0:
        if lastval != 511:
            errors = True
            print 'ERROR over rollover at %i'%ctr
    else:
        if val != lastval + 1:
            errors = True
            print 'ERROR in the ramp at %i'%ctr
    lastval = val
if errors:
    print 'DATA RAMP ERRORS ENCOUNTERED'

# check the time and pkt_time
errors = False
for ctr, p in enumerate(snapdata['dtime']):
    if p != snapdata['pkt_time'][ctr]:
        print 'ERROR:', ctr-1, snapdata['dtime'][ctr-1], numpy.binary_repr(snapdata['dtime'][ctr-1]),\
            snapdata['pkt_time'][ctr-1]
        print 'ERROR:', ctr, p, numpy.binary_repr(p), snapdata['pkt_time'][ctr]
        errors = True
if errors:
    print 'TIME vs PKT_TIME ERRORS ENCOUNTERED'

# check the unique times and timestep
errors = False
unique_times = list(numpy.unique(snapdata['pkt_time']))
for ctr, utime in enumerate(unique_times[1:]):
    if utime != unique_times[ctr] + 2:
        print 'ERROR:', ctr, utime, unique_times[ctr-1]
        errors = True
if errors:
    print 'TIMESTEP ERRORS ENCOUNTERED'
