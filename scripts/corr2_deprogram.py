#!/usr/bin/env python
"""
Deprogram one or more ROACHs.

@author: paulp
"""
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(description='Deprogram one or more CASPER devices',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument('--class', dest='hclass', action='store', default='',
                    help='start/stop a class: fengine or xengine')
parser.add_argument('--dnsmasq', dest='dnsmasq', action='store_true', default=False,
                    help='search for roach hostnames in /var/lib/misc/dnsmasq.leases')
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

# look for hosts in the leases file
if args.dnsmasq:
    hosts = []
    masqfile = open('/var/lib/misc/dnsmasq.leases')
    for line in masqfile:
        if line.find('roach') > 0:
            roachname = line[line.find('roach'):line.find(' ', line.find('roach') + 1)].strip()
            hosts.append(roachname)
    masqfile.close()
    print 'Found %i roaches in dnsmasq.leases.' % len(hosts)
    # for host in hosts:
    #     print '\t', host
    # hosts = []
else:
    # are we doing it by class?
    if 'CORR2INI' in os.environ.keys() and args.hosts == '':
        args.hosts = os.environ['CORR2INI']
    if args.hclass != '':
        if args.hclass == 'fengine':
            hosts = utils.parse_hosts(args.hosts, section='fengine')
        elif args.hclass == 'xengine':
            hosts = utils.parse_hosts(args.hosts, section='xengine')
        else:
            raise RuntimeError('No such host class: %s' % args.hclass)
    else:
        hosts = utils.parse_hosts(args.hosts)

if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# create the devices and deprogram them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
running = fpgautils.threaded_fpga_function(fpgas, 10, 'is_running')
deprogrammed = []
already_deprogrammed = []
for fpga in fpgas:
    if running[fpga.host]:
        fpga.deprogram()
        deprogrammed.append(fpga.host)
    else:
        already_deprogrammed.append(fpga.host)
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
if len(deprogrammed) != 0:
    print deprogrammed, ': deprogrammed okay.'
if len(already_deprogrammed) != 0:
    print already_deprogrammed, ': already deprogrammed.'
# end