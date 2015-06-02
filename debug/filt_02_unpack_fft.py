#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Collect the output of a post-unpack snapshot and do an FFT on it.

@author: paulp
"""
import argparse
import sys
import signal

from casperfpga import katcp_fpga
import matplotlib.pyplot as pyplot
from casperfpga.memory import bin2fp
import numpy

FFT_CHANS = 4096

parser = argparse.ArgumentParser(description='Perform an FFT on the incoming data.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--host', dest='host', type=str, action='store', default='',
                    help='the host to query')
parser.add_argument('--integrate', dest='integrate', action='store', default=-1, type=int,
                    help='integrate n successive spectra, -1 is infinite')
parser.add_argument('--number', dest='number', action='store', default=-1, type=int,
                    help='number of spectra/integrations to fetch, -1 is unlimited')
parser.add_argument('--linear', dest='linear', action='store_true', default=False,
                    help='plot linear, not log')
parser.add_argument('--filtered', dest='filtered', action='store_true', default=False,
                    help='plot filtered data, not raw ADC data')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
parser.add_argument('--checktvg', dest='checktvg', action='store_true', default='',
                    help='if the TVG is enabled on the digitiser, check TVG data instead of generating'
                         'an FFT on the data')
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

    def eighty_to_ten(snapdata):
        ten_bit_samples = []
        for word80 in snapdata:
            for ctr in range(70, -1, -10):
                tenbit = (word80 >> ctr) & 1023
                tbsigned = bin2fp(tenbit, 10, 9, True)
                ten_bit_samples.append(tbsigned)
        return ten_bit_samples

    data_p0 = eighty_to_ten(snapdata_p0['p0'])
    data_p1 = eighty_to_ten(snapdata_p1['p1'])
    return {'p0': data_p0, 'p1': data_p1}

def get_data_filtered():
    snapdata = fpga.snapshots.filtout_ss.read(man_trig=True)['data']
    return snapdata

def plot_func(figure, sub_plots, idata, ictr, pctr):
    if args.filtered:
        unpacked_data = get_data_filtered()
    else:
        unpacked_data = get_data()
    ictr += 1
    for datastart in range(0, len(unpacked_data['p0']), FFT_CHANS*2):
        # LOGGER.info('datastart is {}'.format(datastart))
        for pol in ['p0', 'p1']:
            _data = unpacked_data[pol][datastart:datastart+(FFT_CHANS*2)]
            fftdata = numpy.fft.fft(_data, FFT_CHANS*2)
            showdata = FFT_CHANS * [0]
            for ctr, sample in enumerate(fftdata[:FFT_CHANS]):
                showdata[ctr] = pow(sample.real, 2) + pow(sample.imag, 2)
            for ctr, _ in enumerate(showdata):
                idata[pol][ctr] += showdata[ctr]
    for pol in ['p0', 'p1']:
        sub_plots[pol].cla()
        sub_plots[pol].set_title(pol)
        if args.linear:
            sub_plots[pol].plot(idata[pol])
        else:
            sub_plots[pol].semilogy(idata[pol])
        LOGGER.info('max for pol {} at {}'.format(pol, idata[pol].index(max(idata[pol][10:]))))
        figure.canvas.draw()
    if ictr >= args.integrate and args.integrate > 0:
        idata = {}
        ictr = 0
        pctr += 1
    if pctr >= args.number and args.number > 0:
        return
    fig.canvas.manager.window.after(100, plot_func, figure, sub_plots, idata, ictr, pctr)

# set up the figure with a subplot to be plotted
fig = pyplot.figure()
subplots = {'p0': fig.add_subplot(2, 1, 1),
            'p1': fig.add_subplot(2, 1, 2)}
integrated_data = {'p0': FFT_CHANS * [0], 'p1': FFT_CHANS * [0]}
integration_counter = 0
plot_counter = 0
fig.canvas.manager.window.after(100, plot_func, fig, subplots, integrated_data, integration_counter, plot_counter)
pyplot.show()
print 'Plot started.'

# wait here so that the plot can be viewed
print 'Press Ctrl-C to exit...'
sys.stdout.flush()
import time
while True:
    time.sleep(1)

# end
