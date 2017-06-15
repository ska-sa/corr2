#! /usr/bin/env python
""" 
Script for checking the approximate clock rate of correlator FPGAs.
"""
from __future__ import print_function
import sys
import argparse
import os

from casperfpga import utils as fpgautils
from corr2 import utils

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Ping a list of hosts by connecting to them.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--hosts', dest='hosts', type=str, action='store', default='',
        help='comma-delimited list of hosts, or a corr2 config file')
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

    if 'CORR2INI' in os.environ.keys() and args.hosts == '':
        args.hosts = os.environ['CORR2INI']
    hosts = utils.parse_hosts(args.hosts)
    if (not hosts) or (len(hosts) == 0):
        raise RuntimeError('No good carrying on without hosts.')
try:
    print('Connecting...', end='')
    sys.stdout.flush()
    fpgas = fpgautils.threaded_create_fpgas_from_hosts(hosts)
    print('done.')

    print('Calculating all clocks...', end='')
    sys.stdout.flush()
    results = fpgautils.threaded_fpga_function(fpgas, 10, 'estimate_fpga_clock')
    print('done.')
    for fpga_ in fpgas:
        print('%s: %.0f Mhz' % (fpga_.host, results[fpga_.host]))

    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
except:
    import IPython
    IPython.embed()

# end
