#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Created on Thu May  8 15:35:52 2014

Set up the TVG on the d-engine and check the error registers on the f-engines
to see if the data being received is correct. Helps to debug ethernet links.

@author: paulp
"""
import logging, time, argparse

logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.INFO)

from casperfpga import KatcpClientFpga
import casperfpga.scroll as scroll

dhost = 'roach020958'
fhosts = ['roach02091b', 'roach020914', 'roach020915', 'roach020922']

parser = argparse.ArgumentParser(description='Test the d-engine to f-engine links.',
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

# switch on the tvg on the d-engine
fdig = KatcpClientFpga(dhost)
fdig.get_system_information()
#fdig.tvg_on()

# init the f-engines
ffpgas = []
for fhost in fhosts:
    fpga = KatcpClientFpga(fhost)
    fpga.get_system_information()
    if reset_counters:
        fpga.registers.control.write(unpack_cnt_rst='pulse')
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
            scroller.add_line('Polling %i fengine%s every %s - %is elapsed. The numbers before the : should all tick over, anything after the : indicate errors.' %
                (len(ffpgas), '' if len(ffpgas) == 1 else 's',
                'second' if polltime == 1 else ('%i seconds' % polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
            scroller.set_ypos(newpos=2)
            for fpga in ffpgas:
                fifo_vcnt0 = fpga.device_by_name('unpack_fifo_vcnt0').read()['data']
                fifo_vcnt1 = fpga.device_by_name('unpack_fifo_vcnt1').read()['data']
                vcnt = fpga.device_by_name('unpack_vcnt').read()['data']
                fstring = '%s [%10d,%10d,%10d,%10d,%10d,%10d]: ' % (fpga.host, fifo_vcnt0['fifo0'], fifo_vcnt0['fifo1'],
                                                                    fifo_vcnt1['fifo2'], fifo_vcnt1['fifo3'], vcnt['arb'], vcnt['reord'])
                for interface in [0, 1, 2, 3]:
                    errors = fpga.device_by_name('unpack_err_%i' % interface).read()['data']
                    if (errors['cnt'] > 0) or (errors['time'] > 0) or (errors['timestep'] > 0):
                        fstring += ('if_%d(%i, %i, %i) ' % (interface, errors['cnt'], errors['time'], errors['timestep']))
                # and check it after the fifo and reorder block
                for interface in [0, 1]:
                    errors = fpga.device_by_name('unpack_err_reorder%i' % interface).read()['data']
                    if (errors['cnt'] > 0) or (errors['time'] > 0) or (errors['timestep'] > 0):
                        fstring += ('reord_pol%d(%i, %i, %i) ' % (interface, errors['cnt'], errors['time'], errors['timestep']))
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
