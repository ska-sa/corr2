#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given xengine.

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
from casperfpga import dcp_fpga
import casperfpga.scroll as scroll
from corr2 import utils

parser = argparse.ArgumentParser(description='Display information about a MeerKAT x-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument('-p', '--polltime', dest='polltime', action='store', default=1, type=int,
                    help='time at which to poll x-engine data, in seconds')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

polltime = args.polltime

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
hosts = utils.parse_hosts(args.hosts, section='xengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# xeng_hosts = ['roach020921', 'roach020927', 'roach020919', 'roach020925',
#           'roach02091a', 'roach02091e', 'roach020923', 'roach020924']

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 'get_system_information')

# check for 10gbe cores
for fpga_ in fpgas:
    numgbes = len(fpga_.tengbes)
    if numgbes < 1:
        raise RuntimeError('Cannot have an x-engine with no 10gbe cores? %s' % fpga_.host)
    print '%s: found %i 10gbe core%s.' % (fpga_.host, numgbes, '' if numgbes == 1 else 's')


def print_headers(scr):
    """Print the table headers.
    """
    scr.addstr(2, 2, 'xhost')
    scr.addstr(2, 20, 'tap')
    scr.addstr(2, 30, 'TX')
    scr.addstr(3, 30, 'cnt')
    scr.addstr(3, 40, 'err')
    scr.addstr(2, 50, 'RX')
    scr.addstr(3, 50, 'cnt')
    scr.addstr(3, 60, 'err')


def get_fpga_data(fpga_):
    return {'gbe': {core_.name: core_.read_counters() for core_ in fpga_.tengbes}}

fpga_data = get_fpga_data(fpgas[0])

def signal_handler(signal_, frame):
    fpgautils.threaded_fpga_function(fpgas, 'disconnect')
    scroll.screen_teardown()
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)

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
            scroller.add_line('Polling %i x-engine%s every %s - %is elapsed.' %
                              (len(fpgas), '' if len(fpgas) == 1 else 's',
                               'second' if polltime == 1 else ('%i seconds' % polltime),
                               time.time() - STARTTIME), 0, 0, absolute=True)
#            scroller.add_line('hdr1', 10)
#            scroller.add_line('hdr2', 30, scroller.get_current_line())
            scroller.add_line('Host', 0, 1, absolute=True)
            scroller.add_line('GBE_rxcnt', 30, 1, absolute=True)
            scroller.add_line('GBE_rxerror', 50, 1, absolute=True)
            scroller.add_line('GBE_txcnt', 70, 1, absolute=True)
            scroller.add_line('GBE_txerror', 90, 1, absolute=True)
            scroller.set_ypos(2)
            scroller.set_ylimits(ymin=2)
            all_fpga_data = fpgautils.threaded_fpga_operation(fpgas, get_fpga_data)
            for ctr, fpga_ in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga_.host]
                scroller.add_line(fpga_.host)
                for core, value in fpga_data['gbe'].items():
                    scroller.add_line(core, 5)
                    xpos = 30
                    for regname in [core + '_rxctr', core + '_rxerrctr', core + '_txctr', core + '_txerrctr']:
                        try:
                            regval = '%10d' % fpga_data['gbe'][core][regname]['data']['reg']
                        except KeyError:
                            regval = 'n/a'
                        scroller.add_line(regval, xpos, scroller.get_current_line() - 1)
                        xpos += 20
            scroller.draw_screen()
            last_refresh = time.time()
except Exception, e:
    signal_handler(None, None)
    raise

signal_handler(None, None)
# end
