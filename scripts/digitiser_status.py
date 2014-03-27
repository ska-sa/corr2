#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given digitiser.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import logging, time, curses, argparse, copy

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from corr2.digitiser import Digitiser
import corr2.scroll as scroll

parser = argparse.ArgumentParser(description='Display information about a MeerKAT digitiser.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hostname', type=str, action='store',
                    help='the hostname of the digitiser')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll digitiser data, in seconds')
parser.add_argument('-s', '--payloadsize', dest='payloadsize', action='store',
                    default=5120, type=int,
                    help='the 10GBE SPEAD payload size, in bytes')
args = parser.parse_args()

polltime = args.polltime
num_spead_headers = 4
bytes_per_packet = args.payloadsize + (num_spead_headers*8)

# create the device and connect to it
digitiser_fpga = Digitiser(args.hostname, 7147)
time.sleep(0.2)
if not digitiser_fpga.is_connected():
    digitiser_fpga.connect()
digitiser_fpga.test_connection()
digitiser_fpga.get_system_information()

# is there a 10gbe core in the design?
numgbes = len(digitiser_fpga.device_names_by_container('tengbes'))
if not numgbes == 4:
    raise RuntimeError('A digitiser must have four 10Gbe cores.')
print 'Found %i ten gbe core%s:' % (numgbes, '' if numgbes == 1 else 's')

def get_coredata(fpga):
    '''Get the updated counters for all the cores.
    '''
    cdata = {}
    for device in fpga.tengbes.keys():
        data = fpga.devices[device].read_counters()
        cdata[device] = data
    return cdata

def reset_counters(fpga, cdata):
    '''Reset all core counters.
    '''
    for device in fpga.tengbes.keys():
        for direction in ['tx', 'rx']:
            for key in cdata[device][direction].keys():
                cdata[device][direction][key] = 0
    return cdata

def print_top_str(stdscr, host, starttime):
    '''Print the top string of the display.
    '''
    stdscr.move(1, 2)
    stdscr.clrtoeol()
    stdscr.addnstr(1, 2,
        'Polling %i core%s on %s every %i second%s - %is elapsed.' %
        (numgbes, '' if numgbes == 1 else 's', host, polltime,
        '' if polltime == 1 else 's', time.time() - starttime), 100,
        curses.A_REVERSE)

def print_bottom_str(stdscr):
    '''Control instructions at the bottom of the screen.'''
    (y, _) = stdscr.getmaxyx()
    stdscr.addstr(y - 2, 2, 'q to quit, r to refresh', curses.A_REVERSE)

def print_headers(stdscr):
    '''Print the table headers.
    '''
    stdscr.addstr(2, 2, 'core')
    stdscr.addstr(2, 20, 'ip')
    stdscr.addstr(2, 40, 'tap_running')
    stdscr.addstr(2, 60, 'packets/sec')
    stdscr.addstr(2, 80, 'rate, Gb/sec')
    stdscr.addstr(2, 100, 'errors/sec')
    stdscr.addstr(2, 120, 'full count')
    stdscr.addstr(2, 140, 'overflow count')
    stdscr.addstr(2, 160, 'packet count')
    stdscr.addstr(2, 180, 'last_time')

def handle_keys(keyval, dig_fpga):
    ''' Handle some key presses.
    '''
    if (keyval == ord('q')) or (keyval == ord('Q')):
        return (True, False)
    elif (keyval == ord('r')) or (keyval == ord('R')):
        #reset_counters(dig_fpga)
        return (False, True)
    return (False, False)

def mainfunc(stdscr, dig_fpga, coredata):
    '''The main screen-drawing loop of the program.
    '''
    device_list = dig_fpga.tengbes.keys()
    for device in device_list:
        if not (coredata[device]['tx'].has_key(device + '_txctr') and
                coredata[device]['tx'].has_key(device + '_txerrctr') and
                coredata[device]['tx'].has_key(device + '_txofctr') and
                coredata[device]['tx'].has_key(device + '_txfullctr') and
                coredata[device]['tx'].has_key(device + '_txvldctr')):
            raise RuntimeError('Core %s was not built with the required debug counters.', device)

    starttime = time.time()
    curses.use_default_colors()
    curses.curs_set(0)
    stdscr.clear()
    stdscr.box()
    stdscr.nodelay(1)
    print_top_str(stdscr, dig_fpga.host, starttime)
    print_bottom_str(stdscr)
    print_headers(stdscr)
    # core names
    for ctr, core in enumerate(device_list):
        line = 3 + ctr
        stdscr.addstr(line, 2, '%s' % core)
    dig_fpga.registers['control'].write(clr_status='pulse')
    # loop and read & print the core info
    last_render = time.time() - (polltime + 1)
    coredata_old = copy.deepcopy(coredata)
    while True:
        (quit_pressed, force_render) = handle_keys(stdscr.getch(), dig_fpga)
        if quit_pressed:
            break
        if force_render:
            last_render = time.time() - (polltime + 1)
        if time.time() > last_render + polltime:
            print_top_str(stdscr, dig_fpga.host, starttime)
            loop_time = dig_fpga.get_current_time()
            for ctr, core in enumerate(device_list):
                line = 3 + ctr
                stdscr.move(line, 20)
                stdscr.clrtoeol()
                # update the core counter data
                newdata = get_coredata(dig_fpga)
                for device in device_list:
                    for direction in ['tx', 'rx']:
                        for key in coredata[device][direction].keys():
                            coredata[device][direction][key] = newdata[device][direction][key]
                # and update the table
                packets = coredata[core]['tx'][core + '_txctr'] - \
                            coredata_old[core]['tx'][core + '_txctr']
                errors = coredata[core]['tx'][core + '_txerrctr'] - \
                            coredata_old[core]['tx'][core + '_txerrctr']
                errors = coredata[core]['tx'][core + '_txerrctr']
                rate = packets * (bytes_per_packet * 8) / (1000000000.0 * (time.time() - last_render))
                ipstr = coredata[core]['tap']['ip']
                stdscr.addnstr(line, 20, ipstr, 20)
                stdscr.addnstr(line, 40, 'False' if coredata[core]['tap']['name'] == '' else 'True', 20)
                stdscr.addnstr(line, 60, '%i' % packets, 20)
                stdscr.addnstr(line, 80, '%.2f' % rate, 20)
                stdscr.addnstr(line, 100, '%i' % errors, 20)
                stdscr.addnstr(line, 120, '%i' % coredata[core]['tx'][core + '_txfullctr'], 20)
                stdscr.addnstr(line, 140, '%i' % coredata[core]['tx'][core + '_txofctr'], 20)
                stdscr.addnstr(line, 160, '%i' % coredata[core]['tx'][core + '_txctr'], 20)
                stdscr.addnstr(line, 180, '%i' % loop_time, 20)
            stdscr.refresh()
            last_render = time.time()
            coredata_old = copy.deepcopy(coredata)
        time.sleep(0.1)
    return

# set up the counters
tengbedata = get_coredata(digitiser_fpga)
for tengbecore in digitiser_fpga.tengbes.keys():
    tengbedata[tengbecore]['tap'] = digitiser_fpga.devices[tengbecore].tap_info()
    print '\t', tengbecore
tengbedata = reset_counters(digitiser_fpga, tengbedata)

# start curses after setting up a clean teardown
def teardown():
    '''Clean up before exiting curses.'''
    curses.nocbreak()
    curses.echo()
    curses.endwin()
import signal
def signal_handler(sig, frame):
    '''Handle a os signal.'''
    teardown()
    import sys
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)
curses.wrapper(mainfunc, digitiser_fpga, tengbedata)
teardown()
# end
