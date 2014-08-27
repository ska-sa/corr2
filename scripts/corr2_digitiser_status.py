#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given digitiser.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import time
import curses
import argparse
import copy

from corr2.digitiser import Digitiser
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga

parser = argparse.ArgumentParser(description='Display information about a MeerKAT digitiser.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hostname', type=str, action='store',
                    help='the hostname of the digitiser')
parser.add_argument('-p', '--polltime', dest='polltime', action='store', default=1, type=int,
                    help='time at which to poll digitiser data, in seconds')
parser.add_argument('-s', '--payloadsize', dest='payloadsize', action='store', default=5120, type=int,
                    help='the 10GBE SPEAD payload size, in bytes')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

polltime = args.polltime
num_spead_headers = 4
bytes_per_packet = args.payloadsize + (num_spead_headers*8)

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if args.comms == 'katcp':
    HOSTCLASS = katcp_fpga.KatcpFpga
else:
    HOSTCLASS = dcp_fpga.DcpFpga

# create the device and connect to it
digitiser_fpga = Digitiser(args.hostname, 7147)
time.sleep(0.2)
if not digitiser_fpga.is_connected():
    digitiser_fpga.connect()
digitiser_fpga.test_connection()
digitiser_fpga.get_system_information()

# is there a 10gbe core in the design?
numgbes = len(digitiser_fpga.tengbes)
if not numgbes == 4:
    raise RuntimeError('A digitiser must have four 10Gbe cores.')
print 'Found %i ten gbe core%s:' % (numgbes, '' if numgbes == 1 else 's')


def get_coredata():
    """Get the updated counters for all the cores.
    """
    cdata = {}
    for device in digitiser_fpga.tengbes:
        cdata[device.name] = device.read_counters()
        for key in cdata[device.name].keys():
            cdata[device.name][key]['data'] = cdata[device.name][key]['data']['reg']
    return cdata


def reset_counters(cdata):
    """Reset all core counters.
    """
    for device in digitiser_fpga.tengbes:
        for key in cdata[device.name].keys():
            cdata[device.name][key]['data'] = 0
            cdata[device.name][key]['timestamp'] = -1
    return cdata


def print_top_str(stdscr, host, displaytime):
    """Print the top string of the display.
    """
    stdscr.move(1, 2)
    stdscr.clrtoeol()
    stdscr.addnstr(1, 2,
                   'Polling %i core%s on %s every %i second%s - %is elapsed.' %
                   (numgbes, '' if numgbes == 1 else 's', host, polltime,
                    '' if polltime == 1 else 's', time.time() - displaytime), 100,
                   curses.A_REVERSE)


def print_bottom_str(stdscr):
    """
    Control instructions at the bottom of the screen.
    """
    (y, _) = stdscr.getmaxyx()
    stdscr.addstr(y - 2, 2, 'q to quit, r to refresh', curses.A_REVERSE)


def print_headers(stdscr):
    """
    Print the table headers.
    """
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
    stdscr.addstr(2, 200, 'spead_time')


def handle_keys(keyval):
    """
    Handle some key presses.
    :param keyval:
    :return: boolean quit_pressed, boolean force_render
    """
    if (keyval == ord('q')) or (keyval == ord('Q')):
        return True, False
    elif (keyval == ord('r')) or (keyval == ord('R')):
        #reset_counters(digitiser_fpga)
        return False, True
    return False, False


def mainloop(stdscr):
    counter_data = get_coredata()
    last_render = time.time() - (polltime + 1)
    while True:
        if stdscr is not None:
            quit_pressed, force_render = handle_keys(stdscr.getch())
            if quit_pressed:
                break
            if force_render:
                last_render = time.time() - (polltime + 1)
        if time.time() > last_render + polltime:
            if stdscr is not None:
                print_top_str(stdscr, digitiser_fpga.host, starttime)
            digitiser_time = -1  # digitiser_fpga.get_current_time()
            spead_time = digitiser_time >> 9
            newdata = get_coredata()
            for ctr, core in enumerate(device_list):
                packets = newdata[core][core + '_txctr']['data'] - counter_data[core][core + '_txctr']['data']
                time_elapsed = newdata[core][core + '_txctr']['timestamp'] - \
                               counter_data[core][core + '_txctr']['timestamp']
                errors = newdata[core][core + '_txerrctr']['data'] - counter_data[core][core + '_txerrctr']['data']
                errors = newdata[core][core + '_txerrctr']['data']
                rate = packets * (bytes_per_packet * 8) / (1000000000.0 * time_elapsed)
                ipstr = tap_data[core]['ip']
                line = 3 + ctr
                if stdscr is None:
                    print newdata
                    print ''
                    print counter_data
                if stdscr is not None:
                    stdscr.move(line, 20)
                    stdscr.clrtoeol()
#                    stdscr.addnstr(40, 0, '%.3f'%last_render, 40)
#                    stdscr.addnstr(41, 0, '%.3f'%time.time(), 40)
#                    stdscr.addnstr(42, 0, '%.3f'%polltime, 40)
                    stdscr.addnstr(line, 20, ipstr, 20)
                    stdscr.addnstr(line, 40, 'False' if tap_data[core]['name'] == '' else 'True', 20)
                    stdscr.addnstr(line, 60, '%i' % packets, 20)
                    stdscr.addnstr(line, 80, '%.3f' % rate, 20)
                    stdscr.addnstr(line, 100, '%i' % errors, 20)
                    stdscr.addnstr(line, 120, '%i' % newdata[core][core + '_txfullctr']['data'], 20)
                    stdscr.addnstr(line, 140, '%i' % newdata[core][core + '_txofctr']['data'], 20)
                    stdscr.addnstr(line, 160, '%i' % newdata[core][core + '_txctr']['data'], 20)
                    stdscr.addnstr(line, 180, '%i' % digitiser_time, 20)
                    stdscr.addnstr(line, 200, '%i' % spead_time, 20)
            last_render = time.time()
            if stdscr is not None:
                stdscr.refresh()
            counter_data = copy.deepcopy(newdata)
        time.sleep(0.1)


def mainfunc(stdscr):
    """
    The main screen-drawing loop of the program.
    :param stdscr:
    :return:
    """
    curses.use_default_colors()
    curses.curs_set(0)
    stdscr.clear()
    stdscr.box()
    stdscr.nodelay(1)
    print_top_str(stdscr, digitiser_fpga.host, starttime)
    print_bottom_str(stdscr)
    print_headers(stdscr)
    for ctr, core in enumerate(device_list):
        line = 3 + ctr
        stdscr.addstr(line, 2, '%s' % core)
    digitiser_fpga.registers.control.write(clr_status='pulse')
    mainloop(stdscr)

# set up the counters
counter_data = get_coredata()
tap_data = {}
for core in digitiser_fpga.tengbes.names():
    tap_data[core] = digitiser_fpga.tengbes[core].tap_info()
    print '\t', core
counter_data = reset_counters(counter_data)
starttime = time.time()
device_list = digitiser_fpga.tengbes.names()
for device in device_list:
    if not (((device + '_txctr') in counter_data[device].keys()) and
            ((device + '_txerrctr') in counter_data[device].keys()) and
            ((device + '_txofctr') in counter_data[device].keys()) and
            ((device + '_txfullctr') in counter_data[device].keys()) and
            ((device + '_txvldctr') in counter_data[device].keys())):
        raise RuntimeError('Core %s was not built with the required debug counters.', device)


# start curses after setting up a clean teardown
def teardown():
    """
    Clean up before exiting curses.
    """
    curses.nocbreak()
    curses.echo()
    curses.endwin()


def signal_handler(sig, frame):
    """
    Handle an os signal.
    """
    teardown()
    import sys
    sys.exit(0)
import signal
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)

curses.wrapper(mainfunc)

teardown()
# end
