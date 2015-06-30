#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check the SPEAD error counter and valid counter in the unpack section of the F-engines.

@author: paulp
"""
import sys
import time
import argparse
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
import casperfpga.scroll as scroll
from corr2 import utils

parser = argparse.ArgumentParser(description='Check the SPEAD error counter and valid counter in the '
                                             'unpack section of the F-engines.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

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
hosts = utils.parse_hosts(args.hosts, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')


def get_fpga_data(fpga):
    data = {}
    for interface in [0, 1, 2, 3]:
        data['spead%i' % interface] = (fpga.registers['updebug_sp_err%i' % interface].read()['data']['reg'],
                                       fpga.registers['updebug_sp_val%i' % interface].read()['data']['reg'])
    return data


def exit_gracefully(sig, frame):
    print sig, frame
    scroll.screen_teardown()
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit(0)
import signal
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGHUP, exit_gracefully)

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
registers_missing = []
max_hostname = -1
for fpga_ in fpgas:
    max_hostname = max(len(fpga_.host), max_hostname)
    freg_error = False
    for necreg in ['updebug_sp_err0', 'updebug_sp_err1', 'updebug_sp_err2', 'updebug_sp_err3', 'updebug_sp_val0',
                   'updebug_sp_val1', 'updebug_sp_val2', 'updebug_sp_val3']:
        if necreg not in fpga_.registers.names():
            freg_error = True
            continue
    if freg_error:
        registers_missing.append(fpga_.host)
        continue
if len(registers_missing) > 0:
    print 'The following hosts are missing necessary registers. Bailing.'
    print registers_missing
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    raise RuntimeError

if args.rstcnt:
    if 'unpack_cnt_rst' in fpgas[0].registers.control.field_names():
        fpgautils.threaded_fpga_operation(fpgas, 10,
                                          lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse',
                                                                                      unpack_cnt_rst='pulse'))
    else:
        fpgautils.threaded_fpga_operation(fpgas, 10,
                                          lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse',
                                                                                      up_cnt_rst='pulse'))

fpga_data = get_fpga_data(fpgas[0])
reg_names = fpga_data.keys()
reg_names.sort()

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
            # if character == 'c':
            #     for f in fpgas:
            #         f.reset_counters()
            scroller.draw_screen()
        if time.time() > last_refresh + args.polltime:
            scroller.clear_buffer()
            scroller.add_line('Polling %i fengine%s every %s - %is elapsed.' %
                              (len(fpgas), '' if len(fpgas) == 1 else 's',
                               'second' if args.polltime == 1 else ('%i seconds' % args.polltime),
                               time.time() - STARTTIME), 0, 0, absolute=True)

            scroller.add_line('SPEAD(error_count, valid_count)', 0, 1, absolute=True)

            scroller.add_line('Host', 0, 2, absolute=True)
            start_pos = max_hostname + 3
            pos_increment = 20
            for reg in reg_names:
                scroller.add_line(new_line=reg.ljust(10), xpos=start_pos, ypos=2, absolute=True)
                start_pos += pos_increment
            scroller.set_ypos(newpos=3)
            scroller.set_ylimits(ymin=3)
            all_fpga_data = fpgautils.threaded_fpga_operation(fpgas, 10, get_fpga_data)
            for ctr, ffpga in enumerate(fpgas):
                fpga_data = all_fpga_data[ffpga.host]
                scroller.add_line(ffpga.host)
                start_pos = max_hostname + 3
                for reg in ['spead0', 'spead1', 'spead2', 'spead3']:
                    valstring = '(%d,%d)' % (fpga_data[reg][0], fpga_data[reg][1])
                    scroller.add_line(valstring, start_pos, scroller.get_current_line() - 1) # all on the same line
                    start_pos += pos_increment
            scroller.draw_screen()
            last_refresh = time.time()
        else:
            time.sleep(0.1)
except Exception, e:
    exit_gracefully(None, None)
    raise

exit_gracefully(None, None)
# end
