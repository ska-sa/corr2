#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Plot the ADC data on one or more F-engines
"""
import time
import argparse
import os
import sys
import signal
import numpy

# force the use of the TkAgg backend
import matplotlib
matplotlib.use('TkAgg')

from matplotlib import pyplot

from corr2 import utils
from corr2 import fhost_fpga

parser = argparse.ArgumentParser(
    description='Plot a histogram of the incoming ADC data for a fengine host.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    dest='host', type=str, action='store', default='',
    help='the F-engine host to query, if an int, will be taken positionally '
         'from the config file list of f-hosts')
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument(
    '--bitstream', dest='bitstream', type=str, action='store', default='',
    help='a bitstream for the f-engine hosts (Skarabs need this given '
         'if no config is found)')
parser.add_argument(
    '--range', dest='range', action='store', default='-1,-1',
    help='range to plot, -1 means start/end')
parser.add_argument(
    '--hist', dest='hist', action='store_true', default=False,
    help='plot a histogram of the incoming data')
parser.add_argument(
    '--fft', dest='fft', action='store_true', default=False,
    help='perform a soft FFT on the data before plotting')
parser.add_argument(
    '--integrate', dest='integrate', type=int, action='store', default=0,
    help='fft option - how many spectra should be integrated')
parser.add_argument(
    '--linear', dest='linear', action='store_true', default=False,
    help='plot linear, not log')
parser.add_argument(
    '--noplot', dest='noplot', action='store_true', default=False,
    help='do not plot, dump values to screen')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='INFO',
    help='log level to use, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

# process the range argument
plotrange = [int(a) for a in args.range.split(',')]
if plotrange[0] == -1:
    plotrange = (0, plotrange[1])
if (plotrange[1] != -1) and (plotrange[1] <= plotrange[0]):
    raise RuntimeError('Plot range of %s is incorrect.' % str(plotrange))
plotrange = (int(plotrange[0]), int(plotrange[1]))


def exit_gracefully(_, __):
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

# make the FPGA
fpga = utils.feng_script_get_fpga(args)


def plot_func(figure, sub_plots, idata, ictr, pctr):
    data = get_data()
    ictr += 1

    topstop = plotrange[1] if plotrange[1] != -1 else len(data['p0'].data)

    p0_data = data['p0'].data[plotrange[0]:topstop]
    p1_data = data['p1'].data[plotrange[0]:topstop]

    # print('\tMean:   %.10f' % numpy.mean(p0_data[1000:3000])
    # print('\tStddev: %.10f' % numpy.std(p0_data[1000:3000])

    if args.fft:
        plot_data0 = numpy.abs(numpy.fft.fft(p0_data))
        plot_data1 = numpy.abs(numpy.fft.fft(p1_data))
    else:
        plot_data0 = p0_data
        plot_data1 = p1_data

    if idata is None:
        idata = [[0] * len(plot_data0), [0] * len(plot_data1)]
    for ctr in range(0, len(plot_data0)):
        idata[0][ctr] += plot_data0[ctr]
        idata[1][ctr] += plot_data1[ctr]
    if args.integrate != 0:
        plot_data0 = idata[0]
        plot_data1 = idata[1]

    allzero0 = False
    allzero1 = False
    if not args.linear:
        allzero0 = numpy.sum(plot_data0) == 0
        allzero1 = numpy.sum(plot_data1) == 0

    # actually draw the plots
    for pol in [0, 1]:
        sub_plots[pol].cla()
        sub_plots[pol].set_title('p%i' % pol)
        subplots[pol].grid(True)

    if args.hist:
        sub_plots[0].hist(plot_data0, bins=64, range=(-1.0, 1.0))
        sub_plots[1].hist(plot_data1, bins=64, range=(-1.0, 1.0))
    else:
        if args.linear:
            sub_plots[0].plot(plot_data0)
            sub_plots[1].plot(plot_data1)
        else:
            if not allzero0:
                sub_plots[0].semilogy(plot_data0)
            else:
                sub_plots[0].plot([0] * len(plot_data0))
            if not allzero1:
                sub_plots[1].semilogy(plot_data1)
            else:
                sub_plots[1].plot([0] * len(plot_data1))
    figure.canvas.draw()
    if ictr == args.integrate and args.integrate > 0:
        idata = None
        ictr = 0
        pctr += 1
    fig.canvas.manager.window.after(10, plot_func, figure,
                                    sub_plots, idata, ictr, pctr)


def get_data():
    if 'snap_adc0_ss' not in fpga.snapshots.names():
        d0 = fpga.snapshots.snap_cd0_ss.read()['data']
        d1 = fpga.snapshots.snap_cd1_ss.read()['data']
        rvp0 = []
        rvp1 = []
        for ctr in range(0, len(d0['d0'])):
            for ctr2 in range(8):
                rvp0.append(d0['d%i' % ctr2][ctr])
                rvp1.append(d1['d%i' % ctr2][ctr])
        return {'p0': fhost_fpga.AdcData(-1, rvp0),
                'p1': fhost_fpga.AdcData(-1, rvp1)}
    else:
        return fpga.get_adc_snapshots()

if 'snap_adc0_ss' not in fpga.snapshots.names():
    print('Could not find ADC snapshots, attempting to use '
          'CD snaps instead.')

# set up the figure with a subplot to be plotted
data = get_data()

if args.noplot:
    while True:
        print(data)
        time.sleep(1)
        data = get_data()
else:
    fig = pyplot.figure()
    subplots = []
    num_plots = 2
    for p in range(num_plots):
        sub_plot = fig.add_subplot(num_plots, 1, p+1)
        subplots.append(sub_plot)
    integrated_data = None
    integration_counter = 0
    plot_counter = 0
    fig.canvas.manager.window.after(10, plot_func, fig,
                                    subplots, integrated_data,
                                    integration_counter, plot_counter)
    pyplot.show()
    print('Plot started.')

    # wait here so that the plot can be viewed
    print('Press Ctrl-C to exit...')
    sys.stdout.flush()
    while True:
        time.sleep(1)

