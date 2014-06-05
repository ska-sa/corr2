#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Check the post-FIFO debug registers inside the f-engine unpack block.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys, logging, time, argparse

logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.INFO)

from corr2.katcp_client_fpga import KatcpClientFpga
import corr2.scroll as scroll

parser = argparse.ArgumentParser(description='Display the data unpack counters on the fengine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of f-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
args = parser.parse_args()

polltime = args.polltime

feng_hosts = args.hosts.lstrip().rstrip().replace(' ', '').split(',')

feng_hosts = ['roach02091b', 'roach020914', 'roach020958', 'roach020922']

# create the devices and connect to them
ffpgas = []
for host in feng_hosts:
    feng_fpga = KatcpClientFpga(host)
    feng_fpga.get_system_information()
    if args.rstcnt:
        feng_fpga.registers.control.write(cnt_rst='pulse')
        feng_fpga.registers.control.write(up_cnt_rst='pulse')
    ffpgas.append(feng_fpga)

def get_fpga_data(fpga):
    data = {}
    valid_cnt_fifo0 = fpga.device_by_name('up_validcnt_fifo0').read()['data']
    valid_cnt_fifo1 = fpga.device_by_name('up_validcnt_fifo1').read()['data']
    data['valid_fifo0'] = valid_cnt_fifo0['fifo0']
    data['valid_fifo1'] = valid_cnt_fifo0['fifo1']
    data['valid_fifo2'] = valid_cnt_fifo1['fifo2']
    data['valid_fifo3'] = valid_cnt_fifo1['fifo3']
    fifoof = fpga.registers.up_fifo_of1.read()['data']
    fifopktof = fpga.registers.up_fifo_pktof1.read()['data']
    for ctr in range(0,4):
        data['of%i'%ctr] = fifoof['input%i'%ctr]
        data['pktof%i'%ctr] = fifopktof['input%i'%ctr]
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
                scroller.add_line(new_line=reg.rjust(13), xpos=start_pos, ypos=1, absolute=True)
                start_pos += pos_increment
            scroller.set_ypos(newpos=2)
            scroller.set_ylimits(ymin=2)
            for ctr, fpga in enumerate(ffpgas):
                fpga_data = get_fpga_data(fpga)
                scroller.add_line(fpga.host)
                start_pos = 20
                for reg in reg_names:
                    regval = '%13d' % fpga_data[reg]
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
