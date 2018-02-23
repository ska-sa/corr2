#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""
import argparse
import os

from casperfpga import utils as fpgautils
from corr2 import utils
import struct
import time

parser = argparse.ArgumentParser(
    description='Set up the x-engine VACCs.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--hosts', dest='hosts', type=str, action='store',
                    default='', help='comma-delimited list of x-engine hosts')
parser.add_argument('-p', '--polltime', dest='polltime', action='store',
                    default=1, type=int,
                    help='time at which to poll fengine data, in seconds')
parser.add_argument('-r', '--reset_count', dest='rstcnt', action='store_true',
                    default=False,
                    help='reset all counters at script startup')
parser.add_argument('--comms', dest='comms', action='store', default='katcp',
                    type=str, help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, '
                         'DEBUG, ERROR')
args = parser.parse_args()

polltime = args.polltime

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if 'CORR2INI' in os.environ.keys() and args.hosts == '':
    args.hosts = os.environ['CORR2INI']
hosts = utils.parse_hosts(args.hosts, section='xengine')
if len(hosts) == 0:
    raise RuntimeError('No good carrying on without hosts.')

# create the devices and connect to them
hosts = ['roach02081a']
fpgas = fpgautils.threaded_create_fpgas_from_hosts(hosts)
fpgautils.threaded_fpga_function(fpgas, 15, 'get_system_information')

# let it free run so we can reset it
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(valid_sel=False, sync_sel=False), )

# for ctr in range(4):
for ctr in range(1):
    _pref = 'sys%i_vacc_tvg0' % ctr

    _pref = 'vacc_tvg0'

    regname = '%s_n_pulses' % _pref
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers[regname].write_int(10240), )
    # fpgautils.threaded_fpga_operation(
    #     fpgas, 10,
    #     lambda fpga_: fpga_.registers[regname].write_int(777777), )

    regname = '%s_n_per_group' % _pref
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers[regname].write_int(40), )
    regname = '%s_group_period' % _pref
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_: fpga_.registers[regname].write_int(80), )
    # reset the ctrs
    kw = {'vbs_rst%i' % ctr: 'pulse'}
    fpgautils.threaded_fpga_operation(
        fpgas, 10,
        lambda fpga_:
            fpga_.registers.vacctvg_control.write(**kw), )

# set valid select
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(valid_sel=True, pulse_en=False), )

# set sync select
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(sync_sel=True),)

# # set counter select
# fpgautils.threaded_fpga_operation(
#     fpgas, 10,
#     lambda fpga_:
#         fpga_.registers.vacctvg_control.write(ctr_en=True),)

# reset the tvg
fpgautils.threaded_fpga_operation(
    fpgas, 10,
    lambda fpga_:
        fpga_.registers.vacctvg_control.write(reset='pulse'), )

fptr = None


def get_and_check_data(fpga, acc_ctr, bank):

    _qdr_to_read = 'qdr0_memory'

    if not bank:
        # bank 0
        d = fpga.read(_qdr_to_read, 10240 * 8, 0)
    else:
        # bank 1
        d = fpga.read(_qdr_to_read, 10240 * 8, 2**14 * 8)
    d = struct.unpack('>20480I', d)
    dreal = d[0::2]
    dimag = d[1::2]
    errors = False

    ltw = []

    # do the first part until the FIFO 'break'
    for ctr in range(10012):
        dr = dreal[ctr]
        di = dimag[ctr]
        _expval = ctr * (acc_ctr + 1)
        _expval = 1 * (acc_ctr + 1)
        # _expval = 3 * 816
        if (dr != _expval) or (dr != di):
            ltw.append('%i-%i-%i' % (bank, acc_ctr, ctr) +
                       ' (%i,%i)' % (dr, di) +
                       ' ERROR(%i - %i = %i)' % (dr, _expval, dr - _expval) +
                       ' valdiff(%i)\n' % (dr - di))
            # print(ltw[-1]
            errors = True
        else:
            ltw.append('%i-%i-%i' % (bank, acc_ctr, ctr) +
                       ' (%i,%i)' % (dr, di) + ' OKAY\n')
            # print(ltw[-1]
    if acc_ctr > 0:
        for ctr in range(10012, 10240):
            dr = dreal[ctr]
            di = dimag[ctr]
            _expval = ctr * acc_ctr
            _expval = 1 * acc_ctr
            # _expval = 3 * 815
            if (dr != _expval) or (dr != di):
                ltw.append('%i-%i-%i' % (bank, acc_ctr, ctr) +
                           ' (%i,%i)' % (dr, di) +
                           ' ERROR(%i - %i = %i)' % (dr, _expval, dr - _expval) +
                           ' valdiff(%i)\n' % (dr - di))
                # print(ltw[-1]
                errors = True
            else:
                ltw.append('%i-%i-%i' % (bank, acc_ctr, ctr) +
                           ' (%i,%i)' % (dr, di) + ' OKAY\n')
                # print(ltw[-1]

    fptr.writelines(ltw)
    return not errors

num_accs = 816
acc_ctr = 0
bank_select = False

import sys
from subprocess import check_call
import threading

fname = '/tmp/vacc_testing/test_%i.txt' % time.time()
fptr = open(fname, 'w')


def zipfile(fullfilepath):
    try:
        check_call(['bzip2', fullfilepath])
    except:
        return 1
    return 0

try:
    while True:
        # print('%4i - adding a vector' % acc_ctr,
        print('.',
        fptr.writelines(['%4i - adding a vector\n' % acc_ctr])

        # enable the pulse generator
        fpgautils.threaded_fpga_operation(
            fpgas, 10,
            lambda fpga_:
                fpga_.registers.vacctvg_control.write(pulse_en=True), )
        time.sleep(1.0 / 816.0 * 1.05)
        fpgautils.threaded_fpga_operation(
            fpgas, 10,
            lambda fpga_:
                fpga_.registers.vacctvg_control.write(pulse_en=False), )

        res = get_and_check_data(fpgas[0], acc_ctr, bank_select)

        if not res:
            print('ERRORS(%i-%i)' % (bank_select, acc_ctr),

        sys.stdout.flush()
        fptr.flush()

        # if not res:
        #     fptr.close()
        #     break

        acc_ctr += 1
        # acc_ctr += num_accs

        if acc_ctr >= num_accs:
            oldname = fptr.name
            fptr.close()
            _zipthread = threading.Thread(target=zipfile,
                                          kwargs={'fullfilepath': oldname})
            _zipthread.start()
            fname = '/tmp/vacc_testing/test_%i.txt' % time.time()
            fptr = open(fname, 'w')
            acc_ctr = 0
            bank_select = not bank_select

except Exception as e:
    fptr.close()
    raise e

