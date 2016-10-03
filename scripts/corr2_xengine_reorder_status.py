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
    if 'unpack_cnt_rst' in fpgas[0].registers.control.field_names():
        fpgautils.threaded_fpga_operation(
            fpgas, 10, lambda fpga_:
            fpga_.registers.control.write(cnt_rst='pulse',
                                          unpack_cnt_rst='pulse'))
    else:
        fpgautils.threaded_fpga_operation(
            fpgas, 10, lambda fpga_:
            fpga_.registers.control.write(cnt_rst='pulse', up_cnt_rst='pulse'))


def get_fpga_data(fpga):
    return fpga.get_rx_reorder_status()


def exit_gracefully(sig, frame):
    print sig, frame
    scroll.screen_teardown()
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGHUP, exit_gracefully)

data = get_fpga_data(fpgas[0])[0]
fld_names = data.keys()
fld_names.sort()

# work out the maximum host & field name widths
max_1st_col_offset = -1
for fpga in fpgas:
    max_1st_col_offset = max(max_1st_col_offset, len(fpga.host))
max_fldname = -1
max_flddata = -1
for fldname in fld_names:
    max_fldname = max(max_fldname, len(fldname))
    max_flddata = max(max_flddata, len(str(data[fldname])))
max_1st_col_offset += 5
max_fldname += 2
max_flddata += 2

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
            scroller.add_string('Polling %i fengine%s every %s - %is '
                                'elapsed.' % (
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
                        printline += '  {fldname:>{fldwidth}}' \
                                     '[{val:>{valwidth}}]'.format(
                            fldname=key, fldwidth=max_fldname,
                            val=value, valwidth=max_flddata)
                    scroller.add_line(printline)
            scroller.draw_screen()
            last_refresh = time.time()
        else:
            time.sleep(0.1)
except Exception, e:
    exit_gracefully(None, None)
    raise

exit_gracefully(None, None)

# end
