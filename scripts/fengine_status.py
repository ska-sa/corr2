#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given xengine.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys, logging, time, argparse

logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.INFO)

from corr2.katcp_client_fpga import KatcpClientFpga
import corr2.scroll as scroll

parser = argparse.ArgumentParser(description='Display information about a MeerKAT fengine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of f-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
#parser.add_argument('-s', '--payloadsize', dest='payloadsize', action='store',
#                    default=5120, type=int,
#                    help='the 10GBE SPEAD payload size, in bytes')
args = parser.parse_args()

polltime = args.polltime
num_spead_headers = 4

feng_hosts = ['roach02091b', 'roach020914',]# 'roach020915', 'roach020922',
#              'roach020921', 'roach020927', 'roach020919', 'roach020925']

feng_hosts = ['roach020915']

feng_hosts = args.hosts.lstrip().rstrip().replace(' ', '').split(',')

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
        raise RuntimeError('Cannot have an fengine with no 10gbe cores?')
    print '%s: found %i 10gbe core%s.' % (host, numgbes, '' if numgbes == 1 else 's')
    ffpgas.append(feng_fpga)

def fengine_gbe(fpga):
    cores = fpga.tengbes
    returndata = {}
    for core in cores:
        returndata[core.name] = core.read_counters()
    return returndata

def get_fpga_data(fpga):
    data = {}
    data['gbe'] = fengine_gbe(fpga)
    return data

# work out tables for each fpga
fpga_headers = []
for cnt, fpga in enumerate(ffpgas):
    gbedata = get_fpga_data(fpga)['gbe']
    core0_regs = {}
    gbe0 = gbedata.keys()[0]
    for direc in ['tx', 'rx']:
        core0_regs[direc] = [key.replace(gbe0, 'gbe') for key in gbedata[gbe0][direc].keys()]
    if cnt == 0:
        master_list = core0_regs.copy()
    for core in gbedata:
        core_regs = {}
        for direc in ['tx', 'rx']:
            core_regs[direc] = [key.replace(core, 'gbe') for key in gbedata[core][direc].keys()]
        for direc in ['tx', 'rx']:
            if sorted(core0_regs[direc]) != sorted(core_regs[direc]):
                raise RuntimeError('Not all GBE cores for FPGA %s have the same support registers. Problem.', fpga.host)
    fpga_headers.append(core0_regs)

master_list = fpga_headers[0]
all_the_same = True
for cnt, fpga in enumerate(ffpgas):
    for direc in ['tx', 'rx']:
        if sorted(master_list[direc]) != sorted(fpga_headers[cnt][direc]):
            all_the_same = False
            raise RuntimeError('Warning: GBE cores across given FPGAs are NOT configured the same!')
if all_the_same:
    fpga_headers = [fpga_headers[0]]

fpga_headers = [{'rx': ['gbe_rxctr', 'gbe_rxofctr', 'gbe_rxerrctr', 'gbe_rxbadctr'], 'tx': ['gbe_txerrctr', 'gbe_txfullctr', 'gbe_txofctr', 'gbe_txctr', 'gbe_txvldctr']}]

import signal
def signal_handler(sig, frame):
    print sig, frame
    for fpga in ffpgas:
        fpga.disconnect()
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
            scroller.add_line('Polling %i fengine%s every %s - %is elapsed.' %
                (len(ffpgas), '' if len(ffpgas) == 1 else 's',
                'second' if polltime == 1 else ('%i seconds' % polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
            start_pos = 30
            pos_increment = 20
            if len(fpga_headers) == 1:
                scroller.add_line('Host', 0, 1, absolute=True)
                for reg_list in fpga_headers[0].values():
                    for reg in reg_list:
                        scroller.add_line(reg, start_pos, 1, absolute=True)
                        start_pos += pos_increment
                scroller.set_ypos(2)
                scroller.set_ylimits(ymin=2)
            else:
                scroller.set_ypos(1)
                scroller.set_ylimits(ymin=1)
            for ctr, fpga in enumerate(ffpgas):
                fpga_data = get_fpga_data(fpga)
                scroller.add_line(fpga.host)
                start_pos = 30
                pos_increment = 20
                for core, value in fpga_data['gbe'].items():
                    scroller.add_line(core, 5)
                    for direc, reg_list in fpga_headers[0].items():
                        for reg in reg_list:
                            if start_pos < 200:
                                scroller.add_line('%10d' % fpga_data['gbe'][core][direc][reg.replace('gbe', core)], start_pos, scroller.get_current_line() - 1)
                                scroller.add_line(reg, start_pos, 1, absolute=True)
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
