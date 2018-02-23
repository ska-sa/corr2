#!/usr/bin/python
# -*- coding: utf-8 -*-

import spead2
import spead2.recv as s2rx
import time
import threading
import os
import logging
import Queue
import numpy as np
import matplotlib.pyplot as pyplot

from casperfpga.memory import bin2fp, fp2fixed_int

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

FFT_BITS = 13
NUM_ACTIVE_PARTS = 1
PART_HEAP_SIZE = 256
XENG_ACC_LEN = 256
SPEC_LEN = PART_HEAP_SIZE * NUM_ACTIVE_PARTS
HEAP_SIZE = PART_HEAP_SIZE * XENG_ACC_LEN * NUM_ACTIVE_PARTS * 2  # 2 for complex
SPECTRUM_TIME_STEP = (2**FFT_BITS) * XENG_ACC_LEN
FIRST_FREQ = 0

DATA_PORT = 8889


def convert_to_freq(num, beamweight=1.0):
    """
    Convert the 100-bit number from the snapshot to the frequency channel
    of that data point.

    This is assuming that the data is in the pol1 position and the beamweight
    being applied is beamweight.

    :param num: the number to be converted
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
        p1r = bin2fp(a >> 8, 8, 7, True) * (1.0 / beamweight)
        p1i = bin2fp(a & ((2**8)-1), 8, 7, True) * (1.0 / beamweight)
        p1r8 = fp2fixed_int(p1r, 8, 7, True)
        p1i8 = fp2fixed_int(p1i, 8, 7, True)
        res = (p1r8 << 8) | p1i8
    except Exception as e:
        print(a, p1r, p1i, p1r8, p1i8, res
        raise e
    return res


class CorrRx(threading.Thread):
    def __init__(self, **kwargs):
        spead2._logger.setLevel(logging.DEBUG)
        self._target = self.rx_cont
        self._kwargs = kwargs
        self.spead_queue = spead_queue
        self.memory_error_event = memory_error_event
        self.quit_event = quit_event
        threading.Thread.__init__(self)

    def run(self):
        print('Starting target with kwargs ', self._kwargs
        self._target(**self._kwargs)

    def rx_cont(self, **kwargs):
        LOGGER.info('Data reception on port %i.' % DATA_PORT)
        ig = spead2.ItemGroup()
        strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0, max_heaps=8,
                           ring_heaps=8)
        strm.add_udp_reader(port=DATA_PORT, max_size=9200,
                            buffer_size=51200000)
        last_heap_cnt = -1
        heap_ctr = 0
        errs = 0
        try:
            for heap in strm:
                heap_ctr += 1

                # should we quit?
                if self.quit_event.is_set():
                    LOGGER.info('Got a signal from main(), exiting rx loop...')
                    break

                if last_heap_cnt == -1:
                    last_heap_cnt = heap.cnt - SPECTRUM_TIME_STEP
                diff = heap.cnt - last_heap_cnt
                last_heap_cnt = heap.cnt
                # check the heap count only on packets with data
                if diff < 0:
                    raise RuntimeError('The heap count went backwards?!')
                if diff != SPECTRUM_TIME_STEP:
                    LOGGER.debug('Heap cnt JUMP: %i -> %i = %i/%i' %
                                 (heap.cnt - diff, heap.cnt, diff,
                                  diff / SPECTRUM_TIME_STEP))
                    errs += 1
                    continue
                LOGGER.debug('PROCESSING HEAP ctr(%i) cnt(%i) @ %.4f - '
                             '%i' % (heap_ctr, heap.cnt, time.time(), errs))
                ig.update(heap)
                # process the raw beamformer data
                if 'bf_raw' in ig.keys():
                    if ig['bf_raw'] is None:
                        continue
                    bfraw = ig['bf_raw'].value
                    if bfraw is None:
                        continue
                    if not got_data_event.is_set():
                        # check the spectra in the heap
                        # for specctr in range(0, XENG_ACC_LEN):
                        for specctr in range(0, 1):
                            lastfreq = (FIRST_FREQ - 1)
                            spec = bfraw[:, specctr]
                            for fchan in spec:
                                r = np.uint8(fchan[0])
                                i = np.uint8(fchan[1])
                                v = (r << 8) | (i & 255)
                                freq = convert_to_freq(v, 1)
                                assert freq == lastfreq + 1, '%i %i' % (
                                    freq, lastfreq)
                                lastfreq += 1
                if heap_ctr >= 10000:
                    self.quit_event.set()
        except MemoryError:
            self.memory_error_event.set()
            print('mem error?!'

        strm.stop()
        LOGGER.info("Files and sockets closed.")
        self.quit_event.clear()

# some defaults
filename = None
plotbaseline = None
items = None

if __name__ == '__main__':
    import argparse

    from corr2 import utils

    parser = argparse.ArgumentParser(
        description='Receive data from a correlator.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config', dest='config', action='store', default='',
                        help='corr2 config file')
    parser.add_argument('--file', dest='writefile', action='store_true',
                        default=False, help='Write an H5 file.')
    parser.add_argument('--filename', dest='filename', action='store', default='',
                        help='Use a specific filename, otherwise use UNIX time. Implies --file.')
    parser.add_argument('--plot_baselines', dest='plotbaselines', action='store', default='', type=str,
                        help='Plot one or more baselines, comma-seperated list of integers.')
    parser.add_argument('--plot_channels', dest='plotchannels', action='store', default='-1,-1', type=str,
                        help='a start,end tuple, -1 means 0,n_chans respectively')
    parser.add_argument('--item', dest='items', action='append', default=[],   
                        help='spead item to output value to log as we receive it')
    parser.add_argument('--ion', dest='ion', action='store_true', default=False,
                        help='Interactive mode plotting.')
    parser.add_argument('--log', dest='log', action='store_true', default=False,
                        help='Logarithmic y axis.')
    parser.add_argument(
        '--no_auto', dest='noauto', action='store_true', default=False,
        help='Do not scale the data by the number of accumulations.')
    parser.add_argument(
        '--loglevel', dest='log_level', action='store', default='DEBUG',
        help='log level to use, default INFO, options INFO, DEBUG, ERROR')
    parser.add_argument(
        '--speadloglevel', dest='spead_log_level', action='store',
        default='ERROR',
        help='log level to use in spead receiver, default INFO, '
             'options INFO, DEBUG, ERROR')
    args = parser.parse_args()

    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']

    # load the rx port and sd info from the config file
    config = utils.parse_ini_file(args.config)
    n_chans = int(config['fengine']['n_chans'])
    print('Loaded instrument info from config file:\n\t%s' % args.config

    if args.items:
        items = args.items
        print('Tracking:'
        for item in items:
            print('\t  * %s' % item
    else:
        print('Not tracking any items.'

print('Initialising SPEAD transports for data:'
print('\tData reception on port', DATA_PORT
if filename is not None:
    print('\tStoring to file %s' % filename
else:
    print('\tNot saving to disk.'

quit_event = threading.Event()
memory_error_event = threading.Event()
got_data_event = threading.Event()
spead_queue = Queue.Queue()

crx = CorrRx(quit_event=quit_event,
             data_port=DATA_PORT,
             acc_scale=False,
             filename=filename,
             plotbaseline=plotbaseline,
             items=args.items,
             memory_error_event=memory_error_event,
             spead_queue=spead_queue)
try:
    crx.daemon = True
    crx.start()
    # while crx.isAlive():
    #     time.sleep(0.1)
    print('RX process ended.'
    crx.join()
except KeyboardInterrupt:
    import sys
    quit_event.set()
    print('Stopping, waiting for thread to exit...',
    sys.stdout.flush()
    while quit_event.is_set():
        time.sleep(0.1)
    print('all done.'

if memory_error_event.is_set():
    srx = spead_queue.get()
    sig = spead_queue.get()
    import IPython
    IPython.embed()

# end
