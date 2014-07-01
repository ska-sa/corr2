#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Created on Thu May  8 15:35:52 2014

Check errors on the x-engine.

@author: paulp
"""
import logging, time, argparse

logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.INFO)

from casperfpga import KatcpClientFpga
import casperfpga.scroll as scroll

xhosts = ['roach020921', 'roach020927', 'roach020919', 'roach020925',
          'roach02091a', 'roach02091e', 'roach020923', 'roach020924']

parser = argparse.ArgumentParser(description='Check errors on the x-engines.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of f-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('-r', '--reset_counters', dest='reset_counters', action='store_true',
                    default=False,
                    help='reset f-engine error counters')
args = parser.parse_args()
polltime = args.polltime
reset_counters = args.reset_counters

# init the f-engines
xfpgas = []
for xhost in xhosts:
    fpga = KatcpClientFpga(xhost)
    fpga.get_system_information()
#    fpga.registers.control.write(sys_rst = 'pulse') # breaks other systems for some unknown reason
    if reset_counters:
        fpga.registers.control.write(clr_status='pulse', cnt_rst='pulse')
    xfpgas.append(fpga)

# set up the curses scroll screen
scroller = scroll.Scroll(debug=False)
scroller.screen_setup()
# main program loop
STARTTIME = time.time()
last_refresh = STARTTIME - 3
try:
    # loop forever while check the error registers on the f-engines
    # the output of these registers will ONLY make sense if the d-engine
    # tvg is on.
    while True:
        # get key presses from ncurses
        keypress, character = scroller.on_keypress()
        if keypress == -1:
            break
        elif keypress > 0:
            scroller.draw_screen()
        if time.time() > last_refresh + polltime:
            scroller.clear_buffer()
            scroller.add_line('Polling %i fengine%s every %s - %is elapsed. Any numbers indicate errors.' %
                (len(xfpgas), '' if len(xfpgas) == 1 else 's',
                'second' if polltime == 1 else ('%i seconds' % polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
            scroller.set_ypos(newpos=2)
            for fpga in xfpgas:
                fstring = '%s: ' % fpga.host
                rxcnt0 = fpga.registers.rx_cnt0.read()['data']['reg']
                rxerrcnt0 = fpga.registers.rx_err_cnt0.read()['data']['reg']
                rxcnt1 = fpga.registers.rx_cnt1.read()['data']['reg']
                rxerrcnt1 = fpga.registers.rx_err_cnt1.read()['data']['reg']

                rxtvgerr0 = fpga.registers.rx_tvg_errors_0.read()['data']['reg']
                rxtvgerr1 = fpga.registers.rx_tvg_errors_1.read()['data']['reg']
                rxtvgerr2 = fpga.registers.rx_tvg_errors_2.read()['data']['reg']
                rxtvgerr3 = fpga.registers.rx_tvg_errors_3.read()['data']['reg']

                pkt_reord_cnt0 = fpga.registers.pkt_reord_cnt0.read()['data']['reg']
                pkt_reord_err0 = fpga.registers.pkt_reord_err0.read()['data']['reg']
                last_missing_ant0 = fpga.registers.last_missing_ant0.read()['data']['reg']
                pkt_reord_cnt1 = fpga.registers.pkt_reord_cnt1.read()['data']['reg']
                pkt_reord_err1 = fpga.registers.pkt_reord_err1.read()['data']['reg']
                last_missing_ant1 = fpga.registers.last_missing_ant1.read()['data']['reg']
                pkt_reord_cnt2 = fpga.registers.pkt_reord_cnt2.read()['data']['reg']
                pkt_reord_err2 = fpga.registers.pkt_reord_err2.read()['data']['reg']
                last_missing_ant2 = fpga.registers.last_missing_ant2.read()['data']['reg']
                pkt_reord_cnt3 = fpga.registers.pkt_reord_cnt3.read()['data']['reg']
                pkt_reord_err3 = fpga.registers.pkt_reord_err3.read()['data']['reg']
                last_missing_ant3 = fpga.registers.last_missing_ant3.read()['data']['reg']

                fstring += '%10d\t%10d\t%10d\t%10d\t%10d\t%10d\t%10d\t%10d' % \
                    (rxcnt0, rxerrcnt0, rxcnt1, rxerrcnt1,
                     rxtvgerr0, rxtvgerr1, rxtvgerr3, rxtvgerr3)
                scroller.add_line('%s' % fstring)

                fstring = '%s: ' % fpga.host
                fstring += '%10d\t%10d\t%10d\t%10d\t%10d\t%10d' % \
                    (pkt_reord_cnt0, pkt_reord_err0, last_missing_ant0,
                     pkt_reord_cnt1, pkt_reord_err1, last_missing_ant1)
                scroller.add_line('%s' % fstring)

                fstring = '%s: ' % fpga.host
                fstring += '%10d\t%10d\t%10d\t%10d\t%10d\t%10d' % \
                    (pkt_reord_cnt2, pkt_reord_err2, last_missing_ant2,
                     pkt_reord_cnt3, pkt_reord_err3, last_missing_ant3)
                scroller.add_line('%s' % fstring)
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
