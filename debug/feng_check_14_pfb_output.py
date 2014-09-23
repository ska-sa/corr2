#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Collect the output of a post-unpack snapshot and do an FFT on it.

@author: paulp
"""
import argparse
import numpy
import matplotlib.pyplot as pyplot

from casperfpga import utils as fpgautils
from casperfpga import katcp_fpga
from casperfpga import dcp_fpga
from corr2 import utils

parser = argparse.ArgumentParser(description='Display the output of the PFB on an f-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of hosts, or a corr2 config file')
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

hosts = utils.parse_hosts(args.hosts, section='fengine')

hosts = ['roach02091b']

if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

required_snaps = ['pfbdata0_0_ss', 'pfbdata0_1_ss', 'pfbdata1_0_ss', 'pfbdata1_1_ss']

# make the FPGA objects
fpgas = fpgautils.threaded_create_fpgas_from_hosts(HOSTCLASS, hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')
snapshot_missing = []
for fpga_ in fpgas:
    for snap in required_snaps:
        if not snap in fpga_.snapshots.names():
            snapshot_missing.append(fpga_.host)
if len(snapshot_missing) > 0:
    print 'The following hosts are missing one or more of the post-pfb snapshots. Bailing.'
    print snapshot_missing
    fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')
    raise RuntimeError


fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.fft_shift.write_int(1023))
# fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(cnt_rst='pulse'))
print fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.sync_ctr.read())

for loopctr in range(0, 10):

    # arm the snaps
    for snap in required_snaps:
        fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots[snap].arm())

    # allow them to trigger
    fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.registers.control.write(unpack_arm='pulse'))

    # read the data
    snapdata = {}
    for snap in required_snaps:
        snapdata[snap] = fpgautils.threaded_fpga_operation(fpgas, 10, lambda fpga_: fpga_.snapshots[snap].read(arm=False))

    for fpga in snapdata[required_snaps[0]].keys():
        # reorder the data
        r0_to_r3 = snapdata[required_snaps[0]][fpga]['data']
        i3 = snapdata[required_snaps[1]][fpga]['data']
        p0_data = []
        #for ctr in range(0, len(r0_to_r3['r0'])):
        for ctr in range(0, len(i3['i3'])):
            p0_data.append(numpy.complex(r0_to_r3['r0'][ctr], r0_to_r3['i0'][ctr]))
            p0_data.append(numpy.complex(r0_to_r3['r1'][ctr], r0_to_r3['i1'][ctr]))
            p0_data.append(numpy.complex(r0_to_r3['r2'][ctr], r0_to_r3['i2'][ctr]))
            p0_data.append(numpy.complex(r0_to_r3['r3'][ctr], i3['i3'][ctr]))

        r0_to_r3 = snapdata[required_snaps[2]][fpga]['data']
        i3 = snapdata[required_snaps[3]][fpga]['data']
        p1_data = []
        #for ctr in range(0, len(r0_to_r3['r0'])):
        for ctr in range(0, len(i3['i3'])):
            p1_data.append(numpy.complex(r0_to_r3['r0'][ctr], r0_to_r3['i0'][ctr]))
            p1_data.append(numpy.complex(r0_to_r3['r1'][ctr], r0_to_r3['i1'][ctr]))
            p1_data.append(numpy.complex(r0_to_r3['r2'][ctr], r0_to_r3['i2'][ctr]))
            p1_data.append(numpy.complex(r0_to_r3['r3'][ctr], i3['i3'][ctr]))

        print '%s data is %d points long.' % (fpga, len(p0_data))

        pyplot.interactive(True)
        pyplot.subplot(2,1,1)
        pyplot.cla()
        pyplot.semilogy(numpy.abs(p0_data))
        # pyplot.plot(numpy.abs(p0_data))

        print numpy.mean(p0_data)
        print numpy.mean(p1_data)
        pyplot.subplot(2,1,2)
        pyplot.cla()
        pyplot.semilogy(numpy.abs(p1_data))
        # pyplot.plot(numpy.abs(p1_data))
        pyplot.draw()

# and exit
fpgautils.threaded_fpga_function(fpgas, 10, 'disconnect')

# end
