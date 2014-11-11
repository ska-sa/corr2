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

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
import casperfpga.scroll as scroll
from corr2 import utils

parser = argparse.ArgumentParser(description='GAGAH.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of x-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll xengine data, in seconds')
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

hosts = utils.parse_hosts(args.hosts, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# create the devices and connect to them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')

if 'cnt_up_adc_or' in fpgas[0].registers:
    regs = ['mcnt_nolock', 'sync_timestamp_msw', 'sync_timestamp_lsw', 'cnt_up_adc_or',
            'cnt_data_misaligned', 'cnt_relock', ]
    frt_aa = True
else:
    regs = ['mcnt_nolock', 'sync_timestamp_msw', 'sync_timestamp_lsw', ]
    frt_aa = False

if args.rstcnt:
    fpgautils.threaded_fpga_operation(fpgas, 10,
                                      lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse',
                                                                                  unpack_cnt_rst='pulse'))

if args.sysrst:
    fpgautils.threaded_fpga_operation(fpgas, 10,
                                      lambda fpga_: fpga_.registers.control.write(sys_rst='pulse'))


def checkregs(fpga_, necregs):
    freg_error = 0
    regnames = fpga_.registers.names()
    for necreg in necregs:
        if necreg not in regnames:
            freg_error += 1
    return freg_error > 0
regcheck = fpgautils.threaded_fpga_operation(fpgas, 10, checkregs, regs)
registers_missing = []
for fpga, error in regcheck.items():
    if error:
        registers_missing.append(fpga)
if len(registers_missing) > 0:
    print 'The following hosts are missing necessary registers. Bailing.'
    print registers_missing
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit()


def get_fpga_data(fpga):
    data = {}
    if frt_aa:
        data['up_adc_or'] = fpga.registers.cnt_up_adc_or.read()['data']['reg']
        data['data_misal'] = fpga.registers.cnt_data_misaligned.read()['data']['reg']
        data['relock'] = fpga.registers.cnt_relock.read()['data']['reg']
    data['mcnt_nolock'] = fpga.registers.mcnt_nolock.read()['data']['mcnt_nolock']
    data['sync_tstamp_msw'] = fpga.registers.sync_timestamp_msw.read()['data']['reg']
    temp = fpga.registers.sync_timestamp_lsw.read()['data']
    data['sync_tstamp_lsw'] = temp['time_lsw']
    data['tstep_error'] = temp['tstep_err_ctr']
    data['cnt_sync'] = temp['sync80_ctr']
    data['cnt_valid'] = temp['valid80_ctr']
    data['pkt_size'] = temp['pkt_size']
    return data

data = get_fpga_data(fpgas[0])
reg_names = data.keys()
reg_names.sort()

import signal
def signal_handler(sig, frame):
    print sig, frame
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
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
            start_pos = 20
            pos_increment = 20
            scroller.add_line('Host', 0, 1, absolute=True)
            for reg in reg_names:
                scroller.add_line(new_line=reg.rjust(8), xpos=start_pos, ypos=1, absolute=True)
                start_pos += pos_increment
            scroller.set_ypos(newpos=2)
            scroller.set_ylimits(ymin=2)
            all_fpga_data = fpgautils.threaded_fpga_operation(fpgas, 10, get_fpga_data)
            for ctr, fpga in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga.host]
                scroller.add_line(fpga.host)
                start_pos = 20
                pos_increment = 20
                for reg in reg_names:
                    regval = '%8d' % fpga_data[reg]
                    scroller.add_line(regval, start_pos, scroller.get_current_line() - 1) # all on the same line
                    start_pos += pos_increment
            scroller.draw_screen()
            last_refresh = time.time()
except Exception, e:
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    scroll.screen_teardown()
    raise

# handle exits cleanly
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
scroll.screen_teardown()
# end
