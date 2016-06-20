#!/usr/bin/env python
"""
Program one or more ROACHs.

@author: paulp
"""
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Program one or more CASPER devices',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument(
    '--dnsmasq', dest='dnsmasq', action='store_true', default=False,
    help='search for roach hostnames in /var/lib/misc/dnsmasq.leases')
parser.add_argument(
    '--comms', dest='comms', action='store', default='katcp', type=str,
    help='katcp (default) or dcp?')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
parser.add_argument(
    dest='fpg', action='store', default='',
    help='.fpg file to program')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

# look for hosts in the leases file
if args.dnsmasq:
    hosts, lease_filename = utils.hosts_from_dhcp_leases()
    print 'Found %i roaches in %s.' % (len(hosts), lease_filename)
    for host in hosts:
        print '\t', host
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

# create the devices and program them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(katcp_fpga.KatcpFpga, hosts)
running = fpgautils.threaded_fpga_function(fpgas, 10, 'is_running')
fpgautils.threaded_fpga_function(fpgas, 10,
                                 'upload_to_ram_and_program', args.fpg)
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')

# end
