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

from casperfpga import utils as fpgautils
import casperfpga.scroll as scroll
from corr2 import utils

THREADED_FPGA_OPS = fpgautils.threaded_fpga_operation


parser = argparse.ArgumentParser(
    description='Display the corner turner error counters on the fengine.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='comma-delimited list of f-engine hosts or, if integers, positions'
         'of the hosts in the list')
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument(
    '--bitstream', dest='bitstream', type=str, action='store', default='',
    help='a bitstream for the f-engine hosts (Skarabs need this given '
         'if no config is found)')
parser.add_argument(
    '-p', '--polltime', dest='polltime', action='store',
    default=1, type=int,
    help='time at which to poll fengine data, in seconds')
parser.add_argument(
    '-r', '--reset_count', dest='rstcnt', action='store_true',
    default=False,
    help='reset all counters at script startup')
parser.add_argument(
    '--comms', dest='comms', action='store', default='katcp', type=str,
    help='katcp (default) or dcp?')
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

# create the devices and connect to them
fpgas = utils.feng_script_get_fpgas(args)
registers_missing = []
max_hostname = -1
for fpga_ in fpgas:
    max_hostname = max(len(fpga_.host), max_hostname)
    freg_error = False
    for necreg in ['ct_status%i' % regcnt for regcnt in range(6)]:
        if necreg not in fpga_.registers.names():
            print(fpga_.host, ' missing ', necreg)
            freg_error = True
            continue
    if freg_error:
        registers_missing.append(fpga_.host)
        continue
if len(registers_missing) > 0:
    print('The following hosts are missing necessary registers. Bailing.')
    print(registers_missing)
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    raise RuntimeError

if args.rstcnt:
    if 'unpack_cnt_rst' in fpgas[0].registers.control.field_names():
        THREADED_FPGA_OPS(
            fpgas, 10, lambda fpga_:
            fpga_.registers.control.write(cnt_rst='pulse',
                                          unpack_cnt_rst='pulse'))
    else:
        THREADED_FPGA_OPS(
            fpgas, 10, lambda fpga_:
            fpga_.registers.control.write(cnt_rst='pulse', up_cnt_rst='pulse'))


def get_fpga_data(fpga):
    rv = []
    for regname in ['ct_status%i' % regcnt for regcnt in range(6)]:
        rv.append(fpga.registers[regname].read()['data'])
    return rv


def exit_gracefully(sig, frame):
    print(sig, frame)
    scroll.screen_teardown()
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGHUP, exit_gracefully)


print(get_fpga_data(fpgas[0]))
raise RuntimeError



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
#            if character == 'c':
#                for f in ffpgas:
#                    f.reset_counters()
            scroller.draw_screen()
        if time.time() > last_refresh + polltime:
            scroller.clear_buffer()
            scroller.add_line('Polling %i fengine%s every %s - %is elapsed.' %
                (len(fpgas), '' if len(fpgas) == 1 else 's',
                'second' if polltime == 1 else ('%i seconds' % polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
            start_pos = 20
            pos_increment = 20
            scroller.set_ypos(newpos=1)
            all_fpga_data = THREADED_FPGA_OPS(fpgas, 10, get_fpga_data)
            for ctr, fpga in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga.host]
                scroller.add_line(fpga.host)
                printline = ''
                for key, value in fpga_data.items():
                    printline += '\t%s[%i]' % (key, value)
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
