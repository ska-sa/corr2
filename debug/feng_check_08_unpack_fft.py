#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Collect the output of a post-unpack snapshot and do an FFT on it.

@author: paulp
"""
import argparse
import sys
import signal

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(description='Perform an FFT on the post-coarse delay data.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, if you do not want all the fengine hosts in the config file')
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument('--integrate', dest='integrate', action='store', default=-1, type=int,
                    help='integrate n successive spectra, -1 is infinite')
parser.add_argument('--number', dest='number', action='store', default=-1, type=int,
                    help='number of spectra/integrations to fetch, -1 is unlimited')
parser.add_argument('--linear', dest='linear', action='store_true', default=False,
                    help='plot linear, not log')
parser.add_argument('--integ', dest='integrations', action='store', type=int, default=1,
                    help='number of spectra to integrate, -1 is infinate')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
parser.add_argument('--checktvg', dest='checktvg', action='store_true', default='',
                    help='if the TVG is enabled on the digitiser, check TVG data instead of generating'
                         'an FFT on the data')
args = parser.parse_args()

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

# read the config
config = utils.parse_ini_file(args.config)

EXPECTED_FREQS = int(config['fengine']['n_chans'])

# parse the hosts
if args.hosts != '':
    hosts = utils.parse_hosts(args.hosts)
else:
    hosts = utils.parse_hosts(config, section='fengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

def exit_gracefully(signal, frame):
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
snapshot_missing = []
for fpga_ in fpgas:
    if 'snap_adc0_ss' not in fpga_.snapshots.names():
        snapshot_missing.append(fpga_.host)
if len(snapshot_missing) > 0:
    print 'The following hosts are missing the post-unpack snapshot. Bailing.'
    print snapshot_missing
    exit_gracefully(None, None)

def get_data():
    # read the data
    snapdata_p0 = fpgautils.threaded_fpga_operation(fpgas, 10,
                                                    lambda fpga_: fpga_.snapshots.snap_adc0_ss.read(man_trig=True))
    snapdata_p1 = fpgautils.threaded_fpga_operation(fpgas, 10,
                                                    lambda fpga_: fpga_.snapshots.snap_adc1_ss.read(man_trig=True))
    try:
        for key, value in snapdata_p0.items():
            if 'data' not in value.keys():
                raise RuntimeError('Did not get p0 snap data from host %s' % key)
    except:
        print snapdata_p0
        raise RuntimeError('Error getting p0 snap data')
    try:
        for key, value in snapdata_p1.items():
            if 'data' not in value.keys():
                raise RuntimeError('Did not get p1 snap data from host %s' % key)
    except:
        print snapdata_p1
        raise RuntimeError('Error getting p1 snap data')

    # unpack the data
    up_data = {_fpga: {'p0': [], 'p1': []} for _fpga in snapdata_p0}
    for fpga in snapdata_p0.keys():
        p0_data = snapdata_p0[fpga]
        p1_data = snapdata_p1[fpga]
        p0_unpacked = []
        p1_unpacked = []
        for ctr, _ in enumerate(p0_data['data']['d0']):
            for word_ctr in range(0, 8):
                p0_unpacked.append(p0_data['data']['d{}'.format(word_ctr)][ctr])
                p1_unpacked.append(p1_data['data']['d{}'.format(word_ctr)][ctr])
        up_data[fpga]['p0'] = p0_unpacked[:]
        up_data[fpga]['p1'] = p1_unpacked[:]
    return up_data

if args.checktvg:
    raise NotImplementedError
    def eighty_to_tvg(eighty):
        timeramp = eighty >> 32
        dataramp = (eighty & 0xffffffff) >> 1
        pol = eighty & 0x01
        return timeramp, dataramp, pol
    unpacked_data = get_data()
    for fpga, fpga_data in unpacked_data.items():
        print '%s data started at time %d' % (fpga, fpga_data['packettime48']),
        timep0 = eighty_to_tvg(fpga_data['p0'][0])[0]
        timep1 = eighty_to_tvg(fpga_data['p1'][0])[0]
        assert timep0 == timep1, 'p0 and p1 start times do not agree, %d - %d' % (timep0, timep1)
        assert fpga_data['packettime48'] == timep0, 'First time %d is not packet time %d?' % \
                                                    (timep0, fpga_data['packettime48'])
        for pol_data in [(fpga_data['p0'], 0), (fpga_data['p1'], 1)]:
            lasttime = timep0 - 8
            lastdata = -1
            ctr = 0
            for pdata in pol_data[0]:
                timestamp, dataramp, pol = eighty_to_tvg(pdata)
                # print ctr, timestamp, dataramp, pol
                assert pol == pol_data[1], 'pol%d is not %d?' % (pol_data[1], pol_data[1])
                assert timestamp == lasttime + 8, 'ctr_%d: Time stepped from %d to %d diff(%d)?' % \
                                                  (ctr, lasttime, timestamp, timestamp - lasttime)
                lasttime = timestamp
                if (dataramp == 0) and (lastdata == 511):
                    lastdata = -1
                assert dataramp == lastdata + 1, 'ctr_%d: Data ramp went from %d to %d?' % (ctr, lastdata, dataramp)
                lastdata = dataramp
                ctr += 1
        print 'and ended at %d %d samples later. All okay.' % (lasttime, ctr)
else:
    import numpy
    import matplotlib.pyplot as pyplot
    import time

    def plot_func(figure, sub_plots, idata, ictr, pctr):
        unpacked_data = get_data()
        ictr += 1
        for fpga, fpga_data in unpacked_data.items():
            # print '%i: %s data started at %d' % (pctr, fpga, fpga_data['packettime48']),
            if fpga not in idata.keys():
                idata[fpga] = {}
            for polctr, pol in enumerate(['p0', 'p1']):
                pol_samples = fpga_data[pol]
                EXPECTED_FREQS = len(pol_samples) / 2
                if pol not in idata[fpga].keys():
                    idata[fpga][pol] = EXPECTED_FREQS * [0]
                # print 'A snapshot of length %i gave a sample array of length %i' % (len(pol_data[0]), len(allsamples))
                fftdata = numpy.fft.fft(pol_samples)
                # print 'The fft was then length %i' % len(fftdata)
                showdata = EXPECTED_FREQS * [0]
                for ctr, sample in enumerate(fftdata[:EXPECTED_FREQS]):
                    showdata[ctr] = pow(sample.real, 2) + pow(sample.imag, 2)
                # print 'and showdata ended up being %i' % len(showdata)
                # showdata = numpy.abs()
                # showdata = showdata[len(showdata)/2:]
                for ctr, _ in enumerate(showdata):
                    idata[fpga][pol][ctr] += showdata[ctr]
            # print 'and ended %d samples later. All okay.' % (len(pol_samples))
        # actually draw the plots
        for fpga_ctr, intdata in enumerate(idata.values()):
            sub_plots[fpga_ctr].cla()
            sub_plots[fpga_ctr].set_title(idata.keys()[fpga_ctr])
            for ctr, data in enumerate(intdata.values()):
                # print fpga_ctr, ctr, len(data)
                if args.linear:
                    sub_plots[fpga_ctr].plot(data)
                else:
                    sub_plots[fpga_ctr].semilogy(data)

                # subplots[0].set_title('ADC1 (V Pol): Time Domain [ns], Peak ADC Sample %i, Peak Power %3.3f [dBm], Integrated Power %3.3f [dBm]'%(peak_adc_sample0,spectrum0_power_peak,spectrum0_power_int))
                # subplots[0].set_ylabel('ADC Amplitude [raw]')
                # subplots[0].grid(True)

        figure.canvas.draw()
        if ictr == args.integrate and args.integrate > 0:
            idata = {}
            ictr = 0
            pctr += 1
        if pctr == args.number and args.number > 0:
            return
        fig.canvas.manager.window.after(10, plot_func, figure, sub_plots, idata, ictr, pctr)

    # set up the figure with a subplot to be plotted
    unpacked_data = get_data()
    fig = pyplot.figure()
    subplots = []
    num_plots = len(unpacked_data.keys())
    for p in range(num_plots):
        sub_plot = fig.add_subplot(num_plots, 1, p+1)
        subplots.append(sub_plot)
    integrated_data = {}
    integration_counter = 0
    plot_counter = 0
    fig.canvas.manager.window.after(10, plot_func, fig, subplots, integrated_data, integration_counter, plot_counter)
    pyplot.show()
    print 'Plot started.'

# wait here so that the plot can be viewed
print 'Press Ctrl-C to exit...'
sys.stdout.flush()
import time
while True:
    time.sleep(1)

# end
