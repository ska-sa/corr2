#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Collect the output of a post-unpack snapshot and do an FFT on it.

@author: paulp
"""
import argparse
import numpy
import matplotlib.pyplot as pyplot
import time

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
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
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

required_snaps = ['snapquant_ss']

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
snapshot_missing = []
for fpga_ in fpgas:
    for snap in required_snaps:
        if not snap in fpga_.snapshots.names():
            snapshot_missing.append(fpga_.host)
if len(snapshot_missing) > 0:
    print 'The following hosts are missing one or more of the post-quantsnapshots. Bailing.'
    print snapshot_missing
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    raise RuntimeError

# fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.fft_shift.write_int(1023))

# fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse'))
# print fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.sync_ctr.read())
# fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
# import sys
# sys.exit()


def exit_gracefully(sig, frame):
    import sys
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    sys.exit(0)
import signal
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGHUP, exit_gracefully)

while True:

    # arm the snaps
    for snap in required_snaps:
        fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots[snap].arm())

    # allow them to trigger
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(snapquant_arm='pulse'))

    # read the data
    snapdata = {}
    for snap in required_snaps:
        snapdata[snap] = fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots[snap].read(arm=False))

    for fpga in snapdata[required_snaps[0]].keys():
        # reorder the data
        quant_data = snapdata[required_snaps[0]][fpga]['data']
        p0_data = []
        p1_data = []
        for ctr in range(0, len(quant_data['r00'])):
            p0_data.append(numpy.complex(quant_data['r00'][ctr], quant_data['i00'][ctr]))
            p0_data.append(numpy.complex(quant_data['r01'][ctr], quant_data['i01'][ctr]))
            p0_data.append(numpy.complex(quant_data['r02'][ctr], quant_data['i02'][ctr]))
            p0_data.append(numpy.complex(quant_data['r03'][ctr], quant_data['i03'][ctr]))
            p1_data.append(numpy.complex(quant_data['r10'][ctr], quant_data['i10'][ctr]))
            p1_data.append(numpy.complex(quant_data['r11'][ctr], quant_data['i11'][ctr]))
            p1_data.append(numpy.complex(quant_data['r12'][ctr], quant_data['i12'][ctr]))
            p1_data.append(numpy.complex(quant_data['r13'][ctr], quant_data['i13'][ctr]))

        print '%s data is %d points long.' % (fpga, len(p0_data))

        pyplot.interactive(True)
        pyplot.subplot(2,1,1)
        pyplot.cla()
        # pyplot.semilogy(numpy.abs(p0_data))
        pyplot.plot(numpy.abs(p0_data))

        print numpy.mean(p0_data)
        print numpy.mean(p1_data)
        pyplot.subplot(2,1,2)
        pyplot.cla()
        # pyplot.semilogy(numpy.abs(p1_data))
        pyplot.plot(numpy.abs(p1_data))
        pyplot.draw()

        powerdata = numpy.abs(p0_data)
        print '\tMean:   %.10f' % numpy.mean(powerdata[1000:3000])
        print '\tStddev: %.10f' % numpy.std(powerdata[1000:3000])

    time.sleep(1)

# and exit
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')

# end
