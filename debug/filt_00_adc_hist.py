#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Collect the output of a post-unpack snapshot and do an FFT on it.

@author: paulp
"""
import argparse
import sys
import signal
import matplotlib.pyplot as pyplot

from casperfpga import katcp_fpga
from corr2.utils import AdcData

parser = argparse.ArgumentParser(description='Show a histogram of the incoming samples.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--host', dest='host', type=str, action='store', default='',
                    help='the host to query')
parser.add_argument('--filtered', dest='filtered', action='store_true', default=False,
                    help='plot filtered data, not raw ADC data')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

import logging
if args.log_level != '':
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)
LOGGER = logging.getLogger(__name__)

def exit_gracefully(signal, frame):
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

# make the FPGA objects
fpga = katcp_fpga.KatcpFpga(args.host)
fpga.get_system_information()

# check for the required snapshot
if 'snapadc0_ss' not in fpga.snapshots.names():
    raise RuntimeError('ADC0 snap not available!')
if 'snapadc1_ss' not in fpga.snapshots.names():
    raise RuntimeError('ADC1 snap not available!')

def get_data():
    fpga.snapshots.snapadc0_ss.arm()
    fpga.snapshots.snapadc1_ss.arm()
    fpga.registers.ctrl2.write(trig_adc_snaps='pulse')
    snapdata_p0 = fpga.snapshots.snapadc0_ss.read(arm=False)['data']
    snapdata_p1 = fpga.snapshots.snapadc1_ss.read(arm=False)['data']
    snapdata_p1['p1'] = []
    for ctr, msb_data in enumerate(snapdata_p0['p1_msb']):
        snapdata_p1['p1'].append((msb_data << 32) + snapdata_p1['p1_lsb'][ctr])
    data_p0 = AdcData.eighty_to_ten(snapdata_p0['p0'])
    data_p1 = AdcData.eighty_to_ten(snapdata_p1['p1'])
    return {'p0': data_p0, 'p1': data_p1}

def get_data_filtered():
    snapdata = fpga.snapshots.filtout_ss.read(man_trig=True)['data']
    return snapdata

def plot_func(figure, sub_plots):
    if args.filtered:
        unpacked_data = get_data_filtered()
    else:
        unpacked_data = get_data()
    for pol in ['p0', 'p1']:
        sub_plots[pol].cla()
        sub_plots[pol].set_title(pol)
        sub_plots[pol].hist(unpacked_data[pol], 49)
        figure.canvas.draw()
    fig.canvas.manager.window.after(100, plot_func, figure, sub_plots)

# set up the figure with a subplot to be plotted
fig = pyplot.figure()
subplots = {'p0': fig.add_subplot(2, 1, 1),
            'p1': fig.add_subplot(2, 1, 2)}
fig.canvas.manager.window.after(100, plot_func, fig, subplots)
pyplot.show()
print 'Plot started.'

# wait here so that the plot can be viewed
print 'Press Ctrl-C to exit...'
sys.stdout.flush()
import time
while True:
    time.sleep(1)

# end
