#!/usr/bin/env python
"""
"""
import argparse

import corr2

parser = argparse.ArgumentParser(description='Debug the shift in the x-engine...',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
# parser.add_argument(dest='host', type=str, action='store',
#                     help='x-engine host')
# parser.add_argument(dest='hostnumber', type=int, action='store',
#                     help='Which host is it in the list?')
# parser.add_argument(dest='nzinput', type=int, action='store',
#                     help='Which input is nonzero?')
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

# create the device and connect to it

# args.host = 'roach020919'
# args.hostnumber = 4

# args.host = 'roach02095e'
# args.hostnumber = 0

# args.nonzeroinput = 1

c = corr2.fxcorrelator.FxCorrelator('rts correlator', config_source='/home/paulp/code/corr2.ska.github/debug/fxcorr_labrts.ini')
c.initialise(program=False)
eq_array = [0, 0, 0, 0, 0, 0, 0, 0]
for input_ctr in range(0, 8):
    for eqctr in range(0, len(eq_array)):
        eq_array[eqctr] = 0
    eq_array[input_ctr] = 300
    c.feng_set_eq_all(eq_array)
    args.nzinput = input_ctr

    for args.hostnumber, args.host in enumerate(['roach02095e', 'roach020960', 'roach020a0b',
                                                 'roach020927', 'roach020919', 'roach020925',
                                                 'roach02091a', 'roach020923']):

        xeng_fpga = HOSTCLASS(args.host)
        xeng_fpga.get_system_information()

        # check that ONLY ant0x has data in it
        NUM_ANT = 4
        NUM_CHANS = 4096
        TOTAL_X = 32
        X_PER_FPGA = 4
        F_PER_X = 128
        F_CORNERTURN_LEN = 256
        snap_bytes = 16 * 4096
        POL0 = 'data_re'
        POL1 = 'data_im'

        bytes_per_freq = 16 * F_CORNERTURN_LEN
        start_f = (NUM_CHANS / TOTAL_X) * X_PER_FPGA * args.hostnumber
        freqs_in_snap = snap_bytes / (NUM_ANT * bytes_per_freq)

        bytes_per_freq_block = bytes_per_freq * NUM_ANT

        def print_snap(data):
            snapkeys = data.keys()
            snaplen = len(data[snapkeys[0]])
            print('Read %d values from snapblock:\n' % snaplen
            for ctr in range(0, snaplen):
                print('%5d:' % ctr,
                for key in snapkeys:
                    print('%s(%d)\t' % (key, data[key][ctr]),
                print(''
            print(50 * '*'

        for freq in range(0, F_PER_X, NUM_ANT):
            byte_offset = freq * bytes_per_freq_block
            print('reading %i frequencies starting at %i, reading %i bytes at offset %i' % (freqs_in_snap, freq + start_f,
                                                                                            snap_bytes, byte_offset)
            d = xeng_fpga.snapshots.snap_reord0_ss.read(offset=byte_offset)['data']
            assert d['freq'][0] == start_f + freq

            for freq_ctr in range(0, freqs_in_snap):
                for ant_ctr in range(0, NUM_ANT):
                    snap_offset = ((freq_ctr * bytes_per_freq_block) + (ant_ctr * bytes_per_freq)) / 16
                    print('freq(%i) ant(%i) data is at offset %i in snapblock' % (freq_ctr, ant_ctr, snap_offset)
                    for data_ctr in range(0, F_CORNERTURN_LEN):
                        word_pos = snap_offset + data_ctr
                        if (args.nzinput == (ant_ctr * 2)) or (args.nzinput == (ant_ctr * 2) + 1):
                            if args.nzinput == (ant_ctr * 2):
                                nonzero_pol = POL0
                                zero_pol = POL1
                            else:
                                nonzero_pol = POL1
                                zero_pol = POL0
                            if d[nonzero_pol][word_pos] == 0:
                                # the occasional zero in the data is okay, so check if there are more.
                                all_zero = True
                                for ctr in range(word_pos-5, word_pos+5):
                                    if d[nonzero_pol][ctr] != 0:
                                        all_zero = False
                                        break
                                if all_zero:
                                    # print_snap(d)
                                    raise RuntimeError('Nonzero data seems to be zeros.')
                            if d[zero_pol][word_pos] != 0:
                                # print_snap(d)
                                raise RuntimeError('Zero data is not zero 1?')
                        else:
                            if (d[POL0][word_pos] != 0) or (d[POL1][word_pos] != 0):
                                # print_snap(d)
                                raise RuntimeError('Zero data is not zero 2?')

        xeng_fpga.disconnect()

# end
