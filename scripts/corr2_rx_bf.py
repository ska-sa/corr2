#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
 Capture utility for a relatively generic packetised correlator data output stream.

 The script performs two primary roles:

 Storage of stream data on disk in hdf5 format. This includes placing meta data into the file as attributes.

 Regeneration of a SPEAD stream suitable for us in the online signal displays. At the moment this is basically
 just an aggregate of the incoming streams from the multiple x engines scaled with n_accumulations (if set)

Author: Simon Ratcliffe
Revs:
2010-11-26  JRM Added command-line option for autoscaling.
"""

import spead64_48 as spead
import time
import threading
import os
import logging
import Queue
import numpy as np
import matplotlib.pyplot as pyplot


logging.basicConfig(level=logging.DEBUG)
spead.DEBUG = True


class CorrRx(threading.Thread):
    def __init__(self, **kwargs):

        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(logging.StreamHandler())
        self.logger.setLevel(logging.DEBUG)

        spead.logging.getLogger().setLevel(logging.DEBUG)

        self._target = self.rx_cont
        self._kwargs = kwargs

        self.spead_queue = spead_queue

        self.memory_error_event = memory_error_event

        self.quit_event = quit_event
        threading.Thread.__init__(self)

    def run(self):
        print 'Starting target with kwargs ', self._kwargs
        self._target(**self._kwargs)

    def rx_cont(self, **kwargs):
        logger = self.logger

        data_port = 8889

        logger.info('Data reception on port %i.' % data_port)
        rx = spead.TransportUDPrx(data_port, pkt_count=1024,
                                  buffer_size=51200000)
        ig = spead.ItemGroup()
        idx = 0
        last_heap_cnt = -1

        heap_ctr = 0

        try:
            for heap in spead.iterheaps(rx):

                if last_heap_cnt == -1:
                    last_heap_cnt = heap.heap_cnt - 2097152

                diff = heap.heap_cnt - last_heap_cnt

                if diff < 0:
                    raise RuntimeError

                if diff != 2097152:
                    logger.debug('Heap cnt JUMP: %i -> %i' % (last_heap_cnt, heap.heap_cnt))
                last_heap_cnt = heap.heap_cnt

                ig.update(heap)

                logger.debug('PROCESSING HEAP idx(%i) cnt(%i) @ %.4f - %i' % (
                    idx, heap.heap_cnt, time.time(), diff))

                print 'PROCESSING HEAP idx(%i) cnt(%i) @ %.4f - %i' % (
                    idx, heap.heap_cnt, time.time(), diff)

                print 'IG KEYS:', ig.keys()

                if 'x' in ig.keys():
                    if ig['x'] is not None:
                        # print np.shape(ig['x'])
                        channel_select = 66
                        chandata = ig['x'][channel_select, :]

                        chandata = ig['x'][:, 0]

                        _cd = []
                        for _d in chandata:
                            _pwr = np.sqrt(_d[0]**2 + _d[1]**2)
                            _cd.append(_pwr)
                        chandata = _cd[:]

                        if not got_data_event.is_set():
                            plotqueue.put((channel_select, chandata))
                            got_data_event.set()

                # should we quit?
                if self.quit_event.is_set():
                    logger.info('Got a signal from main(), exiting rx loop...')
                    break

                heap_ctr += 1
                if heap_ctr > 10:
                    self.quit_event.set()

        except MemoryError:
            self.memory_error_event.set()

        rx.stop()
        logger.info("Files and sockets closed.")
        self.quit_event.clear()

# some defaults
filename = None
plotbaseline = None
items = None

if __name__ == '__main__':
    import argparse

    from corr2 import utils

    parser = argparse.ArgumentParser(description='Receive data from a correlator.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config', dest='config', action='store', default='',
                        help='corr2 config file')
    parser.add_argument('--file', dest='writefile', action='store_true', default=False,
                        help='Write an H5 file.')
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
    data_port = int(config['xengine']['output_destination_port'])
    n_chans = int(config['fengine']['n_chans'])
    print 'Loaded instrument info from config file:\n\t%s' % args.config

    if args.items:
        items = args.items
        print 'Tracking:'
        for item in items:
            print '\t  * %s' % item
    else:
        print 'Not tracking any items.'

print 'Initialising SPEAD transports for data:'
print '\tData reception on port', data_port
if filename is not None:
    print '\tStoring to file %s' % filename
else:
    print '\tNot saving to disk.'

quit_event = threading.Event()
memory_error_event = threading.Event()
plotqueue = Queue.Queue()
got_data_event = threading.Event()
spead_queue = Queue.Queue()


if args.ion:
    pyplot.ion()


def plot():
    if got_data_event.is_set():
        try:
            chan, chandata = plotqueue.get_nowait()
            pyplot.subplot(1, 1, 1)
            pyplot.cla()
            ymax = -1
            ymin = 2**32
            if args.log:
                pyplot.subplot(1, 1, 1)
                pyplot.semilogy(chandata, label='channel_%i' % chan)
            else:
                pyplot.subplot(1, 1, 1)
                pyplot.plot(chandata, label='channel_%i' % chan)
            # ymax = max(ymax, max(chandata))
            # ymin = min(ymin, min(chandata))
            pyplot.legend(loc='upper left')
            pyplot.draw()
            pyplot.show()
        except Queue.Empty:
            pass
        got_data_event.clear()

crx = CorrRx(quit_event=quit_event,
             data_port=data_port,
             acc_scale=False,
             filename=filename,
             plotbaseline=plotbaseline,
             items=args.items,
             memory_error_event=memory_error_event,
             spead_queue=spead_queue)

try:
    crx.daemon = True
    crx.start()
    while crx.isAlive():
        time.sleep(0.1)
        if plotqueue is not None:
            plot()
    print 'RX process ended.'
    crx.join()
except KeyboardInterrupt:
    import sys
    quit_event.set()
    print 'Stopping, waiting for thread to exit...',
    sys.stdout.flush()
    while quit_event.is_set():
        time.sleep(0.1)
    print 'all done.'

if memory_error_event.is_set():
    srx = spead_queue.get()
    sig = spead_queue.get()
    import IPython
    IPython.embed()

# end
