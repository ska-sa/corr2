#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given Bengine.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys
import time
import argparse
import signal
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
import casperfpga.scroll as scroll
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Display information about a MeerKAT b-engine.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str,
                    action='store', default='',
                    help='comma-delimited list of hosts, or a corr2 '
                         'config file')
parser.add_argument('-p', '--polltime', dest='polltime',
                    action='store', default=1, type=int,
                    help='time at which to poll b-engine data, in seconds')
parser.add_argument('--comms', dest='comms', action='store',
                    default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level',
                    action='store', default='',
                    help='log level to use, default None, options INFO, '
                         'DEBUG, ERROR')
args = parser.parse_args()


def signal_handler(signal_, frame):
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    scroll.screen_teardown()
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)

polltime = args.polltime

if args.log_level:
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=getattr(logging, log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if 'CORR2INI' in os.environ.keys() and args.hosts == '':
    args.hosts = os.environ['CORR2INI']
hosts = utils.parse_hosts(args.hosts, section='xengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(katcp_fpga.KatcpFpga, hosts)
fpgautils.threaded_fpga_function(fpgas, 10, 'get_system_information')

# check for 10gbe cores
for fpga_ in fpgas:
    numgbes = len(fpga_.tengbes)
    if numgbes < 1:
        raise RuntimeError('Cannot have a b-engine with no '
                           '10gbe cores? %s' % fpga_.host)
    print '%s: found %i 10gbe core%s.' % \
          (fpga_.host, numgbes, '' if numgbes == 1 else 's')

# look for b-engine registers
num_beams = 0
for ctr in range(512):
    if 'bf%i_out_count' % ctr in fpgas[0].registers.names():
        num_beams += 1
    else:
        break
if num_beams == 0:
    print 'ERROR: cannot carry on with no beams on x-engines'
    signal_handler(None, None)
print 'Found %i beams on FPGA 0' % num_beams
for fpga_ in fpgas:
    for ctr in range(num_beams):
        if 'bf%i_out_count' % ctr not in fpga_.registers.names():
            print 'ERROR: host %s does not have necessary beamformer ' \
                  'register %s' % (fpga_.host, 'bf%i_out_count' % ctr)
            print fpga_.registers.names()
            raise RuntimeError
        if 'bf%i_of_count' % ctr not in fpga_.registers.names():
            print 'ERROR: host %s does not have necessary beamformer ' \
                  'register %s' % (fpga_.host, 'bf%i_of_count' % ctr)
            print fpga_.registers.names()
            raise RuntimeError


def get_fpga_data(fpga_):
    rv = {}
    for ctr in range(num_beams):
        rvt = {'out': fpga_.registers['bf%i_out_count' % ctr].read()['data'],
               'of': fpga_.registers['bf%i_of_count' % ctr].read()['data']}
        rv[ctr] = rvt
    return rv

# set up the curses scroll screen
scroller = scroll.Scroll(debug=False)
scroller.screen_setup()
# main program loop
STARTTIME = time.time()
last_refresh = STARTTIME - 3
try:
    while True:
        # get key presses from ncurses
        keypress = scroller.on_keypress()[0]
        if keypress == -1:
            break
        elif keypress > 0:
            scroller.draw_screen()
        if time.time() > last_refresh + polltime:
            scroller.clear_buffer()
            scroller.add_string(
                'Polling %i x-engine%s every %s - %is elapsed.' % (
                    len(fpgas), '' if len(fpgas) == 1 else 's',
                    'second' if polltime == 1 else ('%i seconds' % polltime),
                    time.time() - STARTTIME), 0, 0, fixed=True)
            scroller.add_string('Host - out(0,1,2,3) of(0,1,2,3)',
                                0, 1, fixed=True)
            scroller.set_current_line(2)
            scroller.set_ylimits(2)
            all_fpga_data = fpgautils.threaded_fpga_operation(
                fpgas, 10, get_fpga_data)
            for ctr, fpga_ in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga_.host]
                scroller.add_line(fpga_.host)
                for beam_num, beam_data in fpga_data.items():
                    beamd = fpga_data[beam_num]
                    scroller.add_line(
                        '     beam%i%10i%10i%10i%10i%10i%10i%10i%10i' % (
                            beam_num,
                            beamd['out']['count0'],
                            beamd['out']['count1'],
                            beamd['out']['count2'],
                            beamd['out']['count3'],
                            beamd['of']['count0'],
                            beamd['of']['count1'],
                            beamd['of']['count2'],
                            beamd['of']['count3']))
            scroller.draw_screen()
            last_refresh = time.time()
except KeyboardInterrupt:
    signal_handler(None, None)
    raise

signal_handler(None, None)
# end
