#!/usr/bin/env python
"""
"""
import argparse

from casperfpga import katcp_fpga
from casperfpga import dcp_fpga

parser = argparse.ArgumentParser(description='View the xengine snap block on an x-engine.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store',
                    help='x-engine host')
parser.add_argument('-check_freqs_rx', dest='check', action='store_true', default=False,
                    help='check that we are receiving all the necessary frequencies per timestamp per fengine')
parser.add_argument('-plot', dest='plot', action='store_true', default=False,
                    help='check and plot the incoming timestamp spread')
parser.add_argument('--stop', dest='stopon', action='store', type=int, default=-1,
                    help='stop when the difference is larger than this')
parser.add_argument('--search', dest='search', action='store', type=int, default=-1,
                    help='stop when this frequency is found')
parser.add_argument('--showall', dest='showall', action='store_true', default=False,
                    help='only everything, not only the EOF lines')
parser.add_argument('--eofwe', dest='eofwe', action='store_true', default=False,
                    help='Use EOF for write-enable')
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

# create the device and connect to it
xeng_fpga = HOSTCLASS(args.host)
xeng_fpga.get_system_information()

if args.eofwe or args.check:
    xeng_fpga.registers.control.write(unpack_snapwesel=True)
else:
    xeng_fpga.registers.control.write(unpack_snapwesel=False)


def print_snapshot(snapdata):
    snapkeys = snapdata.keys()
    snaplen = len(snapdata[snapkeys[0]])
    print 'Read %d values from the snapblock:\n' % snaplen
    for ctr in range(0, snaplen):
        if args.showall or snapdata['eof'][ctr] == 1:
            print '%5d:' % ctr,
            for key in snapkeys:
                print '%s(%d)  ' % (key, snapdata[key][ctr]),
            print ''

if args.check:
    snapdata = xeng_fpga.snapshots.snap_unpack0_ss.read()['data']
    xeng_fpga.disconnect()
    snapkeys = snapdata.keys()
    snaplen = len(snapdata[snapkeys[0]])
    # find the first full timestamp
    firsttimestamp = snapdata['time'][0]
    newtimepos = -1
    for ctr in range(0, snaplen):
        if snapdata['time'][ctr] != firsttimestamp:
            newtimepos = ctr
            break
    # check three consecutive timestamps
    for targettime in range(snapdata['time'][newtimepos], snapdata['time'][newtimepos] + 3):
        found_freq = {0: [], 1: [], 2: [], 3: []}
        for ctr in range(newtimepos, newtimepos + 1024):
            this_time = snapdata['time'][ctr]
            this_freq = snapdata['freq'][ctr]
            this_feng = snapdata['feng_id'][ctr]
            this_valid = snapdata['valid'][ctr]
            if this_freq > 127:
                assert not this_valid, 'time(%d) feng(%d) freq(%d) valid(%d)' % \
                                       (this_time, this_feng, this_freq, this_valid)
            else:
                assert this_valid, 'time(%d) feng(%d) freq(%d) valid(%d)' % \
                                   (this_time, this_feng, this_freq, this_valid)
            assert this_freq not in found_freq[this_feng]
            assert this_time == targettime
            found_freq[this_feng].append(this_freq)
        for feng in range(0, 4):
            found_freq[feng] = sorted(found_freq[feng])
            assert found_freq[feng] == range(0, 256)
        print 'Got all frequencies for time %d' % targettime
        newtimepos += 1024

elif args.plot:
    import signal
    import sys
    import matplotlib.pyplot as pyplot

    timestep_errors = 0
    diff_histogram = {}
    freq_histogram = {}

    def exit_gracefully(signal, frame):
        xeng_fpga.disconnect()
        print diff_histogram
        sys.exit(0)

    signal.signal(signal.SIGINT, exit_gracefully)

    bins = [0]
    while True:
        if timestep_errors > 0:
            print '%d total timestep errors' % timestep_errors
        else:
            print 'spread(%d, %d)' % (min(bins), max(bins))
            print diff_histogram
        sys.stdout.flush()
        snapdata = xeng_fpga.snapshots.snap_unpack0_ss.read()['data']
        snapkeys = snapdata.keys()
        snaplen = len(snapdata[snapkeys[0]])
        last_time = snapdata['time'][0]
        max_freq = snapdata['freq'][0] - 1
        min_freq = snapdata['freq'][0] - 1
        print_snap = False
        for ctr in range(0, snaplen):
            this_time = snapdata['time'][ctr]
            this_freq = snapdata['freq'][ctr]
            if this_time == last_time:
                freq_diff = this_freq - max_freq
                freq_diff_abs = freq_diff
                if freq_diff_abs < 0:
                    freq_diff_abs *= -1
                if (args.stopon > 0) and (freq_diff_abs > args.stopon):
                        print 50*'$', ctr, this_freq, max_freq
                try:
                    diff_histogram[freq_diff] += 1
                except KeyError:
                    diff_histogram[freq_diff] = 1
                try:
                    freq_histogram[this_freq] += 1
                except KeyError:
                    freq_histogram[this_freq] = 1
                max_freq = max(this_freq, max_freq)
                min_freq = min(this_freq, min_freq)
            elif this_time == last_time + 1:
                maxfreq = this_freq
            else:
                timestep_errors += 1
            if (args.stopon > 0) and (freq_diff_abs > args.stopon):
                print_snap = True
            if (args.search > -1) and (this_freq == args.search):
                print_snap = True
        if print_snap:
            print_snapshot(snapdata)
            exit_gracefully(signal.SIGINT, None)

        maxallowed = max(diff_histogram.keys())
        minallowed = min(diff_histogram.keys())
        bins = range(minallowed, maxallowed+1)
        # print bins
        values = len(bins) * [0]
        for key, value in diff_histogram.items():
            # print key, value
            if key <= maxallowed:
                values[bins.index(key)] = value
        # print bins
        # print values
        pyplot.interactive(True)
        pyplot.clf()
        pyplot.subplot(211)
        pyplot.bar(bins, values, log=1)
        pyplot.subplot(212)
        pyplot.bar(freq_histogram.keys(), freq_histogram.values(), log=1)
        pyplot.draw()
else:
    snapdata = xeng_fpga.snapshots.snap_unpack0_ss.read()['data']
    xeng_fpga.disconnect()
    print_snapshot(snapdata)


# end
