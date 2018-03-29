#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Plot the output of the PFB

@author: paulp
"""
import argparse
import numpy
import matplotlib.pyplot as pyplot
import sys
import signal

from casperfpga import utils as fpgautils
from corr2 import utils

parser = argparse.ArgumentParser(description='Display the output of the PFB on an f-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store', default='',
                    help='comma-delimited list of hosts, if you do not want all the fengine hosts in the config file')
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='a corr2 config file, will use $CORR2INI if none given')
parser.add_argument('--pol', dest='pol', action='store', default=0, type=int,
                    help='polarisation, 0 or 1')
parser.add_argument('--num_ints', dest='integrate', action='store', default=-1, type=int,
                    help='integrate n successive spectra, -1 is infinite')
parser.add_argument('--num_accs', dest='number', action='store', default=-1, type=int,
                    help='number of spectra/integrations to fetch, -1 is unlimited')
parser.add_argument('--fftshift', dest='fftshift', action='store', default=-1, type=int,
                    help='the FFT shift to set')
parser.add_argument('--log', dest='log', action='store_true', default=True,
                    help='True for log plots, False for linear')
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

required_snaps = ['snappfb_0_ss', 'snappfb_1_ss']

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
snapshot_missing = []
for fpga_ in fpgas:
    for snap in required_snaps:
        if snap not in fpga_.snapshots.names():
            snapshot_missing.append(fpga_.host)
if len(snapshot_missing) > 0:
    print('The following hosts are missing one or more of the post-pfb snapshots. Bailing.'
    print(snapshot_missing
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
print('Current FFT shift is: ', current_fft_shift

# select the polarisation
fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(snappfb_dsel=args.pol))

loopctr = 0
integrate_ctr = 0

integrated_data = {fpga.host: EXPECTED_FREQS*[0] for fpga in fpgas}
integrated_power = {fpga.host: EXPECTED_FREQS*[0] for fpga in fpgas}

if args.number == -1 and args.integrate == -1:
    looplimit = -1
else:
    looplimit = args.number * args.integrate

while (looplimit < 0) or (loopctr < looplimit):

    # arm the snaps
    for snap in required_snaps:
        fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots[snap].arm())

    # allow them to trigger
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(snappfb_arm='pulse'))

    # read the data
    snapdata = {}
    for snap in required_snaps:
        snapdata[snap] = fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots[snap].read(arm=False))

    fpga_ctr = 0
    for fpga in snapdata[required_snaps[0]].keys():
        # reorder the data
        r0_to_r3 = snapdata[required_snaps[0]][fpga]['data']
        i3 = snapdata[required_snaps[1]][fpga]['data']
        p_data = []
        for ctr in range(0, len(i3['i3'])):
            p_data.append(numpy.complex(r0_to_r3['r0'][ctr], r0_to_r3['i0'][ctr]))
            p_data.append(numpy.complex(r0_to_r3['r1'][ctr], r0_to_r3['i1'][ctr]))
            p_data.append(numpy.complex(r0_to_r3['r2'][ctr], r0_to_r3['i2'][ctr]))
            p_data.append(numpy.complex(r0_to_r3['r3'][ctr], i3['i3'][ctr]))

        # p0_data = range(0, EXPECTED_FREQS*2, 2)
        # p1_data = range(1, EXPECTED_FREQS*2+1, 2)
        spectra_per_snapshot = len(p_data) / EXPECTED_FREQS
        print('%d: %s snap data is %d points long, %d spectra per snapshot.' % (loopctr, fpga, len(p_data), spectra_per_snapshot)

        for spectrum_ctr in range(0, spectra_per_snapshot):
            sindex = spectrum_ctr * EXPECTED_FREQS
            eindex = sindex + EXPECTED_FREQS - 1
            # print(sindex, eindex
            # integrated_data[fpga]['p0'] = [sum(x) for x in zip(integrated_data[fpga]['p0'], p0_data[sindex:eindex])]
            # integrated_data[fpga]['p1'] = [sum(x) for x in zip(integrated_data[fpga]['p1'], p1_data[sindex:eindex])]
            for datactr in range(0, len(integrated_data[fpga])):
                complex_num = p_data[sindex + datactr]
                integrated_data[fpga][datactr] += complex_num
                integrated_power[fpga][datactr] += pow(complex_num.real, 2) + pow(complex_num.imag, 2)
        if args.integrate:
            p_show_data = integrated_power[fpga]
        else:
            p_show_data = p_data[0:EXPECTED_FREQS]
        pyplot.figure(fpga_ctr)
        pyplot.ion()
        pyplot.subplot(1, 1, 1)
        pyplot.cla()

        p_show_data = numpy.array(p_show_data)
        # p_show_data /= (integrate_ctr+1)

        p_show_data = p_show_data[:-10]

        print('\tMean:   %.10f' % numpy.mean(p_show_data[1000:3000])
        print('\tStddev: %.10f' % numpy.std(p_show_data[1000:3000])

        if args.log:
            plt = pyplot.plot([10*numpy.log10(_d) for _d in p_show_data])
        else:
            pyplot.plot(p_show_data)

        # if integrate_ctr == 0:
        #     ymin_max = (numpy.min(p_show_data), numpy.max(p_show_data))

        # pyplot.ylim(ymin_max)

        pyplot.draw()

        if args.integrate != -1:
            if integrate_ctr == args.integrate:
                integrated_data = {fpga.host: EXPECTED_FREQS*[0] for fpga in fpgas}
                integrated_power = {fpga.host: EXPECTED_FREQS*[0] for fpga in fpgas}
                integrate_ctr = 0
            else:
                integrate_ctr += 1

        fpga_ctr += 1

    loopctr += 1

# wait here so that the plot can be viewed
print('Press Ctrl-C to exit...'
sys.stdout.flush()
import time
while True:
    time.sleep(1)

# end
