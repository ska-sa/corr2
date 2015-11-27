#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Plot the output of the quantiser snapshot

@author: paulp
"""
import argparse
import numpy
import matplotlib.pyplot as pyplot
import sys
import signal

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(description='Display the output of the quantiser on an f-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, if you do not want all the fengine hosts in the config file')
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument('--num_ints', dest='integrate', action='store', default=-1, type=int,
                    help='integrate n successive spectra, -1 is infinite')
parser.add_argument('--num_accs', dest='number', action='store', default=-1, type=int,
                    help='number of spectra/integrations to fetch, -1 is unlimited')
parser.add_argument('--fftshift', dest='fftshift', action='store', default=-1, type=int,
                    help='the FFT shift to set')
parser.add_argument('--linear', dest='linear', action='store_true', default=False,
                    help='plot linear, not log')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
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

required_snaps = ['snap_quant0_ss', 'snap_quant1_ss']

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
snapshot_missing = []
for fpga_ in fpgas:
    for snap in required_snaps:
        if snap not in fpga_.snapshots.names():
            snapshot_missing.append(fpga_.host)
if len(snapshot_missing) > 0:
    print 'The following hosts are missing one or more of the post-quantsnapshots. Bailing.'
    print snapshot_missing
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    raise RuntimeError


def exit_gracefully(_, __):
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

# set the FFT shift
if args.fftshift != -1:
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.fft_shift.write_int(args.fftshift))
current_fft_shift = fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.fft_shift.read())
print 'Current FFT shift is: ', current_fft_shift

# check the size of the snapshot blocks
snapshot_bytes = (2**int(fpgas[0].snapshots.snap_quant0_ss.block_info['snap_nsamples'])) * \
                 (int(fpgas[0].snapshots.snap_quant0_ss.block_info['snap_data_width'])/8)
print 'Snapshot is %i bytes long' % snapshot_bytes
snapshot_samples = (2**int(fpgas[0].snapshots.snap_quant0_ss.block_info['snap_nsamples'])) * 4
print 'Snapshot is %i samples long' % snapshot_samples
loops_necessary = EXPECTED_FREQS / snapshot_samples
print 'Will need to read the snapshot %i times' % loops_necessary


def get_data():
    # read the data
    snapdata = []
    for loop_ctr in range(0, loops_necessary):
        temp_snapdata = {}
        for snap in required_snaps:
            offset = 8*snapshot_bytes*loop_ctr
            # print 'reading at offset %i' % offset
            temp_snapdata[snap] = fpgautils.threaded_fpga_operation(
                fpgas, 10, lambda fpga_: fpga_.snapshots[snap].read(offset=offset))
        snapdata.append(temp_snapdata)

    fpga_data = {key: {'p0': [], 'p1': []} for key in snapdata[0][required_snaps[0]].keys()}
    for fpga in snapdata[0][required_snaps[0]].keys():
        p0_data = []
        p1_data = []
        for loop_ctr in range(0, loops_necessary):
            # reorder the data
            quant0_data = snapdata[loop_ctr][required_snaps[0]][fpga]['data']
            quant1_data = snapdata[loop_ctr][required_snaps[1]][fpga]['data']
            for ctr in range(0, len(quant0_data['real0'])):
                p0_data.append(numpy.complex(quant0_data['real0'][ctr], quant0_data['imag0'][ctr]))
                p0_data.append(numpy.complex(quant0_data['real1'][ctr], quant0_data['imag1'][ctr]))
                p0_data.append(numpy.complex(quant0_data['real2'][ctr], quant0_data['imag2'][ctr]))
                p0_data.append(numpy.complex(quant0_data['real3'][ctr], quant0_data['imag3'][ctr]))
                p1_data.append(numpy.complex(quant1_data['real0'][ctr], quant1_data['imag0'][ctr]))
                p1_data.append(numpy.complex(quant1_data['real1'][ctr], quant1_data['imag1'][ctr]))
                p1_data.append(numpy.complex(quant1_data['real2'][ctr], quant1_data['imag2'][ctr]))
                p1_data.append(numpy.complex(quant1_data['real3'][ctr], quant1_data['imag3'][ctr]))
        print '%s data is %d points long.' % (fpga, len(p0_data))
        assert len(p0_data) == EXPECTED_FREQS, 'Not enough snap data for the number of channels!'
        fpga_data[fpga]['p0'] = p0_data
        fpga_data[fpga]['p1'] = p1_data
    return fpga_data


def plot_func(figure, sub_plots, idata, ictr, pctr):
    data = get_data()
    ictr += 1
    for fpga, fpga_data in data.items():
        p0_data = numpy.abs(fpga_data['p0'])
        p1_data = numpy.abs(fpga_data['p1'])
        if fpga not in idata.keys():
            idata[fpga] = {0: [0] * len(p0_data), 1: [0] * len(p0_data)}
        for ctr in range(0, len(p0_data)):
            idata[fpga][0][ctr] += p0_data[ctr]
            idata[fpga][1][ctr] += p1_data[ctr]
        print '\tMean:   %.10f' % numpy.mean(p0_data[1000:3000])
        print '\tStddev: %.10f' % numpy.std(p0_data[1000:3000])
        # print '\tp0[0]: %.10f' % p0_data[0]
        # print '\tp0[1]: %.10f' % p0_data[1]

    # actually draw the plots
    for fpga_ctr, intdata in enumerate(idata.values()):
        sub_plots[fpga_ctr].cla()
        sub_plots[fpga_ctr].set_title('%s, %i, %i' % (idata.keys()[fpga_ctr], ictr, pctr))
        subplots[fpga_ctr].grid(True)
        for ctr, data in enumerate(intdata.values()):
            if args.linear:
                sub_plots[fpga_ctr].plot(data)
            else:
                sub_plots[fpga_ctr].semilogy(data)
            # subplots[0].set_title('some title')
            # subplots[0].set_ylabel('some label')
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
data = get_data()
fig = pyplot.figure()
subplots = []
num_plots = len(data.keys())
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
