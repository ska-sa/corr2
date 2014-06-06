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

parser = argparse.ArgumentParser(description='Display reorder debug info on the xengines.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of x-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll xengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
args = parser.parse_args()

polltime = args.polltime

xeng_hosts = args.hosts.lstrip().rstrip().replace(' ', '').split(',')

xeng_hosts = ['roach020921', 'roach020927', 'roach020919', 'roach020925',
          'roach02091a', 'roach02091e', 'roach020923', 'roach020924']

# create the devices and connect to them
xfpgas = []
for host in xeng_hosts:
    fpga = KatcpClientFpga(host)
    fpga.get_system_information()
    if args.rstcnt:
        fpga.registers.control.write(cnt_rst='pulse')
    xfpgas.append(fpga)

def get_fpga_data(fpga):
    data = {}
    for ctr in range(0, 4):
        data['re%i_cnt' % ctr] =  fpga.device_by_name('pkt_reord_cnt%i' % ctr).read()['data']['reg']
        data['re%i_err' % ctr] =  fpga.device_by_name('pkt_reord_err%i' % ctr).read()['data']['reg']
        data['missant%i' % ctr] = fpga.device_by_name('last_missing_ant%i' % ctr).read()['data']['reg']
    for ctr in range(0, 2):
        data['rx%i_cnt' % ctr] =  fpga.device_by_name('rx_cnt%i' % ctr).read()['data']['reg']
        data['rx%i_err' % ctr] =  fpga.device_by_name('rx_err_cnt%i' % ctr).read()['data']['reg']
    return data

data = get_fpga_data(xfpgas[0])
reg_names = data.keys()
reg_names.sort()

import signal
def signal_handler(sig, frame):
    print sig, frame
    for fpga in xfpgas:
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
                (len(xfpgas), '' if len(xfpgas) == 1 else 's',
                'second' if polltime == 1 else ('%i seconds' % polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
            start_pos = 20
            pos_increment = 11
            scroller.add_line('Host', 0, 1, absolute=True)
            for reg in reg_names:
                scroller.add_line(new_line=reg.rjust(9), xpos=start_pos, ypos=1, absolute=True)
                start_pos += pos_increment
            scroller.set_ypos(newpos=2)
            scroller.set_ylimits(ymin=2)
            for ctr, fpga in enumerate(xfpgas):
                fpga_data = get_fpga_data(fpga)
                scroller.add_line(fpga.host)
                start_pos = 20
                pos_increment = 11
                for reg in reg_names:
                    regval = '%9d' % fpga_data[reg]
                    scroller.add_line(regval, start_pos, scroller.get_current_line() - 1) # all on the same line
                    start_pos += pos_increment
            scroller.draw_screen()
            last_refresh = time.time()
except Exception, e:
    for fpga in xfpgas:
        fpga.disconnect()
    scroll.screen_teardown()
    raise

# handle exits cleanly
for fpga in xfpgas:
    fpga.disconnect()
scroll.screen_teardown()
# end
