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

regs = ['mcnt_relock', 'tmiss_p0', 'tmiss_p1', 'tmiss_ctr', 'recverr_ctr', 'timestep_ages',
        'sync_timestamp_msw', 'sync_timestamp_lsw']

if args.rstcnt:
    fpgautils.threaded_fpga_operation(fpgas, 10,
                                      target_function=
                                      (lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse',
                                                                                   unpack_cnt_rst='pulse'),))

if args.sysrst:
    fpgautils.threaded_fpga_operation(fpgas, 10,
                                      target_function=
                                      (lambda fpga_: fpga_.registers.control.write(sys_rst='pulse'),))


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
    data = {}
    data['mcnt_rlck'] = fpga.registers.mcnt_relock.read()['data']['reg']
    data['tmis_p0'] = fpga.registers.tmiss_p0.read()['data']['reg']
    data['tmis_p1'] = fpga.registers.tmiss_p1.read()['data']['reg']
    temp = fpga.registers.tmiss_ctr.read()['data']
    data['tmis_ctr0'] = temp['p0']
    data['tmis_ctr1'] = temp['p1']
    temp = fpga.registers.recverr_ctr.read()['data']
    data['rerr_ctr0'] = temp['p0']
    data['rerr_ctr1'] = temp['p1']
    temp = fpga.registers.timestep_ages.read()['data']
    data['futuerr'] = temp['future']
    data['pasterr'] = temp['past']
    data['sy_tstmp'] = fpga.registers.sync_timestamp_msw.read()['data']['reg'] << 4
    temp = fpga.registers.sync_timestamp_lsw.read()['data']
    data['sy_tstmp'] = data['sy_tstmp'] | temp['time_lsw']
    data['tstep_err'] = temp['tstep_err_ctr']
    data['cnt_sync'] = temp['sync80_ctr']
    data['cnt_val'] = temp['valid80_ctr']
    data['pkt_sz'] = temp['pkt_size']
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
#            if character == 'c':
#                for f in ffpgas:
#                    f.reset_counters()
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
                    scroller.add_line(regval, start_pos, scroller.get_current_line() - 1) # all on the same line
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
