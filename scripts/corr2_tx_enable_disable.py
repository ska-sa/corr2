#!/usr/bin/env python
"""
Enable or disable transmission from one or more ROACHs.

@author: paulp
"""
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Enable or disable 10gbe transmission on a CASPER device',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument(
    '--class', dest='hclass', action='store', default='',
    help='enable/disable a class: fengine or xengine')
parser.add_argument(
    '--enable', dest='enable', action='store_true', default=False,
    help='enable TX')
parser.add_argument(
    '--disable', dest='disable', action='store_true', default=False,
    help='disable TX')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
parser.add_argument(
    '--listhosts', dest='listhosts', action='store_true', default=False,
    help='list hosts and exit')
args = parser.parse_args()

if args.log_level:
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=getattr(logging, log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

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

if args.listhosts:
    print hosts
    import sys
    sys.exit(0)

if not (args.disable or args.enable):
    print 'Cowardly refusing to do nothing!'
    import sys
    sys.exit(0)

# create the devices and enable/disable tx
fpgas = fpgautils.threaded_create_fpgas_from_hosts(katcp_fpga.KatcpFpga, hosts)
fpgautils.threaded_fpga_function(fpgas, 10, 'get_system_information')


def enable_disable(endisable):
    print '%s tx on all hosts' % ('Enabling' if endisable else 'Disabling')
    if fpgas[0].registers.names().count('control') > 0:
        if fpgas[0].registers.control.field_names().count('gbe_out_en') > 0:
            print '\tProduction control registers found.'
            fpgautils.threaded_fpga_operation(
                fpgas, 10,
                lambda fpga: fpga.registers.control.write(
                    gbe_out_en=endisable))
        elif fpgas[0].registers.control.field_names().count('gbe_txen') > 0:
            print '\tSim-style control registers found.'
            fpgautils.threaded_fpga_operation(
                fpgas, 10,
                lambda fpga: fpga.registers.control.write(
                    gbe_txen=endisable))
        elif fpgas[0].registers.control.field_names().count('comms_en') > 0:
            print '\tOld-style control registers found.'
            fpgautils.threaded_fpga_operation(
                fpgas, 10,
                lambda fpga: fpga.registers.control.write(
                    comms_en=endisable))
    elif fpgas[0].registers.names().count('ctrl') > 0:
        if fpgas[0].registers.ctrl.field_names().count('comms_en') > 0:
            print '\tSome control registers found?'
            print fpgautils.threaded_fpga_operation(
                fpgas, 10,
                lambda fpga: fpga.registers.ctrl.write(comms_en=endisable))
    else:
        print '\tCould not find the correct registers to control TX'

# disable
if args.disable:
    enable_disable(False)

# enable
if args.enable:
    enable_disable(True)

fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')

# end
