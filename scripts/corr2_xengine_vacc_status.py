#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Display VACC status registers for x-engines.
"""
import sys
import signal
import time
import argparse
import os

from casperfpga import utils as fpgautils
import casperfpga.scroll as scroll
from corr2 import utils
from corr2 import xhost_fpga

parser = argparse.ArgumentParser(
    description='Display vector accumulator debug info on the xengines.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='comma-delimited list of x-engine hosts')
parser.add_argument(
    '-p', '--polltime', dest='polltime', action='store',
    default=1, type=int,
    help='time at which to poll xengine data, in seconds')
parser.add_argument(
    '-r', '--reset_count', dest='rstcnt', action='store_true',
    default=False,
    help='reset all counters at script startup')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='INFO',
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
hosts = utils.parse_hosts(args.hosts, section='xengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# TODO - sort out getting sys info from the config file

# create the devices and connect to them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(xhost_fpga.FpgaXHost, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')

if args.rstcnt:
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse'))


def get_fpga_data(fpga):
    vaccstats = fpga.vacc_get_status()
    _data = {}
    for _ctr in range(0, 4):
        _data['err%i' % _ctr] = vaccstats[_ctr]['errors']
        _data['cnt%i' % _ctr] = vaccstats[_ctr]['count']
        _data['armcnt%i' % _ctr] = vaccstats[_ctr]['armcount']
        _data['ldcnt%i' % _ctr] = vaccstats[_ctr]['loadcount']
    return _data

try:
    data = get_fpga_data(fpgas[0])
    reg_names = data.keys()
    reg_names.sort()
except Exception:
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    raise

# work out the maximum host & field name widths
max_1st_col_offset = -1
for fpga in fpgas:
    max_1st_col_offset = max(max_1st_col_offset, len(fpga.host))
max_regname = -1
for regname in reg_names:
    max_regname = max(max_regname, len(regname))
    max_regname = max(max_regname, len(str(data[regname])))
max_1st_col_offset += 5


def exit_gracefully(sig, frame):
    print('%s %s' % (sig, frame))
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
#            if character == 'c':
#                for f in ffpgas:
#                    f.reset_counters()
            scroller.draw_screen()
        if time.time() > last_refresh + args.polltime:
            scroller.clear_buffer()
            scroller.add_string(
                'Polling %i xengine%s every %s - %is elapsed.' % (
                    len(fpgas), '' if len(fpgas) == 1 else 's',
                    'second' if args.polltime == 1 else ('%i seconds' % args.polltime),
                    time.time() - STARTTIME), 0, 0, fixed=True)
            start_pos = max_1st_col_offset
            pos_increment = max_regname + 2
            scroller.add_string('Host', 0, 1)
            for reg in reg_names:
                regstr = '{val:>{width}}'.format(val=reg, width=max_regname)
                scroller.add_string(regstr, xpos=start_pos, ypos=1)
                start_pos += pos_increment
            scroller.add_string('', cr=True)
            scroller.set_current_line(2)
            scroller.set_ylimits(1)
            all_fpga_data = fpgautils.threaded_fpga_operation(
                fpgas, 10, get_fpga_data)
            for ctr, fpga in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga.host]
                scroller.add_line(fpga.host)
                start_pos = max_1st_col_offset
                pos_increment = max_regname + 2
                for reg in reg_names:
                    regstr = '{val:>{width}}'.format(val=fpga_data[reg],
                                                     width=max_regname)
                    scroller.add_string(regstr, start_pos)
                    start_pos += pos_increment
                scroller.add_string('', cr=True)
            scroller.draw_screen()
            last_refresh = time.time()
        else:
            time.sleep(0.05)
except Exception, e:
    exit_gracefully(None, None)
    raise

exit_gracefully(None, None)

# end
