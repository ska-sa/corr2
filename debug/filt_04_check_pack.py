#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check that the 64-bit packing is working okay.

@author: paulp
"""
import argparse
import sys
import signal
import matplotlib.pyplot as pyplot
import numpy

from corr2.utils import AdcData

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
fpga = CasperFpga(args.host)
fpga.get_system_information()

# check for the required snapshot
if 'packed_p0_ss' not in fpga.snapshots.names():
    raise RuntimeError('ADC0 snap not available!')
if 'packed_p1_ss' not in fpga.snapshots.names():
    raise RuntimeError('ADC1 snap not available!')

def eighty_to_ten_TVG(snapdata):
    ten_bit_samples = []
    for word80 in snapdata:
        eight_samples = []
        for ctr in range(70, -1, -10):
            tenbit = (word80 >> ctr) & 1023
            eight_samples.append(tenbit)
        # eight_samples.reverse()
        ten_bit_samples.extend(eight_samples)
    return ten_bit_samples

def get_data(tvg=False):
    fpga.snapshots.packed_p0_ss.arm()
    fpga.snapshots.packed_p1_ss.arm()
    fpga.registers.ctrl2.write(arm_pack_snap='pulse')
    snapdata_p0 = fpga.snapshots.packed_p0_ss.read(arm=False)['data']['p0']
    snapdata_p1 = fpga.snapshots.packed_p1_ss.read(arm=False)['data']['p0']
    data_p0 = AdcData.sixty_four_to_eighty(snapdata_p0)
    data_p1 = AdcData.sixty_four_to_eighty(snapdata_p1)
    if tvg:
        data_p0 = eighty_to_ten_TVG(data_p0)
        data_p1 = eighty_to_ten_TVG(data_p1)
    else:
        data_p0 = AdcData.eighty_to_ten(data_p0)
        data_p1 = AdcData.eighty_to_ten(data_p1)
    return {'p0': data_p0, 'p1': data_p1}

def plot_func(figure, sub_plots, idata, ictr, pctr):
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
            sub_plots[pol].plot([10*numpy.log10(_d) for _d in idata[pol]])
        LOGGER.info('max for pol {} at {}'.format(pol, idata[pol].index(max(idata[pol][10:]))))
        figure.canvas.draw()
    if ictr >= args.integrate and args.integrate > 0:
        idata = {}
        ictr = 0
        pctr += 1
    if pctr >= args.number and args.number > 0:
        return
    fig.canvas.manager.window.after(100, plot_func, figure, sub_plots, idata, ictr, pctr)

# fpga.registers.ctrl2.write(tvgsel_10_64=True)
#
# d = get_data(tvg=True)
#
# fpga.registers.ctrl2.write(tvgsel_10_64=False)
#
# print(d['p0'][0:1000]
#
# exit_gracefully(None, None)

# set up the figure with a subplot to be plotted
fig = pyplot.figure()
subplots = {'p0': fig.add_subplot(2, 1, 1),
            'p1': fig.add_subplot(2, 1, 2)}
integrated_data = {'p0': FFT_CHANS * [0], 'p1': FFT_CHANS * [0]}
integration_counter = 0
plot_counter = 0
fig.canvas.manager.window.after(100, plot_func, fig, subplots, integrated_data, integration_counter, plot_counter)
pyplot.show()
print('Plot started.'

# wait here so that the plot can be viewed
print('Press Ctrl-C to exit...'
sys.stdout.flush()
import time
while True:
    time.sleep(1)

# end
