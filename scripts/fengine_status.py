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

#feng_hosts = ['roach02091b', 'roach020914',]# 'roach020915', 'roach020922',
##              'roach020921', 'roach020927', 'roach020919', 'roach020925']
#feng_hosts = ['roach020915']

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
    '''Get 10gbe data from the fpga.
    '''
    cores = fpga.tengbes
    returndata = {}
    for core in cores:
        returndata[core.name] = core.read_counters()
    return returndata

def fengine_rxtime(fpga):
    return (fpga.registers.local_time_msw.read()['data']['reg'] << 32) + \
        fpga.registers.local_time_lsw.read()['data']['reg']

def get_fpga_data(fpga):
    data = {}
    data['gbe'] = fengine_gbe(fpga)
    data['rxtime'] = fengine_rxtime(fpga)
    return data

# work out tables for each fpga
fpga_headers = []
master_list = []
for cnt, fpga in enumerate(ffpgas):
    gbedata = get_fpga_data(fpga)['gbe']
    core0_regs = {}
    gbe0 = gbedata.keys()[0]
    core0_regs = [key.replace(gbe0, 'gbe') for key in gbedata[gbe0].keys()]
    if cnt == 0:
        master_list = core0_regs[:]
    for core in gbedata:
        core_regs = {}
        core_regs = [key.replace(core, 'gbe') for key in gbedata[core].keys()]
        if sorted(core0_regs) != sorted(core_regs):
            raise RuntimeError('Not all GBE cores for FPGA %s have the same support registers. Problem.', fpga.host)
    fpga_headers.append(core0_regs)

all_the_same = True
for cnt, fpga in enumerate(ffpgas):
    if sorted(master_list) != sorted(fpga_headers[cnt]):
        all_the_same = False
        raise RuntimeError('Warning: GBE cores across given FPGAs are NOT configured the same!')
if all_the_same:
    fpga_headers = [fpga_headers[0]]

fpga_headers = [['gbe_rxctr', 'gbe_rxofctr', 'gbe_rxerrctr', 'gbe_rxbadctr', 'gbe_txerrctr', 'gbe_txfullctr', 'gbe_txofctr', 'gbe_txctr', 'gbe_txvldctr']]

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
                scroller.add_line(fpga.host + ' - %12d' % fpga_data['rxtime'])
                for core, core_data in fpga_data['gbe'].items():
                    start_pos = 30
                    pos_increment = 20
                    scroller.add_line(core, 5)
                    for header_register in fpga_headers[0]:
                        core_register_name = header_register.replace('gbe', core)
                        if start_pos < 200:
                            regval = '%10d' % core_data[core_register_name]['data']['reg']
                            scroller.add_line(regval, start_pos, scroller.get_current_line() - 1) # all on the same line
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
