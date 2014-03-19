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

from corr2.fengine import Fengine
import corr2.scroll as scroll

parser = argparse.ArgumentParser(description='Display information about a MeerKAT fengine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hostname', type=str, action='store',
                    help='the hostname of the fengine')
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

# create the devices and connect to them
ffpgas = []
for host in feng_hosts:
    feng_fpga = Fengine(host)
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
        returndata[core] = fpga.devices[core].read_counters()
    return returndata

def get_fpga_data(fpga):
    data = {}
    data['gbe'] = fengine_gbe(fpga)
    return data

# set up the curses scroll screen
scroller = scroll.Scroll(debug=False)
scroller.screen_setup()
# main program loop
STARTTIME = time.time()
last_refresh = STARTTIME - 3
try:
    while True:
        # get key presses from ncurses
        keypress = scroller.on_keypress()[0]
        if keypress == -1:
            break
        elif keypress > 0:
            scroller.draw_screen()
        if time.time() > last_refresh + polltime:
            scroller.clear_buffer()
            scroller.add_line('Polling %i fengine%s every %s - %is elapsed.' %
                (len(ffpgas), '' if len(ffpgas) == 1 else 's',
                'second' if polltime == 1 else ('%i seconds' % polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
#            scroller.add_line('hdr1', 10)
#            scroller.add_line('hdr2', 30, scroller.get_current_line())
            scroller.add_line('Host', 0, 1, absolute=True)
            scroller.add_line('GBE_rxcnt', 30, 1, absolute=True)
            scroller.add_line('GBE_rxerror', 50, 1, absolute=True)
            scroller.add_line('GBE_txcnt', 70, 1, absolute=True)
            scroller.add_line('GBE_txerror', 90, 1, absolute=True)
            scroller.set_ypos(2)
            scroller.set_ylimits(ymin=2)
            for ctr, fpga in enumerate(ffpgas):
                fpga_data = get_fpga_data(fpga)
                scroller.add_line(fpga.host)
                for core, value in fpga_data['gbe'].items():
                    scroller.add_line(core, 5)
                    scroller.add_line('%10d' % fpga_data['gbe'][core]['rx'][core + '_rxctr'],       30, scroller.get_current_line() - 1)
                    scroller.add_line('%10d' % fpga_data['gbe'][core]['rx'][core + '_rxerrctr'],    50, scroller.get_current_line() - 1)
                    scroller.add_line('%10d' % fpga_data['gbe'][core]['tx'][core + '_txctr'],       70, scroller.get_current_line() - 1)
                    scroller.add_line('%10d' % fpga_data['gbe'][core]['tx'][core + '_txerrctr'],    90, scroller.get_current_line() - 1)
            scroller.draw_screen()
            last_refresh = time.time()
except Exception, e:
    for fpga in ffpgas:
        fpga.disconnect()
    scroll.screen_teardown()
    raise

# handle exits cleanly
import signal
def signal_handler(signal, frame):
    scroll.screen_teardown()
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)
for fpga in ffpgas:
    fpga.disconnect()
scroll.screen_teardown()
# end
