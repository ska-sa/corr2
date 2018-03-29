import time

# for bitstream = /tmp/test_syncgen3_2016_Feb_12_1513.fpg

from casperfpga.katcp_fpga import KatcpFpga
from casperfpga.memory import bin2fp, fp2fixed_int

hostname = 'roach020818'

f = KatcpFpga(hostname)
f.get_system_information()
f.registers.bf_config.write(tvg_sel=1)


def convert_to_freq(num, beamweight=1.0):
    """
    Convert the 100-bit number from the snapshot to the frequency channel
    of that data point.

    This is assuming that the data is in the pol1 position and the beamweight
    being applied is beamweight.

    :param num: the 100-bit number to be converted
    :param beamweight: the f16.9 beamweight being applied to the data
    :return:
    """
    # a = num & ((2**50)-1)
    # a = num >> 50
    p1r = None
    p1i = None
    p1r8 = None
    p1i8 = None
    res = None
    try:
        a = num
        p1r = bin2fp(a >> 25, 25, 16, True) * (1.0 / beamweight)
        p1i = bin2fp(a & ((2**25)-1), 25, 16, True) * (1.0 / beamweight)
        p1r8 = fp2fixed_int(p1r, 8, 7, True)
        p1i8 = fp2fixed_int(p1i, 8, 7, True)
        res = (p1r8 << 8) | p1i8
    except Exception as e:
        print(a, p1r, p1i, p1r8, p1i8, res
        raise e
    return res


def get_snap_data(offset_words):
    """
    Read the snap data required.
    :param offset_words: offset, in snap words, at which to read
    :return: a snap dictionary
    """
    width_bytes0 = f.snapshots.bfsnap_actrl_ss.width_bits / 8
    width_bytes1 = f.snapshots.bfsnap_actrltime_ss.width_bits / 8
    offset_bytes0 = offset_words * width_bytes0
    offset_bytes1 = offset_words * width_bytes1
    print('Reading snapshot 0 at offset %i, 1 at offset %i' % (offset_bytes0,
                                                               offset_bytes1)
    f.registers.bf_config.write(snap_arm=0)
    f.snapshots.bfsnap_actrl_ss.arm(offset=offset_bytes0)
    f.snapshots.bfsnap_actrltime_ss.arm(offset=offset_bytes1)
    f.registers.bf_config.write(snap_arm=1)
    d = f.snapshots.bfsnap_actrl_ss.read(arm=False)['data']
    d2 = f.snapshots.bfsnap_actrltime_ss.read(arm=False)['data']
    d.update(d2)
    print('Read %i words' % len(d['actrld0'])
    return d

# first look the sync and time transition
d = get_snap_data(0)
if d['actrlsync'][7] != 1:
    for ctr in range(4096):
        print(ctr,
        for key in d.keys():
            print('%s(%i)' % (key, d[key][ctr]),
        print(''
    print('Sync was not found where we expect it.'
    raise RuntimeError
if d['intime27'][8] != d['intime27'][7] + 1:
    for ctr in range(4096):
        print(ctr,
        for key in d.keys():
            print('%s(%i)' % (key, d[key][ctr]),
        print(''
    print('Time jumped from %i to %i?' % (d['intime27'][7],
                                          d['intime27'][8])
    raise RuntimeError
snaplen = len(d['bwd0'])

MAN_TRIG = False

freqloopctr = 0
freqctr = 0
basefreq = 0
lastfreq = -1

while True:
    # get data at the correct offset
    offset = (freqloopctr * snaplen) + 8
    d = get_snap_data(offset)
    freqctr = 0
    timestamp = d['intime27'][0]
    # process it
    for dctr, dword in enumerate(d['bwd0']):
        freq = convert_to_freq(dword, 0.25)
        dstr = '%i %i %i %i %i %i %s' % (dctr, d['intime27'][dctr],
                                         d['bwsync'][dctr], d['bwen'][dctr],
                                         dword, freq,
                                         'ERROR' if freq >= 256 else '')
        if (freq == 255) and (freqctr == 1023):
            if d['bwsync'][dctr] != 1:
                raise RuntimeError('Expected a sync on the last value of the'
                                   'last freq, but it was not there.')
        elif d['bwsync'][dctr] == 1:
            print('After reading snaps at offset %i, got sync error' % offset
            print('freqloopctr', freqloopctr
            print('freqctr', freqctr
            print('freq', freq
            print('lastfreq', lastfreq
            print(dstr
            raise RuntimeError('Sync was high?')
        # they must all have the same timestamp
        if d['intime27'][dctr] != timestamp:
            raise RuntimeError('The time changed in the packet?')
        if freq != lastfreq:
            if lastfreq != -1:
                dstr += '%i' % freqctr
            if freq != lastfreq + 1:
                raise RuntimeError('Jumped from freq %i to %i' % (
                    lastfreq, freqctr))
            freqctr = 0
        else:
            dstr = ''
        if dstr != '':
            print(dstr
        lastfreq = freq
        freqctr += 1
    # check the last one's length
    if freqctr != 1024:
        raise RuntimeError('Frequency %i had too few samples, only %i' % (
            freq, freqctr))
    freqloopctr += 1
    # if it's the last freq, reset
    if lastfreq == 255:
        lastfreq = -1
        freqloopctr = 0
    print('**\n'
    time.sleep(1)
