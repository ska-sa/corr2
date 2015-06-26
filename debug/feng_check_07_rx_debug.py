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
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
import casperfpga.scroll as scroll
from corr2 import utils

COLUMN_WIDTH = 12

parser = argparse.ArgumentParser(description='Read RX debug registers on f-engines.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of f-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
parser.add_argument('--sys_rst', dest='sysrst', action='store_true',
                    default=False,
                    help='SYS RESET')
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

# create the devices and connect to them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')

regs = ['spead_ctrs', 'reorder_ctrs']

if args.rstcnt:
    fpgautils.threaded_fpga_operation(fpgas, 10,
                                      target_function=(lambda fpga_:
                                                       fpga_.registers.control.write(cnt_rst='pulse',)))

if args.sysrst:
    fpgautils.threaded_fpga_operation(
        fpgas, 10, target_function=(lambda fpga_:
                                    fpga_.registers.control.write(sys_rst='pulse'),))

def checkregs(fpga_, necregs):
    freg_error = 0
    regnames = fpga_.registers.names()
    for necreg in necregs:
        if necreg not in regnames:
            freg_error += 1
    return freg_error > 0
regcheck = fpgautils.threaded_fpga_operation(fpgas, 10, target_function=(checkregs, (regs,)))
registers_missing = []
for fpga, error in regcheck.items():
    if error:
        registers_missing.append(fpga)
if len(registers_missing) > 0:
    print 'The following hosts are missing necessary registers. Bailing.'
    print registers_missing
    fpgautils.threaded_fpga_function(fpgas, 10, target_function=('disconnect',))
    sys.exit()

def get_fpga_data(fpga):
    temp = fpga.registers.spead_ctrs.read()['data']
    data = {'sprx0': temp['rx_cnt0'],
            'sprx1': temp['rx_cnt1'],
            'sprx2': temp['rx_cnt2'],
            'sprx3': temp['rx_cnt3'],
            'sperr0': temp['err_cnt0'],
            'sperr1': temp['err_cnt1'],
            'sperr2': temp['err_cnt2'],
            'sperr3': temp['err_cnt3']}
    temp = fpga.registers.reorder_ctrs.read()['data']
    data['pktof0'] = temp['pktof0']
    data['pktof1'] = temp['pktof1']
    data['pktof2'] = temp['pktof2']
    data['pktof3'] = temp['pktof3']
    data['disc'] = temp['discard']
    data['tstep_err'] = temp['timestep_error']
    data['mcnt_rlck'] = temp['mcnt_relock']
    data['rcverr0'] = temp['recverr0']
    data['rcverr1'] = temp['recverr1']
    return data

data = get_fpga_data(fpgas[0])
reg_names = data.keys()
reg_names.sort()

import signal
def exit_gracefully(sig, frame):
    print sig, frame
    scroll.screen_teardown()
    fpgautils.threaded_fpga_function(fpgas, 10, target_function=('disconnect',))
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
            scroller.add_line('Polling %i fengine%s every %s - %is elapsed.' %
                (len(fpgas), '' if len(fpgas) == 1 else 's',
                'second' if args.polltime == 1 else ('%i seconds' % args.polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
            start_pos = 15
            pos_increment = COLUMN_WIDTH
            scroller.add_line('Host', 0, 1, absolute=True)
            for reg in reg_names:
                scroller.add_line(new_line=reg.rjust(8), xpos=start_pos, ypos=1, absolute=True)
                start_pos += pos_increment
            scroller.set_ypos(newpos=2)
            scroller.set_ylimits(ymin=2)
            all_fpga_data = fpgautils.threaded_fpga_operation(fpgas, 10, target_function=(get_fpga_data,))
            for ctr, fpga in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga.host]
                scroller.add_line(fpga.host)
                start_pos = 15
                pos_increment = COLUMN_WIDTH
                for reg in reg_names:
                    regval = '%8d' % fpga_data[reg]
                    scroller.add_line(regval, start_pos, scroller.get_current_line() - 1)  # all on the same line
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
