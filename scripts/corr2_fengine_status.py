#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given fengine.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys
import time
import argparse
import signal
import os

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
import casperfpga.scroll as scroll
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Display information about a MeerKAT f-engine.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--hosts', dest='hosts', type=str, action='store', default='',
    help='comma-delimited list of hosts, or a corr2 config file')
parser.add_argument(
    '-p', '--polltime', dest='polltime', action='store', default=1, type=int,
    help='time at which to poll f-engine data, in seconds')
parser.add_argument(
    '-r', '--reset_count', dest='rstcnt', action='store_true', default=False,
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
hosts = utils.parse_hosts(args.hosts, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(katcp_fpga.KatcpFpga, hosts)
fpgautils.threaded_fpga_function(fpgas, 10, 'get_system_information')

# check for 10gbe cores
for fpga_ in fpgas:
    numgbes = len(fpga_.tengbes)
    if numgbes < 1:
        raise RuntimeError('Cannot have an f-engine with no 10gbe cores? %s' % fpga_.host)
    print '%s: found %i 10gbe core%s.' % (fpga_.host, numgbes, '' if numgbes == 1 else 's')
    if args.rstcnt:
        fpga_.registers.control.write(cnt_rst='pulse')


def fengine_rxtime(fpga_):
    regs = fpga_.registers
    try:
        rv = (regs.local_time_msw.read()['data']['timestamp_msw'] << 32) + \
             regs.local_time_lsw.read()['data']['timestamp_lsw']
    except:
        rv = -1
    return rv


def get_fpga_data(fpga_):
    rv = {
        'gbe': {core_.name: core_.read_counters() for core_ in fpga_.tengbes},
        'rxtime': fengine_rxtime(fpga_),
        'mcnt_nolock': 555
    }
    for gbename in rv['gbe'].keys():
        if gbename.startswith('test_'):
            rv['gbe'].pop(gbename)
    return rv

# work out tables for each fpga
fpga_headers = []
master_list = []
fpga_data = fpgautils.threaded_fpga_operation(fpgas, 10, get_fpga_data)
for cnt, fpga_ in enumerate(fpgas):
    gbedata = fpga_data[fpga_.host]['gbe']
    for core in gbedata.keys():
        if core.startswith('test'):
            del(gbedata[core])

    gbe0 = gbedata.keys()[0]
    core0_regs = [key.replace(gbe0, 'gbe') for key in gbedata[gbe0].keys()]
    if cnt == 0:
        master_list = core0_regs[:]
    for core in gbedata:
        core_regs = [key.replace(core, 'gbe') for key in gbedata[core].keys()]
        if sorted(core0_regs) != sorted(core_regs):
            raise RuntimeError('Not all GBE cores for FPGA %s have the same '
                               'support registers. Problem.', fpga_.host)
    fpga_headers.append(core0_regs)

all_the_same = True
for cnt, _ in enumerate(fpgas):
    if sorted(master_list) != sorted(fpga_headers[cnt]):
        all_the_same = False
        raise RuntimeError('Warning: GBE cores across given FPGAs are NOT '
                           'configured the same!')
if all_the_same:
    fpga_headers = [fpga_headers[0]]

# work out the maximum host & field name widths
max_1st_col_offset = -1
for fpga in fpgas:
    max_1st_col_offset = max(max_1st_col_offset, len(fpga.host))
max_regname = -1
for regname in fpga_headers:
    max_1st_col_offset = max(max_1st_col_offset, len(regname))
    max_regname = max(max_regname, len(regname))
max_1st_col_offset += 5
max_regname += 2


def signal_handler(sig, frame):
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
        keypress, character = scroller.on_keypress()
        if keypress == -1:
            break
        elif keypress > 0:
            scroller.draw_screen()
        if time.time() > last_refresh + polltime:
            scroller.clear_buffer()
            scroller.add_string(
                'Polling %i f-engine%s every %s - %is elapsed.' % (
                    len(fpgas),
                    '' if len(fpgas) == 1 else 's',
                    'second' if polltime == 1 else ('%i seconds' % polltime),
                    time.time() - STARTTIME),
                0, 0, fixed=True)
            scroller.set_current_line(1)
            scroller.set_ylimits(1)
            all_fpga_data = fpgautils.threaded_fpga_operation(
                fpgas, 10, get_fpga_data)
            for ctr, fpga_ in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga_.host]
                scroller.add_string(
                    fpga_.host + (' - %12d' % fpga_data['rxtime']) +
                    (', %12d' % fpga_data['mcnt_nolock']), cr=True)
                for core, core_data in fpga_data['gbe'].items():
                    start_pos = max_1st_col_offset
                    pos_increment = max_regname + 2 + 10 + 5
                    scroller.add_string(core)
                    for header_register in fpga_headers[0]:
                        core_reg = header_register.replace('gbe', core)
                        try:
                            regval = '{}({val:{width}})'.format(
                                core_reg, val=core_data[core_reg],
                                width=5)
                            # regval = '%10d' % core_data[core_reg]
                        except:
                            regval = '-1'
                        regval = regval.rjust(max_regname)
                        scroller.add_string(regval, start_pos)
                        start_pos += pos_increment
                    scroller.add_string('', cr=True)
            scroller.draw_screen()
            last_refresh = time.time()
        else:
            time.sleep(0.05)
except Exception, e:
    signal_handler(None, None)
    raise

signal_handler(None, None)
# end
