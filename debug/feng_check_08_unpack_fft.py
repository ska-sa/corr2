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
parser.add_argument('--linear', dest='linear', action='store_true', default=False,
                    help='plot linear, not log')
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
    if not 'snapcoarse_0_ss' in fpga_.snapshots.names():
        snapshot_missing.append(fpga_.host)
if len(snapshot_missing) > 0:
    print 'The following hosts are missing the post-unpack snapshot. Bailing.'
    print snapshot_missing
    exit_gracefully(None, None)


def get_data():
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
        print snapdata_p0
        raise RuntimeError('Error getting p0 snap data')
    try:
        for key, value in snapdata_p1.items():
            if 'data' not in value.keys():
                raise RuntimeError('Did not get p1 snap data from host %s' % key)
    except:
        print snapdata_p1
        raise RuntimeError('Error getting p1 snap data')

    # unpack the data and the timestamps
    unpacked_data = {}
    for fpga in snapdata_p0.keys():
        unpacked_data[fpga] = {}
        p0_data = snapdata_p0[fpga]
        p1_data = snapdata_p1[fpga]
        packettime = (p0_data['extra_value']['data']['time36_msb'] << 4) | p1_data['extra_value']['data']['time36_lsb']
        unpacked_data[fpga]['packettime36'] = packettime
        unpacked_data[fpga]['packettime48'] = packettime << 12
        p0_unpacked = []
        p1_unpacked = []
        for ctr, _ in enumerate(p0_data['data']['p0_80']):
            p0_80 = p0_data['data']['p0_80'][ctr]
            p1_80 = (p0_data['data']['p1_80_msb'][ctr] << 32) | p1_data['data']['p1_80_lsb'][ctr]
            p0_unpacked.append(p0_80)
            p1_unpacked.append(p1_80)
        unpacked_data[fpga]['p0'] = p0_unpacked[:]
        unpacked_data[fpga]['p1'] = p1_unpacked[:]
    return unpacked_data

if args.checktvg:
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
elif True:

    import matplotlib.pyplot as pyplot
    from casperfpga.memory import bin2fp
    import numpy

    def eighty_to_ten(eighty):
        samples = []
        for offset in range(70, -1, -10):
            binnum = (eighty >> offset) & 0x3ff
            samples.append(bin2fp(binnum, 10, 9, True))
        return samples

    def hennoplot(somearg):
        # clear plots
        subplots[0].cla()
        subplots[1].cla()
        subplots[2].cla()
        subplots[3].cla()

        fpga = 'roach02092b'

        num_adc_samples = 8192
        nyquist_zone = 1

        unpacked_data = get_data()

        adc0_raw = []
        for dataword in unpacked_data[fpga]['p0']:
            samples = eighty_to_ten(dataword)
            adc0_raw.extend(samples)
        adc0_raw = numpy.array(adc0_raw)

        adc1_raw = []
        for dataword in unpacked_data[fpga]['p1']:
            samples = eighty_to_ten(dataword)
            adc1_raw.extend(samples)
        adc1_raw = numpy.array(adc1_raw)

        print adc0_raw

        # # calculate spectrum for this ADC snapshot
        # spectrum0 = numpy.abs((numpy.fft.rfft(adc0_raw)))
        # spectrum1 = numpy.abs((numpy.fft.rfft(adc1_raw)))

        #adc_rms_voltage_scale = (0.25*0.707)/512.0 # 250mV peak for 512 counts (500mV pp 1024 counts)
        adc_rms_voltage_scale = (0.25*1.0)/512.0 # 250mV peak for 512 counts (500mV pp 1024 counts)

        spectrum0_voltage = (numpy.abs((numpy.fft.rfft(adc0_raw*adc_rms_voltage_scale)))/(num_adc_samples * 1.0))
        spectrum0_power = ((spectrum0_voltage*spectrum0_voltage)/50.0)
        spectrum0_power_peak = 10*numpy.log10(1000*numpy.max(spectrum0_power)) + 3.0
        #print spectrum0_power_peak
        spectrum0_power_int = 10*numpy.log10(1000*numpy.sum(spectrum0_power)) + 3.0
        #print spectrum0_power_int

        spectrum1_voltage = (numpy.abs((numpy.fft.rfft(adc1_raw*adc_rms_voltage_scale)))/(num_adc_samples * 1.0))
        spectrum1_power = ((spectrum1_voltage*spectrum1_voltage)/50.0)
        spectrum1_power_peak = 10*numpy.log10(1000*numpy.max(spectrum1_power)) + 3.0
        #print spectrum1_power_peak
        spectrum1_power_int = 10*numpy.log10(1000*numpy.sum(spectrum1_power)) + 3.0
        #print spectrum1_power_int

        n_points = num_adc_samples
        n_chans = (n_points)/2
        bandwidth = 856e6
        freqs=numpy.arange(n_chans)*float(bandwidth)/n_chans
        period = (1000e6*1.0)/(bandwidth*2) # scale to ns
        time_ticks=numpy.arange(n_points)*float(period)

        if (nyquist_zone == 1):
            bandwidth = 856e6
            freqs=numpy.arange(n_chans)*((float(bandwidth)/n_chans))
            freqs=numpy.add(freqs,bandwidth)
            # no need to flip spectrum anymore - done in firmware
            #spectrum0 = spectrum0[::-1]
            #spectrum1 = spectrum1[::-1]

        peak_adc_sample0 = numpy.max(adc0_raw)
        peak_adc_sample1 = numpy.max(adc1_raw)

        # Time Domain Plot ADC0 (V Pol)
        subplots[0].set_title('ADC1 (V Pol): Time Domain [ns], Peak ADC Sample %i, Peak Power %3.3f [dBm], Integrated Power %3.3f [dBm]'%(peak_adc_sample0,spectrum0_power_peak,spectrum0_power_int))
        subplots[0].set_ylabel('ADC Amplitude [raw]')
        subplots[0].grid(True)
        subplots[0].plot(time_ticks[0:256],adc0_raw[0:256])

        # Spectrum Plot ADC0
        subplots[1].set_title('ADC1 (V Pol): Spectrum [MHz]')
        subplots[1].set_ylabel('Power (arbitrary units)')
        subplots[1].grid(True)
        #subplots[1].semilogy(freqs/1e6,spectrum0[0:n_chans])
        subplots[1].plot(freqs/1e6,10*numpy.log10(1000*(spectrum0_power[0:n_chans])))

        # Time Domain Plot ADC1 (H Pol)
        subplots[2].set_title('ADC2 (H Pol): Time Domain [ns], Peak ADC Sample %i, Peak Power %3.3f [dBm], Integrated Power %3.3f [dBm]'%(peak_adc_sample1,spectrum1_power_peak,spectrum1_power_int))
        subplots[2].set_ylabel('ADC2 Amplitude [raw]')
        subplots[2].grid(True)
        subplots[2].plot(time_ticks[0:256],adc1_raw[0:256])

        # Spectrum Plot ADC1
        subplots[3].set_title('ADC2 (H Pol): Spectrum [MHz]')
        subplots[3].set_ylabel('Power (arbitrary units)')
        subplots[3].grid(True)
        #subplots[3].semilogy(freqs/1e6,spectrum1[0:n_chans])
        subplots[3].plot(freqs/1e6,10*numpy.log10(1000*(spectrum1_power[0:n_chans])))

        fig.canvas.draw()
        fig.canvas.manager.window.after(100, hennoplot ,1)

    #set up the figure with a subplot to be plotted
    fig = pyplot.figure()

    subplots = []
    for p in range(4):
        subPlot = fig.add_subplot(4,1,p+1)
        subplots.append(subPlot)
    fig.canvas.manager.window.after(100, hennoplot, 1)
    pyplot.show()
    print 'Plot started.'
else:
    import numpy
    import matplotlib.pyplot as pyplot
    from casperfpga.memory import bin2fp
    import time

    def eighty_to_ten(eighty):
        samples = []
        for offset in range(70, -1, -10):
            binnum = (eighty >> offset) & 0x3ff
            samples.append(bin2fp(binnum, 10, 9, True))
        return samples

    num_pols = 2
    integrated_data = {}
    pyplot.ion()

    # looplimit = args.number * args.integrate

    looplimit = -1
    loopctr = 0
    starttime = time.time()
    while (looplimit == -1) or (loopctr < looplimit):
        unpacked_data = get_data()
        for fpga, fpga_data in unpacked_data.items():
            print '%i: %s data started at %d' % (loopctr, fpga, fpga_data['packettime48']),
            if fpga not in integrated_data.keys():
                integrated_data[fpga] = {}
            for polctr, pol in enumerate(['p0', 'p1']):
                if pol not in integrated_data[fpga].keys():
                    integrated_data[fpga][pol] = EXPECTED_FREQS * [0]
                pol_samples = []
                for dataword in fpga_data[pol]:
                    samples = eighty_to_ten(dataword)
                    pol_samples.extend(samples)
                assert len(pol_samples) == EXPECTED_FREQS * 2
                # print 'A snapshot of length %i gave a sample array of length %i' % (len(pol_data[0]), len(allsamples))
                fftdata = numpy.fft.fft(pol_samples)
                # print 'The fft was then length %i' % len(fftdata)
                showdata = EXPECTED_FREQS * [0]
                for ctr, sample in enumerate(fftdata[:EXPECTED_FREQS]):
                    showdata[ctr] = pow(sample.real, 2) + pow(sample.imag, 2)
                # print 'and showdata ended up being %i' % len(showdata)
                # showdata = numpy.abs()
                #showdata = showdata[len(showdata)/2:]
                for ctr, _ in enumerate(showdata):
                    integrated_data[fpga][pol][ctr] += showdata[ctr]
                loopctr += 1
            rate = (time.time() - starttime) / (loopctr * 1.0)
            time_remaining = (looplimit - loopctr) * rate
            print 'and ended %d samples later. All okay. %.2fs remaining.' % (len(pol_samples), time_remaining)
        # actually draw the plots
        for intdata in integrated_data.values():
            pyplot.cla()
            for ctr, data in enumerate(intdata.values()):
                #pyplot.subplot(2, 1, ctr+1)
                #pyplot.cla()
                if args.linear:
                    pyplot.plot(data)
                else:
                    pyplot.semilogy(data)
        pyplot.draw()

# wait here so that the plot can be viewed
print 'Press Ctrl-C to exit...'
sys.stdout.flush()
import time
while True:
    time.sleep(1)

# end
