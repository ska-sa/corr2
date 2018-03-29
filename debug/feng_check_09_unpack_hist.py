#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Collect the output of a post-unpack snapshot and do an FFT on it.

@author: paulp
"""
import argparse
import sys
import signal
import os
import matplotlib.pyplot as pyplot
import numpy

from casperfpga import utils as fpgautils
from corr2 import utils

parser = argparse.ArgumentParser(description='Display a histogram of the post-coarse delay data.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='le host de fengine')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('--pol', dest='pol', action='store', default=0, type=int,
                    help='polarisation')
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
    HOSTCLASS = CasperFpga
else:
    HOSTCLASS = dcp_fpga.DcpFpga

if 'CORR2INI' in os.environ.keys() and args.hosts == '':
    args.hosts = os.environ['CORR2INI']
hosts = utils.parse_hosts(args.hosts, section='fengine')
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
    if not 'snapcoarse_0_ss' in fpga_.snapshots.names():
        snapshot_missing.append(fpga_.host)
if len(snapshot_missing) > 0:
    print('The following hosts are missing the post-unpack snapshot. Bailing.'
    print(snapshot_missing
    exit_gracefully(None, None)

def get_data():
    """
    Read the snap data from the f-engines
    :return:
    """
    # arm the snaps
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots.snapcoarse_0_ss.arm())
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots.snapcoarse_1_ss.arm())

    # allow them to trigger
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(snapcoarse_arm='pulse'))

    # read the data
    snapdata_p0 = fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots.snapcoarse_0_ss.read(arm=False))
    snapdata_p1 = fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots.snapcoarse_1_ss.read(arm=False))

    try:
        for key, value in snapdata_p0.items():
            if 'data' not in value.keys():
                raise RuntimeError('Did not get p0 snap data from host %s' % key)
    except:
        print(snapdata_p0
        raise RuntimeError('Error getting p0 snap data')
    try:
        for key, value in snapdata_p1.items():
            if 'data' not in value.keys():
                raise RuntimeError('Did not get p1 snap data from host %s' % key)
    except:
        print(snapdata_p1
        raise RuntimeError('Error getting p1 snap data')

    # unpack the data and the timestamps
    _unpacked_data = {}
    for _fpga in snapdata_p0.keys():
        _unpacked_data[_fpga] = {}
        p0_data = snapdata_p0[_fpga]
        p1_data = snapdata_p1[_fpga]
        packettime = (p0_data['extra_value']['data']['time36_msb'] << 4) | p1_data['extra_value']['data']['time36_lsb']
        _unpacked_data[_fpga]['packettime36'] = packettime
        _unpacked_data[_fpga]['packettime48'] = packettime << 12
        p0_unpacked = []
        p1_unpacked = []
        for _ctr, _ in enumerate(p0_data['data']['p0_80']):
            p0_80 = p0_data['data']['p0_80'][_ctr]
            p1_80 = (p0_data['data']['p1_80_msb'][_ctr] << 32) | p1_data['data']['p1_80_lsb'][_ctr]
            p0_unpacked.append(p0_80)
            p1_unpacked.append(p1_80)
        _unpacked_data[_fpga]['p0'] = p0_unpacked[:]
        _unpacked_data[_fpga]['p1'] = p1_unpacked[:]
    return _unpacked_data

def _populate_subplots(data, figure):
    _plot_ctr = 0
    sub_plots = {}
    for fpga in data:
        print('Adding subplot for fpga {}'.format(fpga)
        sub_plots['{}'.format(fpga)] = figure.add_subplot(len(data), 1, _plot_ctr + 1)
        _plot_ctr += 1
    return sub_plots

def plot_func(figure, sub_plots):
    unpacked_data = get_data()
    if len(sub_plots) == 0:
        sub_plots.update(_populate_subplots(unpacked_data, figure))
    for fpga, fpga_data in unpacked_data.items():
        print('%s data started at %d' % (fpga, fpga_data['packettime48']),
        _sbplt = sub_plots['{}'.format(fpga)]
        if args.pol == 0:
            plotdata = fpga_data['p0']
        else:
            plotdata = fpga_data['p1']
        allsamples = utils.AdcData.eighty_to_ten(plotdata)
        _sbplt.cla()
        _sbplt.hist(allsamples, 100, (-0.5, 0.5))
        print('and ended %d samples later. All okay.' % (len(allsamples))
        print('\tMean:  %.5f' % numpy.mean(allsamples)
        print('\tStddev: %.10f' % numpy.std(allsamples)
    pyplot.xlim((-0.5, 0.5))
    figure.canvas.draw()
    figure.canvas.manager.window.after(100, plot_func, figure, sub_plots)

# set up the figure with a subplot to be plotted
fig = pyplot.figure()
subplots = {}
fig.canvas.manager.window.after(100, plot_func, fig, subplots)
pyplot.show()
print('Plot started.'

# wait here so that the plot can be viewed
print('Press Ctrl-C to exit...'
sys.stdout.flush()
import time
while True:
    time.sleep(1)
exit_gracefully(None, None)

# end
