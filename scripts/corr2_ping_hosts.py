#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ping a list of hosts by connecting to them.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import time
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(description='Ping a list of hosts by connecting to them.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, or a corr2 config file')
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
hosts = utils.parse_hosts(args.hosts)
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')


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

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)

# ping them
connected = []
programmed = []
unavailable = []
responses = fpgautils.threaded_fpga_operation(fpgas, pingfpga)
for host, response in responses.items():
    if response == 'unavailable':
        unavailable.append(host)
    elif response == 'programmed':
        programmed.append(host)
    elif response == 'connected':
        connected.append(host)

fpgautils.threaded_fpga_function(fpgas, 'disconnect')

sconn = set(connected)
sprog = set(programmed)
connected = list(sconn.difference(sprog))
print '%d hosts:' % len(hosts)
print '\tProgrammed:', programmed
print '\tConnected:', connected
print '\tUnavailable:', unavailable

# end
