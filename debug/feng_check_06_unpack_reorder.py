#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Check the debug registers after the reorder block inside the unpack section of the f-engine.

The unpack block has hardware error checking of the data inside the reordered packets.

1. Is the data ramp inside the packet payload present?
2. Does the time in the data payload match the SPEAD time?
3. Do successive packets have successive timestamps? This is a decent link quality check. It also checks the functionality of the reorder block.

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

parser = argparse.ArgumentParser(description='Check the flags out of the FIFO section in the unpack block. They'
                                             'should be zero of OFs and constantly incrementing for the VFIFOs.',
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
    for pol in [0, 1]:
        reord_errors = fpga.registers['updebug_reord_err%i' % pol].read()['data']
        # data['re%i_cnt' % pol] = reord_errors['cnt']
        # data['re%i_time' % pol] = reord_errors['time']
        # data['re%i_tstep' % pol] = reord_errors['timestep']
        data['timerror%i' % pol] = reord_errors['timestep']
    valid_cnt = fpga.registers.updebug_validcnt.read()['data']
    data['valid_arb'] = valid_cnt['arb']
    data['valid_reord'] = valid_cnt['reord']
    data['mcnt_relock'] = fpga.registers.mcnt_relock.read()['data']['reg']
    temp = fpga.registers.pfb_of.read()['data']
    data['pfb_of0'] = temp['of0']
    data['pfb_of1'] = temp['of1']
    return data


def signal_handler(sig, frame):
    print sig, frame
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    scroll.screen_teardown()
    sys.exit(0)
import signal
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
registers_missing = []
max_hostname = -1
for fpga_ in fpgas:
    max_hostname = max(len(fpga_.host), max_hostname)
    freg_error = False
    for necreg in ['updebug_reord_err0', 'updebug_reord_err1', 'updebug_validcnt', 'mcnt_relock', 'pfb_of']:
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
            start_pos = max_hostname + 3
            pos_increment = 20
            scroller.add_line('Host', 0, 1, absolute=True)
            for reg in reg_names:
                scroller.add_line(new_line=reg.rjust(13), xpos=start_pos, ypos=1, absolute=True)
                start_pos += pos_increment
            scroller.set_ypos(newpos=2)
            scroller.set_ylimits(ymin=2)
            all_fpga_data = fpgautils.threaded_fpga_operation(fpgas, 10, get_fpga_data)
            for ctr, ffpga in enumerate(fpgas):
                fpga_data = all_fpga_data[ffpga.host]
                scroller.add_line(ffpga.host)
                start_pos = max_hostname + 3
                pos_increment = 20
                for reg in reg_names:
                    regval = '%13d' % fpga_data[reg]
                    scroller.add_line(regval, start_pos, scroller.get_current_line() - 1) # all on the same line
                    start_pos += pos_increment
            scroller.draw_screen()
            last_refresh = time.time()
        else:
            time.sleep(0.1)
except Exception, e:
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    scroll.screen_teardown()
    raise

# handle exits cleanly
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
scroll.screen_teardown()
# end
