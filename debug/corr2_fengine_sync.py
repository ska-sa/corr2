#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given xengine.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""

from __future__ import print_function
import time
import argparse

from casperfpga import utils as fpgautils
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Sync MeerKAT F-engines.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument(
    '--retry', dest='retry', action='store', default=10, type=int,
    help='how many times should we try to sync?')
parser.add_argument(
    '--force', dest='force', action='store_true', default=False,
    help='force a sync even if they are already synced')
parser.add_argument(
    '--checkonly', dest='checkonly', action='store_true', default=False,
    help='check sync only, do not try to sync')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

# make the fpgas
fpgas = utils.feng_script_get_fpgas(args)


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
print('Current F-engine sync times:')
for host, synctime in times.items():
    print('\t%s: %i' % (host, synctime))

if ((not synced) or args.force) and (not args.checkonly):
    # sync the F-engines
    tries = 0
    while tries < args.retry:
        print('Syncing...', end='')
        fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(sys_rst='pulse'))
        print('checking...', end='')
        time.sleep(1)
        synced, times = check_sync(fpgas)
        if synced:
            print('done. Synced at %d.' % times[times.keys()[0]])
            break
        print('failed. Trying again. %s' % times)
    if tries == args.retry:
        if args.log_level != '':
            logging.error('FAILED to sync!')
        print('FAILED to sync!')

fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
