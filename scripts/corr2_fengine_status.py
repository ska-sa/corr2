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
import logging
import time
import argparse
import signal
from casperfpga import KatcpClientFpga
import casperfpga.scroll as scroll
from corr2 import utils

logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser(description='Display information about a MeerKAT f-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of f-engine hosts, or a corr2 config file')
parser.add_argument('-p', '--polltime', dest='polltime', action='store', default=1, type=int,
                    help='time at which to poll f-engine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true', default=False,
                    help='reset all counters at script startup')
args = parser.parse_args()

polltime = args.polltime

feng_hosts = args.hosts.strip().replace(' ', '').split(',')
if len(feng_hosts) == 1:  # check to see it it's a file
    try:
        hosts = utils.hosts_from_config_file(feng_hosts[0])
        feng_hosts = hosts['fengine']
    except IOError:
        # it's not a file so carry on
        pass
    except KeyError:
        raise RuntimeError('That config file does not seem to have a f-engine section.')

if len(feng_hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

#feng_hosts = ['roach02091b', 'roach020914', 'roach020915', 'roach020922']
#feng_hosts = ['roach02091b']

# create the devices and connect to them
ffpgas = []
for host in feng_hosts:
    feng_fpga = KatcpClientFpga(host)
    time.sleep(0.3)
    if not feng_fpga.is_connected():
        feng_fpga.connect()
    feng_fpga.test_connection()
    feng_fpga.get_system_information()
    numgbes = len(feng_fpga.tengbes)
    if numgbes < 1:
        raise RuntimeError('Cannot have an f-engine with no 10gbe cores?')
    print '%s: found %i 10gbe core%s.' % (host, numgbes, '' if numgbes == 1 else 's')
    if args.rstcnt:
        feng_fpga.registers.control.write(cnt_rst='pulse')
    ffpgas.append(feng_fpga)


def fengine_gbe(fpga_):
    """
    Get 10gbe data from the fpga.
    :param fpga_:
    :return:
    """
    cores = fpga_.tengbes
    returndata = {}
    for core_ in cores:
        returndata[core_.name] = core_.read_counters()
    return returndata


def fengine_rxtime(fpga_):
    try:
        returnval = (fpga_.registers.local_time_msw.read()['data']['reg'] << 32) + \
                    fpga_.registers.local_time_lsw.read()['data']['reg']
    except:
        returnval = -1
    return returnval


def get_fpga_data(fpga_):
    return {'gbe': fengine_gbe(fpga_), 'rxtime': fengine_rxtime(fpga_), 'mcnt_nolock': 555}

# work out tables for each fpga
fpga_headers = []
master_list = []
for cnt, fpga in enumerate(ffpgas):
    gbedata = get_fpga_data(fpga)['gbe']
    gbe0 = gbedata.keys()[0]
    core0_regs = [key.replace(gbe0, 'gbe') for key in gbedata[gbe0].keys()]
    if cnt == 0:
        master_list = core0_regs[:]
    for core in gbedata:
        core_regs = [key.replace(core, 'gbe') for key in gbedata[core].keys()]
        if sorted(core0_regs) != sorted(core_regs):
            raise RuntimeError('Not all GBE cores for FPGA %s have the same support registers. Problem.', fpga.host)
    fpga_headers.append(core0_regs)

all_the_same = True
for cnt, _ in enumerate(ffpgas):
    if sorted(master_list) != sorted(fpga_headers[cnt]):
        all_the_same = False
        raise RuntimeError('Warning: GBE cores across given FPGAs are NOT configured the same!')
if all_the_same:
    fpga_headers = [fpga_headers[0]]

fpga_headers = [['gbe_rxctr', 'gbe_rxofctr', 'gbe_rxerrctr', 'gbe_rxeofctr', 'gbe_txerrctr',
                 'gbe_txfullctr', 'gbe_txofctr', 'gbe_txctr', 'gbe_txvldctr']]


def signal_handler(sig, frame):
    print sig, frame
    for fpga_ in ffpgas:
        fpga_.disconnect()
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
        if time.time() > last_refresh + polltime:
            scroller.clear_buffer()
            scroller.add_line('Polling %i f-engine%s every %s - %is elapsed.' %
                              (len(ffpgas), '' if len(ffpgas) == 1 else 's',
                               'second' if polltime == 1 else ('%i seconds' % polltime),
                               time.time() - STARTTIME), 0, 0, absolute=True)
            start_pos = 30
            pos_increment = 20
            if len(fpga_headers) == 1:
                scroller.add_line('Host', 0, 1, absolute=True)
                for reg in fpga_headers[0]:
                    scroller.add_line(reg, start_pos, 1, absolute=True)
                    start_pos += pos_increment
                scroller.set_ypos(newpos=2)
                scroller.set_ylimits(ymin=2)
            else:
                scroller.set_ypos(1)
                scroller.set_ylimits(ymin=1)
            for ctr, fpga in enumerate(ffpgas):
                fpga_data = get_fpga_data(fpga)
#                scroller.add_line(fpga.host)
                scroller.add_line(fpga.host + (' - %12d' % fpga_data['rxtime']) + (', %12d' % fpga_data['mcnt_nolock']))
                for core, core_data in fpga_data['gbe'].items():
                    start_pos = 30
                    pos_increment = 20
                    scroller.add_line(core, 5)
                    for header_register in fpga_headers[0]:
                        core_register_name = header_register.replace('gbe', core)
                        if start_pos < 200:
                            try:
                                regval = '%10d' % core_data[core_register_name]['data']['reg']
                            except KeyError:
                                regval = '-1'
                            scroller.add_line(regval, start_pos, scroller.get_current_line() - 1)  # all on one line
                            start_pos += pos_increment
            scroller.draw_screen()
            last_refresh = time.time()
except Exception, e:
    for fpga in ffpgas:
        fpga.disconnect()
    scroll.screen_teardown()
    raise

# handle exits cleanly
for fpga in ffpgas:
    fpga.disconnect()
scroll.screen_teardown()
# end
