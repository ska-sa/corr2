#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Read big incoming GBE snapshots to perform a software reorder on the f-engine input.

@author: paulp
"""
import argparse

from casperfpga import katcp_fpga

parser = argparse.ArgumentParser(description='Perform a software reorder on incoming digitiser data'
                                             'from GBE snapshot blocks.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--host', dest='host', type=str, action='store', default='',
                    help='the FPGA host to query')
parser.add_argument('--loglevel', dest='log_level', action='store', default='INFO',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if args.host == '':
    raise RuntimeError('No good carrying on without a host.')

# make the FPGA objects
fpga = katcp_fpga.KatcpFpga(args.host)
fpga.get_system_information()

import time
start_time = time.time()

try:
    loopctr = 0
    while True:

        # arm the snapshots
        fpga.registers.snap_control.write(enable=False)
        fpga.snapshots.s0_ss.arm()
        fpga.snapshots.s1_ss.arm()

        # let them trigger
        fpga.registers.snap_control.write(enable=True)

        # read the snapshots
        d0 = fpga.snapshots.s0_ss.read(arm=False)['data']
        d1 = fpga.snapshots.s1_ss.read(arm=False)['data']
        fpga.registers.snap_control.write(enable=False)

        print 'Read %i words from two snapblocks.' % len(d0['data_in'])

        # convert the data into gbe packets
        from casperfpga import Snap
        gp0 = Snap.packetise_snapdata(d0, 'eof_in')
        gp1 = Snap.packetise_snapdata(d1, 'eof_in')

        # and make lists of the data
        gdata0 = []
        gdata1 = []
        for ctr in range(0, len(gp0)):
            gdata0.append(gp0[ctr]['data_in'])
            gdata1.append(gp1[ctr]['data_in'])

        # make spead processors
        from casperfpga import spead as casperspead
        sp0 = casperspead.SpeadProcessor(4, '64,48', 640, 8)
        sp1 = casperspead.SpeadProcessor(4, '64,48', 640, 8)

        # convert the gbe packets
        sp0.process_data(gdata0)
        sp1.process_data(gdata1)

        times = [[], []]
        last_time = [None, None]
        max_diff = [0, 0]
        out_of_order = [0, 0]
        p0_p1_diff_error = False
        for pkt_ctr in range(0, len(sp0.packets)):
            p0_pkt = sp0.packets[pkt_ctr]
            p1_pkt = sp1.packets[pkt_ctr]
            pkt_time0 = p0_pkt.headers[0x1600]
            pkt_time1 = p1_pkt.headers[0x1600]
            if pkt_time0 in times[0]:
                raise RuntimeError('Duplicate times on p0?!')
            if pkt_time1 in times[1]:
                raise RuntimeError('Duplicate times on p1?!')
            if last_time[0] is not None:
                this_diff = pkt_time0 - last_time[0]
                max_diff[0] = max(max_diff[0], abs(this_diff))
                if this_diff != 8192:
                    out_of_order[0] += 1
            if last_time[1] is not None:
                this_diff = pkt_time1 - last_time[1]
                max_diff[1] = max(max_diff[1], abs(this_diff))
                if this_diff != 8192:
                    out_of_order[1] += 1
            if abs(pkt_time1 - pkt_time0) != 4096:
                print 'pkt_time0(0x%0x) -> pkt_time1(0x%0x) ' \
                      '!= 4096 - 0x%0x' % (pkt_time0,
                                           pkt_time1,
                                           pkt_time1 - pkt_time0)
                p0_p1_diff_error = True
            last_time[0] = pkt_time0
            last_time[1] = pkt_time1
            times[0].append(pkt_time0)
            times[1].append(pkt_time1)

        print 'pol 0 timestamps:'
        print '\tgot %i packets' % len(sp0.packets)
        print '\tranged from 0x%x to 0x%x with ' \
              'a max difference ' \
              'between packets of %i' % (min(times[0]),
                                         max(times[0]),
                                         max_diff[0])
        print '\t%i of them were out of order' % out_of_order[0]

        print 'pol 1 timestamps:'
        print '\tgot %i packets' % len(sp1.packets)
        print '\tranged from 0x%x to 0x%x with ' \
              'a max difference ' \
              'between packets of %i' % (min(times[1]),
                                         max(times[1]),
                                         max_diff[1])
        print '\t%i of them were out of order' % out_of_order[1]

        if out_of_order[0] > 0 or out_of_order[1] > 0:
            break
        if p0_p1_diff_error:
            break

        loopctr += 1


except KeyboardInterrupt:
    pass

stop_time = time.time()

print 'ran %i times in %.3f seconds' % (stop_time - start_time,
                                        loopctr)

import IPython
IPython.embed()

# end
