#!/usr/bin/env python
"""
"""
import argparse

import corr2

parser = argparse.ArgumentParser(description='Debug the shift in the x-engine, check that baselines are only'
                                             'in the correct place...',
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
NUM_BASELINES = NUM_ANT * (NUM_ANT + 1) / 2 * 4

POL_POSITIONS = [0, 1, 8, 9, 20, 21, 32, 33]

c = corr2.fxcorrelator.FxCorrelator('rts correlator', config_source='/home/paulp/code/corr2.ska.github/debug/fxcorr_labrts.ini')
c.initialise(program=False)
eq_array = [0, 0, 0, 0, 0, 0, 0, 0]
for input_ctr in range(0, 8):
    for eqctr in range(0, len(eq_array)):
        eq_array[eqctr] = 0
    eq_array[input_ctr] = 300
    c.feng_set_eq_all(eq_array)
    expected_pos = POL_POSITIONS[input_ctr]

    print('input %i set to zero' % input_ctr

    for args.hostnumber, args.host in enumerate(['roach02095e', 'roach020960', 'roach020a0b',
                                                 'roach020927', 'roach020919', 'roach020925',
                                                 'roach02091a', 'roach020923']):
        print('\tchecking host %s' % args.host
        xeng_fpga = HOSTCLASS(args.host)
        xeng_fpga.get_system_information()

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
        d = xeng_fpga.snapshots.snap_xeng0_ss.read()['data']
        num_sets = len(d['valid']) / 40
        for set in range(0, num_sets):
            set_offset = set * 40
            print('\t\tchecking baselines starting at %i' % set_offset
            for baseline in range(0, 40):
                baseline_pos = set_offset + baseline
                if baseline == expected_pos:
                    assert d['data_re'][baseline_pos] != 0
                else:
                    assert d['data_re'][baseline_pos] == 0
                assert d['data_im'][baseline_pos] == 0
        xeng_fpga.disconnect()
# end
