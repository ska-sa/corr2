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

import spead2
import spead2.recv as s2rx
import numpy as np
import time
import h5py
import threading
import os
import logging
import argparse

from corr2 import utils


def do_track_items(ig, logger, track_list):
    """

    :param ig:
    :param logger:
    :param track_list:
    :return:
    """
    if track_list is None:
        return
    for name in ig.keys():
        if name not in track_list:
            continue
        item = ig[name]
        if not item.has_changed():
            continue
            logger.info('(%s) %s => %s' % (time.ctime(), name, str(item)))


def do_h5_file(ig, logger, h5_file, datasets, dataset_indices):
    """

    :param ig:
    :param logger:
    :param h5_file:
    :return:
    """
    if h5_file is None:
        return
    # we need these bits of meta data before being able to assemble and
    # transmit signal display data
    meta_required = ['n_chans', 'bandwidth', 'n_bls', 'n_xengs', 'center_freq',
                     'bls_ordering', 'n_accs']
    for name in ig.keys():
        try:
            logger.debug('\tkey name %s' % name)
            item = ig[name]
            if item.value is None:
                continue
            if name in meta_required:
                meta_required.pop(meta_required.index(name))
                if len(meta_required) == 0:
                    n_chans = h5_file['n_chans'][0]
                    n_bls = h5_file['n_bls'][0]
                    logger.info('Got all required metadata. Expecting data '
                                'frame shape of %i %i %i' % (
                        n_chans, n_bls, 2))
                    meta_required = ['n_chans', 'bandwidth', 'n_bls', 'n_xengs',
                                     'center_freq', 'bls_ordering', 'n_accs']

            # check to see if we have encountered this type before
            if name not in datasets.keys():
                datasets[name] = item
                dataset_indices[name] = 0

            # check to see if we have stored this type before
            if name not in h5_file.keys():
                shape = item.shape if item.shape == -1 else item.shape
                dtype = np.dtype(type(item)) if shape == [] else item.dtype
                if dtype is None:
                    dtype = item.dtype
                # if we can't get a dtype from the descriptor try and get one
                # from the value
                if dtype != 'object':
                    logger.debug('Creating dataset for %s (%s,%s).' % (str(name), str(shape), str(dtype)))
                    h5_file.create_dataset(
                        name, [1] + ([] if list(shape) == [1] else list(shape)),
                        maxshape=[None] + ([] if list(shape) == [1] else list(shape)), dtype=dtype)
            else:
                logger.debug('Adding %s to dataset. New size is %i.' % (name, dataset_indices[name]+1))
                h5_file[name].resize(dataset_indices[name]+1, axis=0)

            # if name.startswith('xeng_raw'):
            #     sd_timestamp = ig['sync_time'] + (ig['timestamp'] / float(ig['scale_factor_timestamp']))
            #     logger.info("SD Timestamp: %f (%s)." % (sd_timestamp, time.ctime(sd_timestamp)))
            #     scale_factor = float(meta['n_accs'] if ('n_accs' in meta.keys() and acc_scale) else 1)
            #     scaled_data = (item / scale_factor).astype(np.float32)
            #     scale_status = 'Unscaled' if not acc_scale else 'Scaled by %i' % scale_factor
            #     logger.info(
            #         'Sending signal display frame with timestamp %i (%s). %s. '
            #         'Max: %i, Mean: %i' % (
            #             sd_timestamp, time.ctime(sd_timestamp),
            #             scale_status, np.max(scaled_data), np.mean(scaled_data)))

            h5_file[name][dataset_indices[name]] = item.value

            dataset_indices[name] += 1

        except IOError:
            import IPython
            IPython.embed()

        # next item...


def print_xeng_data(logger, data):
    """

    :param data:
    :return:
    """
    if data is None:
        return
    powerdata = data[0]
    phasedata = data[1]
    for blsctr in range(len(powerdata)):
        bls = powerdata[blsctr][0]
        pwr = powerdata[blsctr][1]
        phs = phasedata[blsctr][1]
        logger.info('%i-%s:\n\tpwr: %s\n\tphs: %s' % (bls, BASELINES[bls],
                                                      pwr, phs))


def process_xeng_data(ig, logger, baselines, channels):
    """
    Assemble plotting data for the the plotting thread to deal with.
    :param ig:
    :return:
    """
    if 'xeng_raw' not in ig.keys():
        return None
    if ig['xeng_raw'] is None:
        return None
    xeng_raw = ig['xeng_raw'].value
    if xeng_raw is None:
        return None
    logger.info('Processing xeng_raw heap with shape: %s' % str(np.shape(xeng_raw)))
    scale_factor = float(ig['scale_factor_timestamp'].value)
    sd_timestamp = ig['sync_time'].value + (ig['timestamp'].value / scale_factor)
    logger.info('(%s) timestamp %i => %s' % (
        time.ctime(), ig['timestamp'].value, time.ctime(sd_timestamp)))
    baseline_data = []
    baseline_phase = []
    for baseline in baselines:
        bdata = xeng_raw[:, baseline]
        powerdata = []
        phasedata = []
        for ctr in range(channels[0], channels[1]):
            complex_tuple = bdata[ctr]
            pwr = np.sqrt(complex_tuple[0]**2 + complex_tuple[1]**2)
            powerdata.append(pwr)
            cplx = complex(complex_tuple[0], complex_tuple[1])
            phase = np.angle(cplx)
            # phase = np.unwrap(phase)
            phasedata.append(phase)
        baseline_data.append((baseline, powerdata[:]))
        baseline_phase.append((baseline, phasedata[:]))
    return baseline_data, baseline_phase


class CorrPlotter(threading.Thread):
    def __init__(self, quit_event, plot_queue,
                 plot_data_event, plot_update_event,
                 subplots, acc_scale,
                 baselines, channels):
        self.quit_event = quit_event
        self.plot_queue = plot_queue
        self.plot_data_event = plot_data_event
        self.plot_update_event = plot_update_event
        self.baselines = baselines
        self.channels = channels
        self.subplots = subplots
        self.plot_counter = 0
        self.acc_scale = acc_scale
        threading.Thread.__init__(self)

    def run(self):
        self.plot_data()

    def plot_data(self):
        while True:
            if self.plot_data_event.is_set():
                self.actually_plot()
                plot_data_event.clear()
            if self.quit_event.is_set():
                logging.debug('exiting plotting thread')
                break
            time.sleep(1)

    def actually_plot(self):
        try:
            plotdata = self.plot_queue.get_nowait()
            if plotdata is None:
                return
            self.subplots[0].cla()
            self.subplots[0].set_title('pwr - %i' % self.plot_counter)
            self.subplots[0].grid(True)
            self.subplots[1].cla()
            self.subplots[1].set_title('phs - %i' % self.plot_counter)
            self.subplots[1].grid(True)
            powerdata = plotdata[0]
            phasedata = plotdata[1]
            lines = []
            names = []
            for pltctr, plot in enumerate(powerdata):
                baseline = plot[0]
                plotdata = plot[1]
                phaseplot = phasedata[pltctr][1]
                bls_name = BASELINES[baseline]
                names.append(bls_name)
                if args.log:
                    l, = self.subplots[0].semilogy(plotdata)
                    self.subplots[1].semilogy(phaseplot)
                else:
                    l, = self.subplots[0].plot(plotdata)
                    self.subplots[1].plot(phaseplot)
                lines.append(l)
            if LEGEND:
                self.subplots[0].legend(lines, names)
            self.plot_counter += 1
            plot_update_event.set()
        except Queue.Empty:
            pass


class CorrReceiver(threading.Thread):
    """
    Receive thread to process heaps received by a SPEAD2 stream.
    """
    def __init__(self, port,
                 quit_event,
                 track_list,
                 h5_filename,
                 print_data,
                 plot_queue,
                 plot_data_event,
                 baselines,
                 channels,
                 log_handler=None,
                 log_level=logging.INFO,
                 spead_log_level=logging.INFO):

        if quit_event is None:
            raise RuntimeError('No quit event supplied?')
        # if log_handler == None:
        #     log_handler = log_handlers.DebugLogHandler(100)
        # self.log_handler = log_handler
        self.logger = logging.getLogger('CorrRx')
        # self.logger.addHandler(self.log_handler)
        self.logger.setLevel(log_level)
        self.logger = logging.getLogger(__name__)
        spead2._logger.setLevel(spead_log_level)
        self._target = self.rx_cont

        self.port = port

        self.track_list = track_list
        self.print_data = print_data
        self.plot_queue = plot_queue
        self.plot_data_event = plot_data_event
        self.baselines = baselines
        self.channels = channels

        self.h5_filename = h5_filename
        self.h5_datasets = {}
        self.h5_dataset_indices = {}

        self.quit_event = quit_event

        threading.Thread.__init__(self)

    def run(self):
        print 'Starting RX target'
        self._target()

    def rx_cont(self):
        """
        The main receive loop method.
        :return:
        """
        logger = self.logger
        logger.info('RXing data on port %i.' % self.port)

        # make a SPEAD2 receiver stream
        strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0,
                           max_heaps=8, ring_heaps=8)
        strm.add_udp_reader(port=self.port, max_size=9200,
                            buffer_size=5120000)

        # were we given a H5 file to which to write?
        h5_file = None
        if self.h5_filename:
            logger.info('Starting H5 file %s.' % self.h5_filename)
            h5_file = h5py.File(self.h5_filename, mode='w')

        # make the ItemGroup and some local vars
        ig = spead2.ItemGroup()
        idx = 0
        last_cnt = -1

        # process receivd heaps
        for heap in strm:
            ig.update(heap)
            cnt_diff = heap.cnt - last_cnt
            last_cnt = heap.cnt
            logger.debug('PROCESSING HEAP idx(%i) cnt(%i) cnt_diff(%i) '
                         '@ %.4f' % (idx, heap.cnt, cnt_diff, time.time()))

            if self.track_list:
                do_track_items(ig, logger, track_list=self.track_list)

            if h5_file:
                do_h5_file(ig, logger, h5_file,
                           self.h5_datasets, self.h5_dataset_indices)

            get_data = False
            if self.plot_data_event is not None:
                get_data = not self.plot_data_event.is_set()
            get_data = get_data or self.print_data
            if get_data:
                data = process_xeng_data(ig, logger,
                                         self.baselines, self.channels)
            else:
                logger.debug('\talready got data, skipping this heap.')
                data = None

            if self.plot_queue:
                if not self.plot_data_event.is_set():
                    if not data:
                        logger.error('Plot queue is not set, but NO data?')
                    else:
                        self.plot_queue.put(data)
                        self.plot_data_event.set()

            if self.print_data:
                print_xeng_data(logger, data)

            # should we quit?
            if self.quit_event.is_set():
                logger.info('Got a signal from main(), exiting rx loop...')
                break

            idx += 1

#        for (name,idx) in datasets_index.iteritems():
#            if idx == 1:
#                self.logger.info("Repacking dataset %s as an attribute as it is singular."%name)
#                h5_file['/'].attrs[name] = h5_file[name].value[0]
#                h5_file.__delitem__(name)

        if h5_file is not None:
            logger.info('Closing H5 file, %s' % h5_filename)
            h5_file.flush()
            h5_file.close()

        strm.stop()
        logger.info('SPEAD2 RX stream socket closed.')
        self.quit_event.clear()


parser = argparse.ArgumentParser(
    description='Receive data from a corr2 correlator.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', action='store', default='',
    help='corr2 config file')
parser.add_argument(
    '--file', dest='writefile', action='store_true', default=False,
    help='Write an H5 file.')
parser.add_argument(
    '--filename', dest='filename', action='store', default='',
    help='Use a specific filename, otherwise use UNIX time. Implies --file.')
parser.add_argument(
    '--plot', dest='plot', action='store_true', default=False,
    help='Plot the specified baselines and channels.')
parser.add_argument(
    '--print', dest='printdata', action='store_true', default=False,
    help='Print the specified baselines and channels.')
parser.add_argument(
    '--baselines', dest='baselines', action='store', default='', type=str,
    help='Plot one or more baselines, comma-seperated list of '
         'integers. \'all\' for ALL.')
parser.add_argument(
    '--channels', dest='channels', action='store', default='-1,-1', type=str,
    help='a (start,end) tuple, -1 means 0, n_chans respectively')
parser.add_argument(
    '--items', dest='items', action='store', default='',
    help='SPEAD items to track, in comma-separated list - will output '
         'value to log as it is RXd')
parser.add_argument(
    '--log', dest='log', action='store_true', default=False,
    help='Logarithmic y axis.')
parser.add_argument(
    '--no_auto', dest='noauto', action='store_true', default=False,
    help='Do not scale the data by the number of accumulations.')
parser.add_argument(
    '--legend', dest='legend', action='store_true', default=False,
    help='Show a plot legend.')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='INFO',
    help='log level to use, default INFO, options INFO, DEBUG, ERROR')
parser.add_argument(
    '--speadloglevel', dest='spead_log_level', action='store', default='INFO',
    help='log level to use in spead receiver, default INFO, options '
         'INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level:
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=getattr(logging, log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if args.spead_log_level:
    spead_log_level = args.spead_log_level.strip()
    try:
        logging.basicConfig(level=getattr(logging, spead_log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % spead_log_level)

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']

# load information from the config file of the running system
config = utils.parse_ini_file(args.config)
data_port = int(config['xengine']['output_destination_port'])
n_chans = int(config['fengine']['n_chans'])
fhosts = config['fengine']['hosts'].split(',')
n_ants = len(fhosts)
print 'Loaded instrument info from config file:\n\t%s' % args.config

NUM_BASELINES = n_ants * (n_ants + 1) / 2 * 4
BASELINES = utils.baselines_from_config(config=config)
LEGEND = args.legend

if args.items:
    track_list = args.items.split(',')
    print 'Tracking:'
    for item in track_list:
        print '\t%s' % item
else:
    track_list = None
    print 'Not tracking any items.'

h5_filename = None
if args.writefile:
    h5_filename = str(time.time()) + '.corr2.h5'
if args.filename != '':
    h5_filename = args.filename + '.corr2.h5'
if h5_filename:
    print 'Storing to H5 file: %s' % h5_filename
else:
    print 'Not saving to disk.'

if args.noauto:
    acc_scale = False
else:
    acc_scale = True

baselines = []
channels = []
if args.printdata or args.plot:
    if args.baselines != '':
        if args.baselines == 'all':
            baselines = range(NUM_BASELINES)
        else:
            baselines = [int(bls) for bls in args.baselines.split(',')]
    if not baselines:
        print 'No baselines to plot or print.'
    else:
        print 'Given baselines:', baselines
        temp = args.channels.split(',')
        plot_startchan = int(temp[0].strip())
        plot_endchan = int(temp[1].strip())
        if plot_startchan == -1:
            plot_startchan = 0
        if plot_endchan == -1:
            plot_endchan = n_chans
        channels = (plot_startchan, plot_endchan)
        print 'Given channel range:', channels
    if (not baselines) or (not channels):
        print 'Print or plot requested, but no baselines and/or ' \
              'channels specified.'

quit_event = threading.Event()

# if there are baselines to plot, set up a plotter that will pull
# data from a data queue
plot_queue = None
plot_data_event = None
plot_thread = None
plot_update_event = threading.Event()
if args.plot:
    if not len(baselines):
        raise RuntimeError('plot requested, but no baselines specified.')
    import matplotlib.pyplot as pyplot
    import Queue
    plot_queue = Queue.Queue()
    plot_data_event = threading.Event()
    # figure_manager = pyplot.get_current_fig_manager()
    # figure_manager.resize(*figure_manager.window.maxsize())
    subplots = []
    for p in range(2):
        sub_plot = pyplot.subplot(2, 1, p + 1)
        subplots.append(sub_plot)
    plot_counter = 0
    # pyplot.ion()
    pyplot.show(block=False)
    plot_thread = CorrPlotter(quit_event, plot_queue,
                              plot_data_event, plot_update_event,
                              subplots, acc_scale,
                              baselines, channels)
    plot_thread.daemon = True
    plot_thread.start()
    print 'Plot started, waiting for data.'

# start the receiver thread
print 'Initialising SPEAD transports for data:'
print '\tData reception on port', data_port

corr_rx = CorrReceiver(
    port=data_port,
    log_level=eval('logging.%s' % log_level),
    spead_log_level=eval('logging.%s' % spead_log_level),
    track_list=track_list,
    h5_filename=h5_filename,
    print_data=args.printdata,
    plot_queue=plot_queue,
    plot_data_event=plot_data_event,
    baselines=baselines,
    channels=channels,
    quit_event=quit_event, )
try:
    corr_rx.daemon = True
    corr_rx.start()
    while corr_rx.isAlive():
        if plot_update_event.is_set():
            pyplot.draw()
            plot_update_event.clear()
        else:
            time.sleep(0.05)
    print 'RX process ended.'
    quit_event.set()
    corr_rx.join()
    if plot_thread is not None:
        plot_thread.join()
except KeyboardInterrupt:
    import sys
    quit_event.set()
    print 'Stopping, waiting for thread to exit...',
    sys.stdout.flush()
    while quit_event.is_set():
        print '.',
        sys.stdout.flush()
        time.sleep(0.1)
    print 'all done.'

# end
