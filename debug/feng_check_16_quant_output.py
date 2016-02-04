#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Plot the output of the quantiser snapshot.

@author: paulp
"""
import time
import argparse
import os
import sys
import signal
import numpy
from matplotlib import pyplot

from casperfpga import utils as fpgautils

from corr2.fhost_fpga import FpgaFHost
from corr2 import utils

parser = argparse.ArgumentParser(
    description='Display the output of the quantiser on an f-engine.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--fftshift', dest='fftshift', action='store', default=-1, type=int,
    help='the FFT shift to set')
parser.add_argument(
    dest='host', type=str, action='store', default='',
    help='the f-engine host to query, if an int, will be taken positionally '
         'from the config file list of f-hosts')
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

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']
if args.config != '':
    host_list = utils.parse_hosts(args.config, section='fengine')
else:
    host_list = []

try:
    hostname = host_list[int(args.host)]
    logging.info('Got hostname %s from config file.' % hostname)
except ValueError:
    hostname = args.host

# read the config
config = utils.parse_ini_file(args.config)

EXPECTED_FREQS = int(config['fengine']['n_chans'])

required_snaps = ['snap_quant0_ss', 'snap_quant1_ss']

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
fpga = FpgaFHost(hostname)
time.sleep(0.5)
fpga.get_system_information()

# set the FFT shift
if args.fftshift != -1:
    fpga.registers.fft_shift.write_int(args.fftshift)
current_fft_shift = fpga.registers.fft_shift.read()['data']['fft_shift']
print 'Current FFT shift for %s is %i.' % (fpga.host, current_fft_shift)

# check the size of the snapshot blocks
snap0 = fpga.snapshots.snap_quant0_ss
nsamples = int(snap0.block_info['snap_nsamples'])
dwidth = int(snap0.block_info['snap_data_width'])
snapshot_bytes = (2**nsamples) * (dwidth/8)
print 'Snapshot is %i bytes long' % snapshot_bytes
snapshot_samples = (2**nsamples) * 4
print 'Snapshot is %i samples long' % snapshot_samples
loops_necessary = EXPECTED_FREQS / snapshot_samples
print 'Will need to read the snapshot %i times' % loops_necessary


def get_data():
    # read the data
    snapdata = []
    for loop_ctr in range(0, loops_necessary):
        temp_snapdata = {}
        for snap in required_snaps:
            offset = 8 * snapshot_bytes * loop_ctr
            print 'reading %s at offset %i' % (snap, offset)
            temp_snapdata[snap] = fpga.snapshots[snap].read(offset=offset)
        snapdata.append(temp_snapdata)

    fpga_data = {'p0': [], 'p1': []}
    pol_data = [[], []]
    # reorder the data
    for loop_ctr in range(0, loops_necessary):
        quant_data = [snapdata[loop_ctr][required_snaps[0]]['data'],
                      snapdata[loop_ctr][required_snaps[1]]['data']]
        for polctr in range(0, 2):
            for data_ctr in range(0, len(quant_data[0]['real0'])):
                for valctr in range(0, 4):
                    rval = quant_data[polctr]['real%i' % valctr][data_ctr]
                    ival = quant_data[polctr]['imag%i' % valctr][data_ctr]
                    cplx = numpy.complex(rval, ival)
                    pol_data[polctr].append(cplx)

        if len(pol_data[0]) != len(pol_data[1]):
            raise RuntimeError('Unequal length data for p0 and p1?!')
        print '%s data is %d points long.' % (fpga.host, len(pol_data[0]))
        assert len(pol_data[0]) == EXPECTED_FREQS, 'Not enough snap data for ' \
                                                   'the number of channels!'
        fpga_data['p0'] = pol_data[0]
        fpga_data['p1'] = pol_data[1]
    return fpga_data


def plot_func(figure, sub_plots, idata, ictr, pctr):
    data = get_data()
    ictr += 1
    p0_data = numpy.abs(data['p0'])
    p1_data = numpy.abs(data['p1'])
    if idata is None:
        idata = {0: [0] * len(p0_data), 1: [0] * len(p1_data)}
    for ctr in range(0, len(p0_data)):
        idata[0][ctr] += p0_data[ctr]
        idata[1][ctr] += p1_data[ctr]
    print '\tMean:   %.10f' % numpy.mean(p0_data[100:4000])
    print '\tStddev: %.10f' % numpy.std(p0_data[100:4000])
    # actually draw the plots
    for ctr, integd in enumerate(idata.values()):
        plt = sub_plots[ctr]
        plt.cla()
        plt.set_title('%s:%i, %i, %i' % (fpga.host, ctr, ictr, pctr))
        plt.grid(True)
        if args.hist:
            plt.hist(integd, bins=64, range=(-1.0, 1.0))
            idata = None
            ictr = 0
            pctr += 1
        elif args.linear:
            plt.plot(integd)
        else:
            plt.semilogy(integd)
    figure.canvas.draw()
    if ictr == args.integrate and args.integrate > 0:
        idata = None
        ictr = 0
        pctr += 1
    fig.canvas.manager.window.after(10, plot_func, figure, sub_plots,
                                    idata, ictr, pctr)

# set up the figure with a subplot to be plotted
fig = pyplot.figure()
subplots = []
for p in range(2):
    sub_plot = fig.add_subplot(2, 1, p+1)
    subplots.append(sub_plot)
integrated_data = None
integration_counter = 0
plot_counter = 0
fig.canvas.manager.window.after(10, plot_func, fig, subplots,
                                integrated_data,
                                integration_counter, plot_counter)
pyplot.show()
print 'Plot started.'

# wait here so that the plot can be viewed
print 'Press Ctrl-C to exit...'
sys.stdout.flush()
while True:
    time.sleep(1)

# end
