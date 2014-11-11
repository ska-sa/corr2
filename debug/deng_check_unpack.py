# -*- coding: utf-8 -*-
"""
Created on Thu May  8 15:35:52 2014

@author: paulp
"""

import time
import argparse

from casperfpga import katcp_fpga

dhost = 'roach020958'
#fhosts = ['roach02091b', 'roach020914', 'roach020915', 'roach020922']

parser = argparse.ArgumentParser(description='Display the data unpack counters on the dengine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of d-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=0.5, type=float,
                    help='time at which to poll dengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
args = parser.parse_args()

fdig = katcp_fpga.KatcpFpga(dhost)
fdig.get_system_information()
if args.rstcnt:
    fdig.registers.control.write(cnt_rst='pulse')

ffs = []
#for fhost in fhosts:
#    fpga = KatcpClientFpga(fhost)
#    fpga.get_system_information()
#    ffs.append(fpga)

start_time = time.time()

while True:
    got_errors = False
    print '%.2f' % (time.time() - start_time),
    for interface in [0,1,2,3]:
        errors = fdig.registers['up_err_%i' % interface].read()['data']
        if (errors['cnt'] > 0) or (errors['time'] > 0) or (errors['timestep'] > 0):
            got_errors = True
            print '%s(%i,%i,%i)' % (fdig.host, errors['cnt'], errors['time'], errors['timestep']),
#    for fpga in ffs:
#        for interface in [0,1,2,3]:
#            err_cnt = fpga.device_by_name('unpack_err_pktcnt%i' % interface).read()['data']['reg']
#            err_time = fpga.device_by_name('unpack_err_pkttime%i' % interface).read()['data']['reg']
#            err_timestep = fpga.device_by_name('unpack_err_timestep%i' % interface).read()['data']['reg']
#            if (err_cnt > 0) or (err_time > 0) or (err_timestep > 0):
#                print '(%i, %i, %i)' % (err_cnt, err_time, err_timestep),
#        for interface in [0,1]:
#            err_cnt = fpga.device_by_name('unpack_err_repktcnt%i' % interface).read()['data']['reg']
#            err_time = fpga.device_by_name('unpack_err_repkttime%i' % interface).read()['data']['reg']
#            err_timestep = fpga.device_by_name('unpack_err_retimestep%i' % interface).read()['data']['reg']
#            if (err_cnt > 0) or (err_time > 0) or (err_timestep > 0):
#                print '(%i, %i, %i)' % (err_cnt, err_time, err_timestep),
    if got_errors == True:
        print ''
    else:
        print '<no errors>'
    time.sleep(args.polltime)

# end
