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

parser = argparse.ArgumentParser(description='Display information about a MeerKAT xengine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of x-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll xengine data, in seconds')
#parser.add_argument('-s', '--payloadsize', dest='payloadsize', action='store',
#                    default=5120, type=int,
#                    help='the 10GBE SPEAD payload size, in bytes')
args = parser.parse_args()

polltime = args.polltime
num_spead_headers = 4

xeng_hosts = args.hosts.lstrip().rstrip().replace(' ', '').split(',')

xeng_hosts = ['roach020921', 'roach020927', 'roach020919', 'roach020925',
          'roach02091a', 'roach02091e', 'roach020923', 'roach020924']

# create the devices and connect to them
xfpgas = []
for host in xeng_hosts:
    xeng_fpga = KatcpClientFpga(host)
    time.sleep(0.3)
    if not xeng_fpga.is_connected():
        xeng_fpga.connect()
    xeng_fpga.test_connection()
    xeng_fpga.get_system_information()
    numgbes = len(xeng_fpga.tengbes)
    if numgbes < 1:
        raise RuntimeError('Cannot have an xengine with no 10gbe cores?')
    print '%s: found %i 10gbe core%s.' % (host, numgbes, '' if numgbes == 1 else 's')
    xfpgas.append(xeng_fpga)

def print_headers(scr):
    '''Print the table headers.
    '''
    scr.addstr(2, 2, 'xhost')
    scr.addstr(2, 20, 'tap')
    scr.addstr(2, 30, 'TX')
    scr.addstr(3, 30, 'cnt')
    scr.addstr(3, 40, 'err')
    scr.addstr(2, 50, 'RX')
    scr.addstr(3, 50, 'cnt')
    scr.addstr(3, 60, 'err')

def xengine_gbe(fpga):
    cores = fpga.tengbes
    returndata = {}
    for core in cores:
        returndata[core.name] = core.read_counters()
    return returndata

def get_fpga_data(fpga):
    data = {}
    data['gbe'] = xengine_gbe(fpga)
    return data

fpga_data = get_fpga_data(xfpgas[0])
print fpga_data

#sys.exit()

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
            scroller.add_line('Polling %i xengine%s every %s - %is elapsed.' %
                (len(xfpgas), '' if len(xfpgas) == 1 else 's',
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
            for ctr, fpga in enumerate(xfpgas):
                fpga_data = get_fpga_data(fpga)
                scroller.add_line(fpga.host)
                for core, value in fpga_data['gbe'].items():
                    scroller.add_line(core, 5)
                    xpos = 30
                    for regname in [core + '_rxctr', core + '_rxerrctr', core + '_txctr', core + '_txerrctr']:
                        try:
                            regval = '%10d' % fpga_data['gbe'][core][regname]['data']['reg']
                        except KeyError:
                            regval = 'n/a'
                        scroller.add_line(regval, xpos, scroller.get_current_line() - 1)
                        xpos += 20
            scroller.draw_screen()
            last_refresh = time.time()
except Exception, e:
    for fpga in xfpgas:
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
for fpga in xfpgas:
    fpga.disconnect()
scroll.screen_teardown()
# end
