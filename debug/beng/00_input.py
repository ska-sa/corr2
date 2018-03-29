from __future__ import print_function
import time

from casperfpga.memory import bin2fp, fp2fixed_int
from casperfpga.casperfpga import CasperFpga

# for /tmp/beng_bw_input_snap2.py

# /tmp/test_syncgen_2016_Feb_10_1242.fpg
# /tmp/test_syncgen2_2016_Feb_10_1219.fpg


hostname = 'roach020818'

f = CasperFpga(hostname)
f.get_system_information()

f.registers.bf_config.write(tvg_sel=True)

XENG_ACC_LEN = 256
NUM_ANT = 4
WORDS_PER_FREQ = XENG_ACC_LEN * NUM_ANT

freqloopctr = 0
freqctr = 0

basefreq = 0

while True:

    offset0 = freqloopctr * f.snapshots.bfsyncgen_snap0_ss.length_bytes
    offset1 = freqloopctr * f.snapshots.bfsyncgen_snap1_ss.length_bytes

    f.registers.bf_config.write(snap_arm=False)

    # arm the snaps
    f.snapshots.bfsyncgen_snap0_ss.arm(offset=offset0)
    f.snapshots.bfsyncgen_snap1_ss.arm(offset=offset1)

    # allow them to trigger
    f.registers.bf_config.write(snap_arm=True)

    d = f.snapshots.bfsyncgen_snap0_ss.read(arm=False, man_valid=False)['data']
    d2 = f.snapshots.bfsyncgen_snap1_ss.read(arm=False, man_valid=False)['data']
    d.update(d2)

    print('Reading snap0 at byte offset %i' % offset0)
    print('Reading snap1 at byte offset %i' % offset1)

    loop_time = -1

    snaplen = len(d[d.keys()[0]])
    print('Snapshot is %i words long. ' % snaplen)

    last_time = -1
    last_freq = -1
    this_freq_ctr = 0
    error = False

    for dctr in range(snaplen):
        print(dctr, end='')
        print('IN(%i %i %i %i)' % (d['insync'][dctr],
                                   d['inen'][dctr],
                                   d['intime27'][dctr],
                                   d['infreq12'][dctr]), end='')
        print('OUT(%i %i %i %i)' % (d['outsync'][dctr],
                                    d['outen'][dctr],
                                    d['outtime27'][dctr],
                                    d['outfreq12'][dctr]), end='')

        # has the timestamp changed in this packet?
        if (last_time != -1) and (last_time != d['outtime27'][dctr]):
            print('TIMESTEP', end='')
            if offset0 != 0:
                print('ERROR(time should not have changed)', end='')
                error = True
            if d['outsync'][dctr-1] != 1:
                print('ERROR(time should change ONLY after a sync)', end='')
                error = True
            if d['outfreq12'][dctr] != 0:
                print('ERROR(freq after a time change MUST be zero, for beng0)', end='')
                error = True

        # has the frequency changed in this packet
        if (last_freq != -1) and (last_freq != d['outfreq12'][dctr]):
            print('FSTEP', end='')
            if last_freq != 255:
                if last_freq != d['outfreq12'][dctr] - 1:
                    print('ERROR(odd freq step: %i > %i)' % (
                        last_freq, d['outfreq12'][dctr]), end='')
                    error = True
                if this_freq_ctr != 1024:
                    print('ERROR(not enough of freq %i - only %i samples)' % (
                        last_freq, this_freq_ctr), end='')
                    error = True
            this_freq_ctr = 0

        print('')

        if d['outen'][dctr] == 1:
            this_freq_ctr += 1
        last_time = d['outtime27'][dctr]
        last_freq = d['outfreq12'][dctr]

    if error:
        print('An error forced a stop.')
        break

    freqloopctr += 1
    freqctr += (snaplen / WORDS_PER_FREQ)

    if freqctr >= 255:
        freqctr = 0
        freqloopctr = 0

    time.sleep(1)
