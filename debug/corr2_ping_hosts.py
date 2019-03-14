#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ping a list of hosts by connecting to them.

@author: paulp
"""
import time
import argparse

from casperfpga import utils as fpgautils
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Ping a list of hosts by connecting to them.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store',
                    default='', help='comma-delimited list of hosts')
parser.add_argument('--config', type=str, action='store', default='', help=
                    'corr2 config file. (default: Use CORR2INI env var)')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, '
                         'DEBUG, ERROR')
args = parser.parse_args()

raise RuntimeError('Not working with Skarabs yet.')

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)


def pingfpga(fpga):
    timeout = 0.5
    stime = time.time()
    while (not fpga.is_connected()) and (time.time() - stime < timeout):
        time.sleep(0.1)
        fpga.connect()
    if not fpga.is_connected():
        return 'unavailable'
    try:
        fpga.test_connection()
        return 'programmed'
    except:
        return 'connected'

# create the devices and connect to them
fpgas = utils.script_get_fpgas(args)

# ping them
connected = []
programmed = []
unavailable = []
responses = fpgautils.threaded_fpga_operation(fpgas, 10, pingfpga)
for host, response in responses.items():
    if response == 'unavailable':
        unavailable.append(host)
    elif response == 'programmed':
        programmed.append(host)
    elif response == 'connected':
        connected.append(host)

fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')

sconn = set(connected)
sprog = set(programmed)
connected = list(sconn.difference(sprog))
print('%d hosts:' % len(fpgas))
print('\tProgrammed: %s' % programmed)
print('\tConnected: %s' % connected)
print('\tUnavailable: %s' % unavailable)

# end
