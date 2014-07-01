#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Created on Thu May  8 15:35:52 2014

Check post-CT errors on the f-engine.

@author: paulp
"""
import logging, time, argparse

logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.INFO)

from casperfpga import KatcpClientFpga
import casperfpga.scroll as scroll

fhosts = ['roach02091b', 'roach020914', 'roach020915', 'roach020922']

parser = argparse.ArgumentParser(description='Check post-CT errors on the f-engines.',
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
ffpgas = []
for fhost in fhosts:
    fpga = KatcpClientFpga(fhost)
    fpga.get_system_information()
#    fpga.registers.control.write(sys_rst = 'pulse') # breaks other systems for some unknown reason
    if reset_counters:
        fpga.registers.control.write(cnt_rst = 'pulse')
    ffpgas.append(fpga)

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
                (len(ffpgas), '' if len(ffpgas) == 1 else 's',
                'second' if polltime == 1 else ('%i seconds' % polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
            scroller.set_ypos(newpos=2)
            for fpga in ffpgas:
                fstring = '%s: ' % fpga.host
                mcnt_nolock = fpga.registers.mcnt_nolock.read()['data']['mcnt_nolock']
                data = fpga.registers.ct_cnt.read()['data']
                sync_cnt = data['synccnt']
                valid_cnt = data['validcnt']
                data = fpga.registers.ct_errcnt.read()['data']
                errcnt0 = data['errcnt0']
                parerrcnt0 = data['parerrcnt0']
                errcnt1 = data['errcnt1']
                parerrcnt1 = data['parerrcnt1']
                fstring += 'syncs(%10d)\tvalids(%10d)\tmcnt_nolock(%10d)\tct_errors(%10d, %10d, %10d, %10d)' % (sync_cnt, valid_cnt, mcnt_nolock, errcnt0, parerrcnt0, errcnt1, parerrcnt1)
                scroller.add_line('%s' % fstring)
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
