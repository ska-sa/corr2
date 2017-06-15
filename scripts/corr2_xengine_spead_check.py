#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Check the SPEAD status registers on x-engines.

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

parser = argparse.ArgumentParser(
    description='Display SPEAD RX info from the xengines.',
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
hosts = utils.parse_hosts(args.hosts, section='xengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# create the devices and connect to them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
registers_missing = []
max_hostname = -1
for fpga_ in fpgas:
    max_hostname = max(len(fpga_.host), max_hostname)
    freg_error = False
    for necreg in ['rx_cnt0', 'rx_cnt1', 'rx_err_cnt0', 'rx_err_cnt1',
                   'speadtime_lsbzero', ]:
        if necreg not in fpga_.registers.names():
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
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse'))


def get_fpga_data(fpga):
    data = {}
    for ctr in range(0, 2):
        data['rxcnt%i' % ctr] = fpga.registers['rx_cnt%i' % ctr].read()['data']['reg']
        data['rxerr%i' % ctr] = fpga.registers['rx_err_cnt%i' % ctr].read()['data']['reg']
    temp = fpga.registers['speadtime_lsbzero'].read()['data']
    data['timlsbs0'] = temp['spead0']
    data['timlsbs1'] = temp['spead1']
    return data

data = get_fpga_data(fpgas[0])
reg_names = data.keys()
reg_names.sort()

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
            scroller.draw_screen()
        if time.time() > last_refresh + args.polltime:
            scroller.clear_buffer()
            scroller.add_string(
                'Polling %i xengine%s every %s - %is elapsed.' % (
                    len(fpgas), '' if len(fpgas) == 1 else 's',
                    'second' if args.polltime == 1 else ('%i seconds' % args.polltime),
                    time.time() - STARTTIME), 0, 0, fixed=True)
            start_pos = max_1st_col_offset
            pos_increment = max_regname + 4
            scroller.add_string('Host', 0, 1)
            for reg in reg_names:
                regval = '{val:>{width}}'.format(val=reg, width=max_regname)
                scroller.add_string(
                    reg.rjust(max_regname), xpos=start_pos, ypos=1)
                start_pos += pos_increment
            scroller.add_string('', cr=True)
            scroller.set_current_line(2)
            scroller.set_ylimits(1)
            all_fpga_data = fpgautils.threaded_fpga_operation(
                fpgas, 10, get_fpga_data)
            for ctr, fpga in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga.host]
                scroller.add_string(fpga.host)
                start_pos = max_1st_col_offset
                pos_increment = max_regname + 4
                for reg in reg_names:
                    regval = '{val:>{width}}'.format(
                        val=fpga_data[reg], width=max_regname)
                    scroller.add_string(regval, start_pos)
                    start_pos += pos_increment
                scroller.add_string('', cr=True)
            scroller.draw_screen()
            last_refresh = time.time()
        else:
            time.sleep(0.1)
except Exception, e:
    exit_gracefully(None, None)
    raise

exit_gracefully(None, None)

# end
