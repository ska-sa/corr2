#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function
import spead2
import spead2.recv as s2rx
import time
import threading
import os
import logging
import Queue
import numpy as np
import matplotlib.pyplot as pyplot
import corr2
from corr2 import data_stream

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


class CorrRx(threading.Thread):
    def __init__(self, **kwargs):

        spead2._logger.setLevel(logging.INFO)
        self._target = self.rx_cont
        self._kwargs = kwargs
        self.spead_queue = spead_queue
        self.memory_error_event = memory_error_event
        self.quit_event = quit_event
        self.heap_step = kwargs['heap_cnt_step']
        self.xeng_acclen = kwargs['xeng_acclen']
        threading.Thread.__init__(self)

    def run(self):
        print('Starting target with kwargs %s' % self._kwargs)
        self._target(**self._kwargs)

    def rx_cont(self, **kwargs):
        LOGGER.info('Data reception on port %i.' % data_port)
        ig = spead2.ItemGroup()
        strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0, max_heaps=8,
                           ring_heaps=8)
        strm.add_udp_reader(port=data_port, max_size=9200,
                            buffer_size=51200000)
        last_heap_cnt = -1
        heap_ctr = 0
        try:
            for heap in strm:
                # wait for the got_data event to be cleared
                if got_data_event.is_set():
                    time.sleep(0.1)
                    continue
                heap_ctr += 1
                # should we quit?
                if self.quit_event.is_set():
                    LOGGER.info('Got a signal from main(), exiting rx loop...')
                    break
                if last_heap_cnt == -1:
                    last_heap_cnt = heap.cnt - self.heap_step
                diff = heap.cnt - last_heap_cnt
                last_heap_cnt = heap.cnt
                if diff < 0:
                    raise RuntimeError('The heap count went backwards?!')
                # if diff != self.heap_step:
                #     LOGGER.debug('Heap cnt JUMP: %i -> %i = %i' %
                #                  (heap.cnt - diff, heap.cnt, diff))
                # else:
                LOGGER.debug('PROCESSING HEAP ctr(%i) cnt(%i) - '
                             '%i' % (heap_ctr, heap.cnt, diff))
                ig.update(heap)
                # process the raw beamformer data
                if 'bf_raw' in ig.keys():
                    if ig['bf_raw'] is None:
                        continue
                    bfraw = ig['bf_raw'].value
                    if bfraw is None:
                        continue
                    # only get more data when we're ready
                    # we'll lose spectra, but that's okay
                    if not got_data_event.is_set():
                        # integrate the spectra in the heap
                        (speclen, numspec, cplx) = np.shape(bfraw)
                        if numspec != self.xeng_acclen:
                            import IPython
                            IPython.embed()
                            raise RuntimeError(
                                'Receiving too many spectra from the '
                                'beamformer. Expected %i, got %i.' % (
                                    self.xeng_acclen, numspec))
                        intdata = [0] * speclen
                        for specctr in range(0, numspec):
                            # print('processing spectrum %i' % specctr
                            specdata = bfraw[:, specctr, :]
                            for ctr, _d in enumerate(specdata):
                                _pwr = np.sqrt(_d[0]**2 + _d[1]**2)
                                intdata[ctr] += _pwr
                        plotqueue.put(intdata)
                        got_data_event.set()
        except MemoryError:
            self.memory_error_event.set()

        strm.stop()
        LOGGER.info("Files and sockets closed.")
        self.quit_event.clear()

# some defaults
data_port = -1
heap_ctr_step = -1
xeng_acclen = -1

if __name__ == '__main__':
    import argparse

    from corr2 import utils

    parser = argparse.ArgumentParser(
        description='Plot SPEAD data from a beamformer.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(dest='beam', action='store',default=0, help='beam index to plot')
    parser.add_argument('--config', dest='config', action='store', default='',
                        help='corr2 config file')
    parser.add_argument('--ion', dest='ion', action='store_true', default=False,
                        help='Interactive mode plotting.')
    parser.add_argument('--log', dest='log', action='store_true', default=False,
                        help='Logarithmic y axis.')
    parser.add_argument('--sum', dest='sum', action='store_true', default=False,
                        help='Sum the spectra in the packet.')
    parser.add_argument('--sum', dest='sum', action='store_true', default=False,
                        help='Sum the spectra in the packet.')
    parser.add_argument(
        '--loglevel', dest='log_level', action='store', default='INFO',
        help='log level to use, default INFO, options INFO, DEBUG, ERROR')
    parser.add_argument(
        '--speadloglevel', dest='spead_log_level', action='store',
        default='ERROR',
        help='log level to use in spead receiver, default INFO, '
             'options INFO, DEBUG, ERROR')
    args = parser.parse_args()

    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']

    print('Loading instrument info from config file:\n\t%s' % args.config)
    configfile = args.config
    c=corr2.fxcorrelator.FxCorrelator('bob',config_source=configfile)
    c.initialise(configure=False,program=False,require_epoch=False)
    configd = c.configd
    streams = c.get_data_streams_by_type(data_stream.BEAMFORMER_FREQUENCY_DOMAIN)
    print('Available beams:')
    for n,s in enumerate(streams):
        print(n,': ',s)
    stream = streams[int(args.beam)]
    print('Subscribing to %s'%stream.name)
    data_port = stream.destination.port
    xeng_acclen = int(configd['xengine']['xeng_accumulation_len'])
    n_chans=int(configd['fengine']['n_chans'])
    heap_ctr_step = xeng_acclen * n_chans * 2


print('Initialising SPEAD transports for data:')
print('\tData reception on port %s' % data_port)

quit_event = threading.Event()
memory_error_event = threading.Event()
plotqueue = Queue.Queue()
got_data_event = threading.Event()
spead_queue = Queue.Queue()

if args.ion:
    pyplot.ion()


def plot():
    if got_data_event.is_set():
        got_data_event.clear()
        try:
            specdata = plotqueue.get_nowait()
            pyplot.subplot(1, 1, 1)
            pyplot.cla()
            ymax = -1
            ymin = 2**32
            if args.log:
                pyplot.subplot(1, 1, 1)
                pyplot.semilogy(specdata, label='bfspectrum')
            else:
                pyplot.subplot(1, 1, 1)
                pyplot.plot(specdata, label='bfspectrum')
            # ymax = max(ymax, max(chandata))
            # ymin = min(ymin, min(chandata))
            pyplot.legend(loc='upper left')
            pyplot.draw()
            pyplot.show()
        except Queue.Empty:
            pass

crx = CorrRx(quit_event=quit_event,
             data_port=data_port,
             acc_scale=False,
             memory_error_event=memory_error_event,
             spead_queue=spead_queue,
             heap_cnt_step=heap_ctr_step,
             xeng_acclen=xeng_acclen)

try:
    crx.daemon = True
    crx.start()
    while crx.isAlive():
        time.sleep(0.1)
        if plotqueue is not None:
            plot()
    print('RX process ended.')
    crx.join()
except KeyboardInterrupt:
    import sys
    quit_event.set()
    print('Stopping, waiting for thread to exit...', end='')
    sys.stdout.flush()
    while quit_event.is_set():
        time.sleep(0.1)
    print('all done.')

if memory_error_event.is_set():
    srx = spead_queue.get()
    sig = spead_queue.get()
    import IPython
    IPython.embed()

# end
