#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given xengine.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import time
import argparse

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(description='Sync MeerKAT f-engines.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument('--retry', dest='retry', action='store', default=10, type=int,
                    help='how many times should we try to sync?')
parser.add_argument('--noforce', dest='noforce', action='store_true', default=False,
                    help='force a sync even if they are already synced')
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

hosts = utils.parse_hosts(args.hosts, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 10, 'get_system_information')


def get_sync(fpga):
    temp1 = fpga.registers.sync_timestamp_msw.read()['data']['reg']
    temp2 = fpga.registers.sync_timestamp_lsw.read()['data']['time_lsw']
    return (temp1 << 4) | (temp2 & 0x0f)


def check_sync(all_fpgas):
    synctimes = fpgautils.threaded_fpga_operation(all_fpgas, 10, get_sync)
    if args.log_level != '':
        logging.info(synctimes)
    synctime = synctimes[synctimes.keys()[0]]
    for stime in synctimes.values():
        if stime != synctime:
            return False, synctimes
    return True, synctimes

# check the current sync times
synced, times = check_sync(fpgas)
if synced and args.noforce:
    print 'All fengines synced at %d.' % times[times.keys()[0]]
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')

# sync the f-engines
tries = 0
while tries < args.retry:
    print 'Syncing...',
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(sys_rst='pulse'))
    print 'checking...',
    time.sleep(1)
    synced, times = check_sync(fpgas)
    if synced:
        print 'done. Synced at %d.' % times[times.keys()[0]]
        break
    print 'failed. Trying again.', times
if tries == args.retry:
    if args.log_level != '':
        logging.error('FAILED to sync!')
    print 'FAILED to sync!'

fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
