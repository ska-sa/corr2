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
from casperfpga import network

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

        strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0,
                       max_heaps=40, ring_heaps=40)
                       #max_heaps=3, ring_heaps=3)

        strm.add_udp_reader(multicast_group=data_ip,
                        port=data_port,
                        max_size=9200,
                        buffer_size=5120000,
                        )

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
                #if diff < 0:
                #    raise RuntimeError('The heap count went backwards?!')
                # if diff != self.heap_step:
                #     LOGGER.debug('Heap cnt JUMP: %i -> %i = %i' %
                #                  (heap.cnt - diff, heap.cnt, diff))
                # else:
                LOGGER.info('PROCESSING HEAP ctr(%i) cnt(%i) - '
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
                        intdata = bfraw[chan_on_partition,:,:]
                        plotqueue.put(intdata)
                        got_data_event.set()
                        #import IPython
                        #IPython.embed()
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
    parser.add_argument('--plot_chan', dest='plot_chan', default=1,action='store',
                        help='Which channel to plot? Default: 1')
    parser.add_argument('--loglevel', dest='log_level', action='store', default='INFO',
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
    xeng_acclen = int(configd['xengine']['xeng_accumulation_len'])
    n_chans=int(configd['fengine']['n_chans'])
    n_xeng=int(configd['xengine']['x_per_fpga'])*len((configd['xengine']['hosts']).split(','))
    n_ants = c.n_antennas
    heap_ctr_step = xeng_acclen * n_chans * 2
    plot_chan = int(args.plot_chan)
    partition = (n_xeng*plot_chan)/n_chans
    chan_on_partition=plot_chan-partition*(n_chans/n_xeng)
    data_port = stream.destination.port
    base_ip = stream.destination.ip_address
    data_ip = network.IpAddress(base_ip.ip_int + partition).ip_str
    print('Subscribing to %s at %s:%i'%(stream.name,data_ip,data_port))
    print('Plotting channel %i. ie chan %i  on partition %i.'%(plot_chan,chan_on_partition,partition))

print('Initialising SPEAD transports for data.')

quit_event = threading.Event()
memory_error_event = threading.Event()
plotqueue = Queue.Queue()
got_data_event = threading.Event()
spead_queue = Queue.Queue()


if args.ion:
    pyplot.ion()
    figure = pyplot.figure()
    figure.add_subplot(2, 1, 1)
    figure.add_subplot(2, 1, 2)
    pyplot.pause(0.0001)
    pyplot.show(block=False)



def plot():
    if got_data_event.is_set():
        #print(plotqueue)
        try:
            print('attempting to plot')
            chandata = plotqueue.get_nowait()
        except Queue.Empty:
            print('no data to plot')
            pass

        sbplt = figure.axes
        sbplt[0].cla()
        sbplt[0].set_title('real')
        sbplt[0].grid(True)
        sbplt[1].cla()
        sbplt[1].set_title('imag')
        sbplt[1].grid(True)
        realdata = chandata[:,0]
        imagdata = chandata[:,1]
        lines = []
        names = []
        sbplt[0].plot(realdata)
        sbplt[1].plot(imagdata)
        pyplot.pause(0.0001)
        figure.canvas.draw()
        pyplot.show()
        #pyplot.show(block=False)
        got_data_event.clear()

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
