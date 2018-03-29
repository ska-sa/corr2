#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""
import struct
import time
import logging

logging.basicConfig(level=eval('logging.INFO'))

# create the devices and connect to them
host = 'roach02081a'
fpga = CasperFpga(host)
fpga.get_system_information()

# let it free run so we can reset it
fpga.registers.vacctvg_control.write(valid_sel=False, sync_sel=False,
                                     pulse_en=False)

_pref = 'sys0_vacc_tvg0'

regname = '%s_n_pulses' % _pref
fpga.registers[regname].write_int(10240)

regname = '%s_n_per_group' % _pref
fpga.registers[regname].write_int(40)

regname = '%s_group_period' % _pref
fpga.registers[regname].write_int(80)

# reset the ctrs
fpga.registers.vacctvg_control.write(vbs_rst0='pulse')

# set valid select
fpga.registers.vacctvg_control.write(valid_sel=True, pulse_en=False)

# set sync select
fpga.registers.vacctvg_control.write(sync_sel=True)

# # set counter select
# fpgautils.threaded_fpga_operation(
#     fpgas, 10,
#     lambda fpga_:
#         fpga_.registers.vacctvg_control.write(ctr_en=True),)

# reset the tvg
fpga.registers.vacctvg_control.write(reset='pulse')

fptr = None

# fpga.registers.vacc_pretvg_ctrl.write(selsync=True,
#                                       seldata=True,
#                                       selvalid=True,
#                                       selflag=True,
#                                       selrben=True,
#                                       selrst=True,
#                                       rst='pulse')

fpga.registers.vacc_pretvg_ctrl.write(selsync=True,
                                      seldata=True,
                                      selvalid=True,
                                      selflag=True,
                                      selrben=False,
                                      selrst=True,
                                      rst='pulse',
                                      en_gating=True)


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
    for ctr in range(10004):
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
        for ctr in range(10004, 10240):
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
        fpga.registers.vacctvg_control.write(pulse_en=True)
        time.sleep(1.0 / 816.0 * 1.05)
        fpga.registers.vacctvg_control.write(pulse_en=False)

        res = get_and_check_data(fpga, acc_ctr, bank_select)

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

