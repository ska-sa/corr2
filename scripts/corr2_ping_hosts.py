#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ping a list of hosts by connecting to them.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import logging
import time
import argparse
from casperfpga import utils as fpgautils
from corr2 import utils

logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser(description='Ping a list of hosts by connecting to them.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of hosts, or a corr2 config file')
args = parser.parse_args()

hosts = args.hosts.strip().replace(' ', '').split(',')

if len(hosts) == 1:  # check to see it it's a file
    try:
        hostsfromfile = utils.hosts_from_config_file(hosts[0])
        hosts = []
        for hostlist in hostsfromfile.values():
            hosts.extend(hostlist)
    except IOError:
        # it's not a file so carry on
        pass

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

# create the devices and connect to them
print '%d hosts:' % len(hosts)
connected = []
programmed = []
unavailable = []

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(hosts)

responses = fpgautils.threaded_fpga_operation(fpgas, pingfpga, -1)
for host, response in responses.items():
    if response == 'unavailable':
        unavailable.append(host)
    elif response == 'programmed':
        programmed.append(host)
    elif response == 'connected':
        connected.append(host)

# disconnect
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')

sconn = set(connected)
sprog = set(programmed)
connected = list(sconn.difference(sprog))
print '\tProgrammed:', programmed
print '\tConnected:', connected
print '\tUnavailable:', unavailable
