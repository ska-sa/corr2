#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Plot the data sent by the dsim for p0.
"""
import time
import argparse
import os
import sys
import signal
import numpy
from matplotlib import pyplot

from casperfpga import CasperFpga

from corr2 import utils

parser = argparse.ArgumentParser(
    description='Plot outgoing p0 dsim data.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--host', dest='host', type=str, action='store', default='',
    help='the dsim host to query, will override that found in the config'
         'if there is a conflict')
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file, will use $CORR2INI if none given')
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

hostname = ''
if args.host != '':
    hostname = args.host
else:
    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']
    if args.config != '':
        cfg_host_list = utils.parse_hosts(args.config, section='dsimengine')
        hostname = cfg_host_list[0]
if hostname == '':
    raise RuntimeError('Could not find a hostname to use.')
logging.info('Using hostname %s.' % hostname)

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

# make the FPGA object
fpga = utils.feng_script_get_fpga(args)


def get_data():
    """
    Read the raw 80-bit output data from the dsim FPGA design
    :param pol:
    :return:
    """
    _snapname = 'ss_cwg_ss'
    if _snapname not in fpga.snapshots.names():
        logging.error('No output snapshot in this DSIM FPGA design.')
        raise RuntimeError('No output snapshot found in FPGA design.')
    d = fpga.snapshots[_snapname].read(man_trig=True, man_valid=True)['data']
    od = []
    for ctr in range(len(d['d0'])):
        for dctr in range(8):
            od.append(d['d%i' % dctr][ctr])
    return {'p0': od}


def plot_func(figure, sub_plots, idata, ictr, pctr):
    data = get_data()
    ictr += 1

    topstop = plotrange[1] if plotrange[1] != -1 else len(data['p0'])

    p0_data = data['p0'][plotrange[0]:topstop]

    # print('\tMean:   %.10f' % numpy.mean(p0_data[1000:3000])
    # print('\tStddev: %.10f' % numpy.std(p0_data[1000:3000])

    if args.fft:
        plot_data0 = numpy.abs(numpy.fft.fft(p0_data))
    else:
        plot_data0 = p0_data

    if idata is None:
        idata = [[0] * len(plot_data0)]
    for ctr in range(0, len(plot_data0)):
        idata[0][ctr] += plot_data0[ctr]
    if args.integrate != 0:
        plot_data0 = idata[0]

    allzero0 = False
    if not args.linear:
        allzero0 = numpy.sum(plot_data0) == 0

    # actually draw the plots
    for pol in [0]:
        sub_plots[pol].cla()
        sub_plots[pol].set_title('p%i' % pol)
        subplots[pol].grid(True)

    if args.hist:
        sub_plots[0].hist(plot_data0, bins=64, range=(-1.0, 1.0))
    else:
        if args.linear:
            sub_plots[0].plot(plot_data0)
        else:
            if not allzero0:
                sub_plots[0].semilogy(plot_data0)
            else:
                sub_plots[0].plot([0] * len(plot_data0))
    figure.canvas.draw()
    if ictr == args.integrate and args.integrate > 0:
        idata = None
        ictr = 0
        pctr += 1
    fig.canvas.manager.window.after(10, plot_func, figure,
                                    sub_plots, idata, ictr, pctr)

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
    num_plots = len(data.keys())
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
