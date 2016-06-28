#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View status and error registers for x-engine reorder.

@author: paulp
"""
import sys
import time
import argparse
import os
import signal

from casperfpga import utils as fpgautils
import casperfpga.scroll as scroll
from corr2 import utils
from corr2.xhost_fpga import FpgaXHost

parser = argparse.ArgumentParser(
    description='View status and error registers for x-engine reorder.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='comma-delimited list of f-engine hosts')
parser.add_argument(
    '-p', '--polltime', dest='polltime', action='store',
    default=1, type=int,
    help='time at which to poll fengine data, in seconds')
parser.add_argument(
    '-r', '--reset_count', dest='rstcnt', action='store_true',
    default=False,
    help='reset all counters at script startup')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='',
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

if 'CORR2INI' in os.environ.keys() and args.hosts == '':
    args.hosts = os.environ['CORR2INI']
hosts = utils.parse_hosts(args.hosts, section='xengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# create the devices and connect to them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(FpgaXHost, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')

if args.rstcnt:
    fpgautils.threaded_fpga_operation(
        fpgas, 10, lambda fpga_:
        fpga_.registers.control.write(status_clr='pulse'))


def get_fpga_data(fpga):
    """
    :param fpga:
    :return: a dictionary of flags set per x-engine
    """
    data = fpga.get_status_registers()
    rv = []
    for xd in data:
        xdata = {}
        for k in xd.keys():
            if xd[k] == 1:
                xdata[k] = 1
        rv.append(xdata)
    return rv

# work out the maximum host & field name widths
max_1st_col_offset = -1
for fpga in fpgas:
    max_1st_col_offset = max(max_1st_col_offset, len(fpga.host))
max_1st_col_offset += 5


def exit_gracefully(sig, frame):
    print sig, frame
    scroll.screen_teardown()
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGHUP, exit_gracefully)

# set up the curses scroll screen
scroller = scroll.Scroll(debug=False)
scroller.screen_setup()
# main program loop
STARTTIME = time.time()
last_refresh = STARTTIME - 3
try:
    while True:
        # get key presses from ncurses
        keypress, character = scroller.on_keypress()
        if keypress == -1:
            break
        elif keypress > 0:
            scroller.draw_screen()
        if time.time() > last_refresh + polltime:
            scroller.clear_buffer()
            scroller.add_string(
                'Polling %i fengine%s every %s - %is elapsed.' % (
                    len(fpgas), '' if len(fpgas) == 1 else 's',
                    'second' if polltime == 1 else ('%i seconds' % polltime),
                    time.time() - STARTTIME), 0, 0, fixed=True)
            start_pos = max_1st_col_offset
            scroller.set_current_line(1)
            scroller.set_ylimits(1)
            all_fpga_data = fpgautils.threaded_fpga_operation(
                fpgas, 10, get_fpga_data)
            for ctr, fpga in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga.host]
                scroller.add_string(fpga.host, cr=True)
                for data in fpga_data:
                    printline = ''
                    for key in sorted(data.iterkeys()):
                        value = data[key]
                        printline += '    %s' % key
                    scroller.add_string(printline, cr=True)
            scroller.draw_screen()
            last_refresh = time.time()
        else:
            time.sleep(0.05)
except Exception, e:
    exit_gracefully(None, None)
    raise

exit_gracefully(None, None)

# end
