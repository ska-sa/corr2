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
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
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

feng_hosts = ['roach02091b', 'roach020914', 'roach020915', 'roach020922']

# create the devices and connect to them
ffpgas = []
for host in feng_hosts:
    feng_fpga = KatcpClientFpga(host)
    feng_fpga.get_system_information()
    if args.rstcnt:
        feng_fpga.registers.control.write(cnt_rst='pulse')
    ffpgas.append(feng_fpga)

def fengine_rxtime(fpga):
    return (fpga.registers.local_time_msw.read()['data']['reg'] << 32) + \
        fpga.registers.local_time_lsw.read()['data']['reg']

def get_fpga_data(fpga):
    data = {}
    data['rxtime'] = fengine_rxtime(fpga)
    data['mcnt_nolock'] = fpga.registers.mcnt_nolock.read_uint()
    fifo_of = fpga.registers.fifo_of.read()['data']
    fifo_pktof = fpga.registers.fifo_pktof.read()['data']
    spead_err = fpga.registers.spead_err.read()['data']
    for ctr in range(0, 4):
        data['fifo_of%d' % ctr] =     fifo_of['input%d' % ctr]
        data['fifo_pktof%d' % ctr] =  fifo_pktof['input%d' % ctr]
        data['spead_err%d' % ctr] =   spead_err['input%d' % ctr]
    return data

data = get_fpga_data(ffpgas[0])
reg_names = data.keys()
reg_names.sort()

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
            start_pos = 20
            pos_increment = 15
            scroller.add_line('Host', 0, 1, absolute=True)
            for reg in reg_names:
                scroller.add_line(reg, start_pos, 1, absolute=True)
                start_pos += pos_increment
            scroller.set_ypos(newpos=2)
            scroller.set_ylimits(ymin=2)
            for ctr, fpga in enumerate(ffpgas):
                fpga_data = get_fpga_data(fpga)
                scroller.add_line(fpga.host)
                start_pos = 20
                pos_increment = 15
                for reg in reg_names:
                    regval = '%10d' % fpga_data[reg]
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
