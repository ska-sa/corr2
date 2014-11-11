#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given xengine.

Created on Fri Jan  3 10:40:53 2014

@author: paulp
"""
import sys
import time
import argparse

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
import casperfpga.scroll as scroll
from corr2 import utils
from casperfpga.tengbe import ip2str

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
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

polltime = args.polltime

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

hosts = utils.parse_hosts(args.hosts, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

#hosts = ['roach02091b', 'roach020914', 'roach020958', 'roach020922']

# create the devices and connect to them
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
registers_missing = []
max_hostname = -1
for fpga_ in fpgas:
    max_hostname = max(len(fpga_.host), max_hostname)
    freg_error = False
    for necreg in ['txip0', 'txip1', 'txip2', 'txip3', 'txpport01', 'txpport23']:
        if necreg not in fpga_.registers.names():
            freg_error = True
            continue
    if freg_error:
        registers_missing.append(fpga_.host)
        continue
if len(registers_missing) > 0:
    print 'The following hosts are missing necessary registers. Bailing.'
    print registers_missing
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    raise RuntimeError

if args.rstcnt:
    if 'unpack_cnt_rst' in fpgas[0].registers.control.field_names():
        fpgautils.threaded_fpga_operation(fpgas, 10,
                                      lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse',
                                                                                  unpack_cnt_rst='pulse'))
    else:
        fpgautils.threaded_fpga_operation(fpgas, 10,
                                      lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse',
                                                                                  up_cnt_rst='pulse'))
tx_ips = {}
for fpga in fpgas:
    tx_ips[fpga.host] = {'ip0': {}, 'ip1': {}, 'ip2': {}, 'ip3': {}, 'port0': {}, 'port1': {}, 'port2': {}, 'port3': {}}
    print fpga.host, ip2str(fpga.registers.iptx_base.read()['data']['reg']), fpga.registers.tx_metadata.read()['data']


def get_fpga_data(fpga):
    txips = {'ip0': {}, 'ip1': {}, 'ip2': {}, 'ip3': {}, 'port0': {}, 'port1': {}, 'port2': {}, 'port3': {}}
    for ctr in range(0, 4):
        txip = fpga.registers['txip%i'%ctr].read()['data']['ip']
        txips['ip%i' % ctr] = txip
    txport = fpga.registers.txpport01.read()['data']
    txport.update(fpga.registers.txpport23.read()['data'])
    for ctr in range(0, 4):
        txips['port%i' % ctr] = txport['port%i'%ctr]
    return txips

import signal
def signal_handler(sig, frame):
    print sig, frame
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
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
                (len(fpgas), '' if len(fpgas) == 1 else 's',
                'second' if polltime == 1 else ('%i seconds' % polltime),
                time.time() - STARTTIME), 0, 0, absolute=True)
            start_pos = 20
            pos_increment = 15
            scroller.set_ypos(newpos=1)
            all_fpga_data = fpgautils.threaded_fpga_operation(fpgas, 10, get_fpga_data)
            for ctr, fpga in enumerate(fpgas):
                fpga_data = all_fpga_data[fpga.host]
                for key, ip_or_port in fpga_data.items():
                    if ip_or_port not in tx_ips[fpga.host][key].keys():
                        tx_ips[fpga.host][key][ip_or_port] = 0
                    tx_ips[fpga.host][key][ip_or_port] += 1
                fpga_data = tx_ips[fpga.host]
                scroller.add_line(fpga.host)
                for ctr in range(0,4):
                    ipstr = '\tip%i: '%ctr
                    ip_addresses = fpga_data['ip%i'%ctr].keys()
                    ip_addresses.sort()
                    cntmin = pow(2,32) - 1
                    cntmax = -1
                    for ip in ip_addresses:
                        cntmin = min([fpga_data['ip%i'%ctr][ip], cntmin])
                        cntmax = max([fpga_data['ip%i'%ctr][ip], cntmax])
                        ipstr += ip2str(ip) + '[%5d], '%fpga_data['ip%i'%ctr][ip]
                    ipstr += 'spread[%2.2f], '%((cntmax-cntmin)/(cntmax*1.0)*100.0)
                    ports = fpga_data['port%i'%ctr].keys()
                    ports.sort()
                    for port in ports:
                        ipstr += str(port) + '[%5d], '%fpga_data['port%i'%ctr][port]
                    scroller.add_line(ipstr)
            scroller.draw_screen()
            last_refresh = time.time()
except Exception, e:
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    scroll.screen_teardown()
    raise

# handle exits cleanly
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
scroll.screen_teardown()
# end
