#!/usr/bin/env python
# # -*- coding: utf-8 -*-
#
# """
#  Capture utility for a relatively generic packetised correlator
#  data output stream.
#
#  The script performs two primary roles:
#
#  Storage of stream data on disk in hdf5 format.
#  This includes placing meta data into the file as attributes.
#
#  Regeneration of a SPEAD stream suitable for us in the online signal
#  displays. At the moment this is basically just an aggregate of
#  the incoming streams from the multiple x engines scaled with
#  n_accumulations (if set)
#
# Author: Simon Ratcliffe
# Revs:
# 2010-11-26  JRM Added command-line option for autoscaling.
# """
from __future__ import print_function

import argparse
import array
import fcntl
import logging
import os
import random
import Queue
import re
import socket
import struct
import sys
import threading
import time

import coloredlogs
import h5py
import katcp
import matplotlib.pyplot as plt
import numpy as np
import spead2
import spead2.recv as s2rx

import casperfpga
import corr2
from casperfpga.network import IpAddress
from corr2 import data_stream

assert hasattr(corr2, "fxcorrelator")
assert hasattr(corr2.fxcorrelator, "FxCorrelator")
assert hasattr(casperfpga, "network")
assert hasattr(casperfpga.network, "IpAddress")

_file_name = os.path.basename(sys.argv[0])
interface_prefix = "10.100"
ri = True

# Custom logging level for printing time
TIMEDEBUG = 45
logging.addLevelName(TIMEDEBUG, 'TIMEDEBUG')

def timedebug(self, message, *args, **kws):
    self.log(TIMEDEBUG, message, *args, **kws)
logging.Logger.timedebug = timedebug


class DictObject(object):

    def __init__(self, _dict):
        """
        Fancier way of converting nested dictionary to an object!

        Parameters
        ----------
        _dict: dictionary
            Already defined dictionary
        Returns
        -------
        object: dictionary object
        """
        for key, value in _dict.items():
            if isinstance(value, (list, tuple)):
                setattr(self, key, [obj(x) if isinstance(x, dict) else x for x in value])
            else:
                setattr(self, key, obj(value) if isinstance(value, dict) else value)

    @staticmethod
    def _dictsMerger(*dicts):
        """
        Given any number of dicts, shallow copy and merge into a new dict,
        precedence goes to key value pairs in latter dicts.
        """
        result = {}
        for dictionary in dicts:
            result.update(dictionary)
        return result


class LoggingClass(object):

    def __init__(self, log_level="INFO"):
        self.log_level = log_level

    @property
    def logger(self):
        log_format = (
            '%(asctime)s | %(name)s | %(levelname)s | %(module)s | %(pathname)s : '
            '%(lineno)d - %(message)s')

        name = '.'.join([_file_name, self.__class__.__name__])
        try:
            logger = logging.getLogger(name)
            if not len(logger.handlers):
                handler = logging.StreamHandler()
                handler.setLevel(getattr(logging, self.log_level))
                formatter = coloredlogs.ColoredFormatter(fmt=log_format, datefmt='%Y.%m.%d %H:%M:%S')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
            return logger
        except AttributeError:
            raise RuntimeError('No such log level: %s' % self.log_level)


class PrintConsumer(object):
    def __init__(self, baselines):
        self.data_queue = Queue.Queue(maxsize=128)
        self.baselines = baselines
        self.need_data_flag = threading.Event()

    def print_data(self, logger):
        """
        Print all the data in our Queue
        :return:
        """
        while True:
            try:
                data = self.data_queue.get_nowait()
            except Queue.Empty:
                break
            if data is None:
                raise RuntimeError('print_data: got None data - this is wrong')
            logger.debug('PROCESSING PRINT DATA')
            powerdata = data[0]
            phasedata = data[1]
            for blsctr in range(len(powerdata)):
                bls = powerdata[blsctr][0]
                pwr = powerdata[blsctr][1]
                phs = phasedata[blsctr][1]
                if args.ri:
                    logger.info('%i-%s:\n\treal: %s\n\timag: %s' % (
                        bls, self.baselines[bls], pwr[0:100], phs[0:100]))
                else:
                    logger.info('%i-%s:\n\tpwr: %s\n\tphs: %s' % (
                        bls, self.baselines[bls], pwr[0:100], phs[0:100]))
        self.need_data_flag.set()


class PlotConsumer(object):

    def __init__(self, figure=None, legend=None, baselines=None, animated=True):
        """
        The Plot consumer - plots the contents it finds in the plot queue
        :param figure:
        :param animated:
        :return:
        """
        self.figure = figure
        self.legend = legend
        self.baselines = baselines
        self.data_queue = Queue.Queue(maxsize=1)
        self.need_data_flag = threading.Event()
        self.need_data_flag.set()
        self.animated = animated
        self.running = threading.Event()
        self.plot_counter = 0
        # callbacks could be useful?
        # self.figure.canvas.mpl_connect('close_event', self.on_close)
        # self.figure.canvas.mpl_connect('key_release_event', self.redraw)

    def plot_data(self, logger):
        try:
            plotdata = self.data_queue.get_nowait()
        except Queue.Empty:
            return
        if plotdata is None:
            raise RuntimeError('plot_data: got None data - this is wrong')
        # sys.stdout.flush()

        if not self.animated:
            self.figure = plt.figure()
            self.figure.add_subplot(2, 1, 1)
            self.figure.add_subplot(2, 1, 2)

        self.figure.subplots_adjust(hspace=0.5)
        sbplt = self.figure.axes
        sbplt[0].cla()
        if args.ri:
            sbplt[0].set_title('real - %s' % self.plot_counter)
            sbplt[0].grid(True)
            sbplt[1].cla()
            sbplt[1].set_title('imag - %s' % self.plot_counter)
            sbplt[1].grid(True)
        else:
            sbplt[0].set_title('power - %s' % self.plot_counter)
            sbplt[0].grid(True)
            sbplt[1].cla()
            sbplt[1].set_title('phase - %s' % self.plot_counter)
            sbplt[1].grid(True)
        powerdata = plotdata[0]
        phasedata = plotdata[1]
        lines = []
        names = []
        for pltctr, plot in enumerate(powerdata):
            baseline = plot[0]
            plotdata = plot[1]
            phaseplot = phasedata[pltctr][1]
            if args.log:
                if np.sum(plotdata) == 0:
                    l, = sbplt[0].plot(plotdata)
                else:
                    l, = sbplt[0].semilogy(plotdata)
                sbplt[1].plot(phaseplot)
            else:
                l, = sbplt[0].plot(plotdata)
                sbplt[1].plot(phaseplot)
            lines.append(l)
            bls_name = self.baselines[baseline]
            names.append(bls_name)
        if self.legend:
            sbplt[0].legend(lines, names)
        self.plot_counter += 1
        if self.animated:
            figure.canvas.draw()
            self.need_data_flag.set()
        else:
            plt.pause(0.01)
            plt.show()
            self.need_data_flag.set()


class CorrReceiver(LoggingClass, threading.Thread):
    """
    Receive thread to process heaps received by a SPEAD2 stream.
    """

    def __init__(
        self, servlet="127.0.0.1:7601", config_file=None, channels=(0, 4095), baselines=None,
        h5_file=None, warmup_capture=False, realimag=True, **kwargs
    ):
        """

        Parameters
        ----------

        :param port: the port on which to receive data
        :param base_ip: the base IP address to subscribe to
        :param quit_event: quit if this thread_safe event is set
        :param track_list: a list of items to track
        :param h5_filename: the H5 filename to use
        :param baselines: the baselines in which we're interested
        :param channels: the channels to plot/print
        :param acc_scale: boolean, to scale the data or not

        Return
        -------

        """

        # Better logging
        log_level = kwargs.get('log_level', "INFO").upper()
        LoggingClass.__init__(self)
        self.logger.setLevel(getattr(logging, log_level))

        self.servlet_ip, self.servlet_port = servlet.split(":")
        self._config_file = config_file
        self.h5_file = h5_file
        self.realimag = realimag
        # a quit event to stop the thread if needed
        self.quit_event = threading.Event()
        if log_level == 'DEBUG':
            spead2._logger.setLevel(getattr(logging, log_level))

        # This runs a capture once with only one substream.
        # It seems to be needed to get larger captures to work.
        # Must be investigated
        # After the warmup loop the normal loop runs
        self.warmup_capture = warmup_capture
        try:
            assert isinstance(self._config_file, str)
        except AssertionError:
            self.logger.error("No Config File defined!!!")
            raise
        else:
            # self.corrVars = DictObject(self.corr_config(self._config_file))
            self._config_info = self.corr_config(self._config_file, **kwargs)
        finally:
            # self.corrVars = DictObject(self.get_sensors(self.servlet_ip, self.servlet_port))
            self._sensors_info = self.get_sensors(self.servlet_ip, self.servlet_port)

        self.corrVars = DictObject(DictObject._dictsMerger(self._sensors_info,  self._config_info))
        self._get_plot_limits(baselines, channels)

        self.need_print_data = None
        self.print_queue = None

        self.need_plot_data = None
        self.plot_queue = None

        threading.Thread.__init__(self)

    def set_print_queue(self, queue, flag):
        self.print_queue = queue
        self.need_print_data = flag

    def set_plot_queue(self, queue, flag):
        self.plot_queue = queue
        self.need_plot_data = flag

    def run(self):
        self.logger.info('Starting RX target')
        self.rx_cont()

    def rx_cont(self):
        """
        The main spead2 receiver loop method.
        """
        # TODO: This runs a capture once with only one substream.
        # It seems to be needed to get larger captures to work.
        # Must be investigated
        # After the warmup loop the normal loop runs
        # self.warmup_capture = True

        strm = self._spead_stream()
        self._mcast_subs(strm)
        # for double_loop in xrange(2):

        # were we given a H5 file to which to write?
        if self.h5_file:
            h5_filename = '{}.corr2.h5'.format(time.time())
            self.logger.info('Starting H5 file %s.' % h5_filename)
            self.h5_file = h5py.File(h5_filename, mode='w')

        # make the ItemGroup and some local vars
        item_group = spead2.ItemGroup()
        idx = 0
        last_cnt = -1 * self.corrVars.n_xengs

        heap_contents = {}

        # process received heaps
        for heap in strm:
            item_group.update(heap)
            cnt_diff = heap.cnt - last_cnt
            last_cnt = heap.cnt
            self.logger.info('PROCESSING HEAP idx(%i) cnt(%i) cnt_diff(%i) @ %.4f' % (
                idx, heap.cnt, cnt_diff, time.time()))
            self.logger.debug('Contents dict is now %i long' % len(heap_contents))
            if len(heap.get_items()) == 0:
                self.logger.error('Empty heap - was this descriptors?')
                continue
            # do we need to process more data?
            if self.print_queue:
                need_print = self.need_print_data.is_set()
            else:
                need_print = False
            if self.plot_queue:
                need_plot = self.need_plot_data.is_set()
            else:
                need_plot = False
            if need_print or need_plot:
                data = self.process_xeng_data(heap_contents, item_group, self.baselines, self.channels)
            else:
                self.logger.warn('\talready got data, skipping processing this heap.')
                data = None
            if data:
                for datatime in data:
                    # add to consumer queues if necessary
                    if need_print:
                        self.need_print_data.clear()
                        try:
                            self.print_queue.put(data[datatime])
                        except Queue.Full:
                            self.print_queue.get()
                            self.print_queue.put(data[datatime])
                    if need_plot:
                        self.need_plot_data.clear()
                        try:
                            self.plot_queue.put(data[datatime])
                        except Queue.Full:
                            self.plot_queue.get()
                            self.plot_queue.put(data[datatime])
                if self.warmup_capture:
                    break
            # should we quit?
            if self.quit_event.is_set():
                self.logger.warn('Got a signal from main(), exiting rx loop...')
                break
            # count processed heaps
            idx += 1
        if self.warmup_capture:
            self.warmup_capture = False

        if self.h5_file is not None:
            self.logger.info('Closing H5 file, %s' % h5_filename)
            self.h5_file.flush()
            self.h5_file.close()

        strm.stop()
        self.logger.info('SPEAD2 RX stream socket closed.')
        self.quit_event.clear()

    def _mcast_subs(self, strm):
        """
        Multicast IP subscription

        Parameters
        ----------
        strm : Spead2 Stream object

        Returns
        -------

        """
        base_ip = self.corrVars.baseline_correlation_products_destination
        n_chans_per_substream = self.corrVars.baseline_correlation_products_n_chans_per_substream
        self._interface_address = ''.join([ethx for ethx in self.network_interfaces()
                                           if ethx.startswith(interface_prefix)])
        try:
            assert self.warmup_capture
            channels = (0, 15)
        except AssertionError:
            channels = self.channels

        self.logger.info('RXing data with base IP address: %s' % (base_ip))
        self._strt_substream, self._stop_substream = map(
            lambda chan: chan / n_chans_per_substream, channels)
        if self._stop_substream == self.corrVars.n_xengs:
            self._stop_substream = self.corrVars.n_xengs - 1
        n_substreams = self._stop_substream - self._strt_substream + 1
        assert hasattr(base_ip, 'ip_address')
        start_ip = IpAddress(base_ip.ip_address.ip_int + self._strt_substream).ip_str
        end_ip = IpAddress(base_ip.ip_address.ip_int + self._stop_substream).ip_str

        self.logger.info('Subscribing to %s substream/s in the range %s to %s' % (n_substreams, start_ip, end_ip))
        for ctr in xrange(self._strt_substream, self._stop_substream + 1):
            addr = IpAddress(base_ip.ip_address.ip_int + ctr).ip_str
            self.logger.debug("Subscribing to %s" % addr)
            strm.add_udp_reader(multicast_group=addr,
                                port=base_ip.port,
                                max_size=9200,
                                interface_address=self._interface_address
                                )

    def _spead_stream(self, active_frames=3):
        """
        Spead stream initialisation with performance tuning added.

        """
        n_chans_per_substream = self.corrVars.baseline_correlation_products_n_chans_per_substream
        heap_data_size = (
            np.dtype(np.complex64).itemsize * n_chans_per_substream *
            self.corrVars.baseline_correlation_products_n_bls)

        # It's possible for a heap from each X engine and a descriptor heap
        # per endpoint to all arrive at once. We assume that each xengine will
        # not overlap packets between heaps, and that there is enough of a gap
        # between heaps that reordering in the network is a non-issue.
        stream_xengs = ring_heaps = (
            self.corrVars.baseline_correlation_products_n_chans // n_chans_per_substream)
        max_heaps = stream_xengs + 2 * self.corrVars.n_xengs
        # We need space in the memory pool for:
        # - live heaps (max_heaps, plus a newly incoming heap)
        # - ringbuffer heaps
        # - per X-engine:
        #   - heap that has just been popped from the ringbuffer (1)
        #   - active frames
        #   - complete frames queue (1)
        #   - frame being processed by ingest_session (which could be several, depending on
        #     latency of the pipeline, but assume 3 to be on the safe side)
        memory_pool_heaps = ring_heaps + max_heaps + stream_xengs * (active_frames + 5)
        memory_pool = spead2.MemoryPool(2**14, heap_data_size + 2**9,
                                        memory_pool_heaps, memory_pool_heaps)

        local_threadpool = spead2.ThreadPool()
        self.logger.debug('Created Spead2 stream instance with max_heaps=%s and ring_heaps=%s' % (
            max_heaps, ring_heaps))
        strm = s2rx.Stream(local_threadpool, max_heaps=max_heaps, ring_heaps=ring_heaps)
        del local_threadpool
        strm.set_memory_allocator(memory_pool)
        strm.set_memcpy(spead2.MEMCPY_NONTEMPORAL)
        return strm

    def process_xeng_data(self, heap_data, ig, baselines, channels, acc_scale=False):
        """
        Assemble data for the the plotting/printing thread to deal with.
        :param heap_data: heaps of data from the x-engines
        :param ig: the SPEAD2 item group
        :param baselines: which baselines are of interest?
        :param channels: the channels in which we are interested
        :param acc_scale: boolean, scale the data down or not
        :return:
        """
        # Calculate the substreams that have been captured
        n_substreams = self._stop_substream - self._strt_substream + 1
        n_chans_per_substream = self.corrVars.baseline_correlation_products_n_chans_per_substream
        chan_offset = n_chans_per_substream * self._strt_substream
        if 'xeng_raw' not in ig.keys():
            return None
        if ig['xeng_raw'] is None:
            return None
        xeng_raw = ig['xeng_raw'].value
        if xeng_raw is None:
            return None

        self.logger.info('PROCESSING %i BASELINES, %i CHANNELS' % (len(baselines),
                                                                   channels[1] - channels[0]))
        this_time = ig['timestamp'].value
        this_freq = ig['frequency'].value
        # start a new heap for this timestamp if it's not in our data
        if this_time not in heap_data:
            heap_data[this_time] = {}
        if this_time in heap_data:
            if this_freq in heap_data[this_time]:
                # already have this frequency - this seems to be a bug
                errstr = ('ERROR: time(%i) freq(%i) - repeat freq data received: ' % (
                    this_time, this_freq))
                old_data = heap_data[this_time][this_freq]
                if np.shape(old_data) != np.shape(xeng_raw):
                    errstr += ' DIFFERENT DATA SHAPE'
                else:
                    if (xeng_raw == old_data).all():
                        errstr += ' DATA MATCHES for repeat'
                    else:
                        errstr += ' DATA is DIFFERENT for repeat'
                self.logger.error(errstr)
            else:
                # save the frequency for this timestamp
                heap_data[this_time][this_freq] = xeng_raw
        # housekeeping - are there older heaps in the data?
        if len(heap_data) > 5:
            self.logger.info('Culling stale timestamps:')
            heaptimes = sorted(heap_data.keys())
            for ctr in range(0, len(heaptimes) - 5):
                heap_data.pop(heaptimes[ctr])
                self.logger.info('\ttime %i culled' % heaptimes[ctr])

        def process_heaptime(htime, hdata):
            """
            Process the heap for a given timestamp.
            :param htime:
            :param hdata:
            :return:
            """
            freqs = hdata.keys()
            self.logger.info('freqs = {}'.format(freqs))
            freqs.sort()
            check_range = range(n_chans_per_substream * self._strt_substream,
                                n_chans_per_substream * self._stop_substream + 1,
                                n_chans_per_substream)
            if freqs != check_range:
                self.logger.error(
                    'Did not get all frequencies from the x-engines for time %i: %s' % (
                        htime, str(freqs)))
                heap_data.pop(htime)
                return None
            vals = []
            for freq, xdata in hdata.items():
                vals.append((htime, freq, xdata))
            vals = sorted(vals, key=lambda val: val[1])
            xeng_raw = np.concatenate([val[2] for val in vals], axis=0)
            time_s = ig['timestamp'].value / (
                self.corrVars.baseline_correlation_products_n_chans * 2.0 * self.corrVars.n_accs)
            self.logger.info(
                'Processing xeng_raw heap with time 0x%012x (%.2fs since epoch) and shape: %s' % (
                    ig['timestamp'].value, time_s, str(np.shape(xeng_raw))))
            heap_data.pop(htime)
            # TODO scaling
            # scale_factor = float(ig['scale_factor_timestamp'].value)
            # sd_timestamp = ig['sync_time'].value + (ig['timestamp'].value /
            #                                         scale_factor)
            # logger.info('(%s) timestamp %i => %s' % (
            #     time.ctime(), ig['timestamp'].value, time.ctime(sd_timestamp)))
            # /TODO scaling
            baseline_data = []
            baseline_phase = []
            for baseline in baselines:
                bdata = xeng_raw[:, baseline]
                # TODO scaling
                # if acc_scale:
                #     bdata = bdata / (num_accs * 1.0)
                # /TODO scaling
                powerdata = []
                phasedata = []
                chan_range = range(channels[0] - chan_offset, channels[1] - chan_offset)
                if not self.realimag:
                    for ctr in chan_range:
                        complex_tuple = bdata[ctr]
                        pwr = np.sqrt(complex_tuple[0] ** 2 + complex_tuple[1] ** 2)
                        powerdata.append(pwr)
                        cplx = complex(complex_tuple[0], complex_tuple[1])
                        phase = np.angle(cplx)
                        phasedata.append(phase)
                else:
                    for ctr in chan_range:
                        complex_tuple = bdata[ctr]
                        powerdata.append(complex_tuple[0])
                        phasedata.append(complex_tuple[1])

                # TODO scaling
                # ?!broken?!
                # bdata = bdata[channels[0]:channels[1], :]
                # if acc_scale:
                #     bdata = bdata / (num_accs * 1.0)
                # powerdata = (bdata**2).sum(1)
                # phasedata = np.angle(bdata[:, 0] + (bdata[:, 1] * 1j))
                # /TODO scaling
                baseline_data.append((baseline, powerdata[:]))
                baseline_phase.append((baseline, phasedata[:]))
            return htime, baseline_data, baseline_phase

        # loop through the times we know about and process the complete ones
        rvs = {}
        heaptimes = heap_data.keys()

    #    heaptimes.sort()
    #    prev=heaptimes[0]
    #    for n,heaptime in enumerate(heaptimes):
    #        print(n, heaptime, heaptime-prev)
    #        prev=heaptime

        for heaptime in heaptimes:
            lendata = len(heap_data[heaptime])
            self.logger.debug('Processing heaptime 0x%012x, already have %i datapoints.' % (
                heaptime, lendata))
            # do we have all the data for this heaptime?
            if len(heap_data[heaptime]) == n_substreams:
                rv = process_heaptime(heaptime, heap_data[heaptime])
                if rv:
                    rvs[rv[0]] = (rv[1], rv[2])
                    _dump_timestamp = self.corrVars.sync_time + float(rv[0]) / self.corrVars.scale_factor_timestamp
                    _dump_timestamp_readable = time.strftime("%H:%M:%S",
                        time.localtime(_dump_timestamp))
                    self.logger.timedebug("Current Dump Timestamp: %s vs Current local time: %s" % (
                        _dump_timestamp_readable, time.strftime('%H:%M:%S')))
        return rvs

    def _get_plot_limits(self, baselines, channels):
        if (not baselines) or (not channels):
            self.logger.error('Print or plot requested, but no baselines and/or channels specified.')

        if baselines != '':
            if baselines == 'all':
                self.baselines = range(self.corrVars.baseline_correlation_products_n_bls)
            else:
                self.baselines = [int(bls) for bls in baselines.split(',')]
            self.logger.info('Given baselines: %s' % self.baselines)

        if not baselines:
            self.logger.error('No baselines to plot or print.')
            self.baselines = random.randrange(self.corrVars.baseline_correlation_products_n_bls)
            self.logger.warn("Randomly selected baselines %s to plot" % self.baselines)

        if channels:
            plot_startchan, plot_endchan = [int(channel) for channel in channels.split(',')]
            if plot_startchan == -1:
                plot_startchan = 0
            if plot_endchan == -1:
                plot_endchan = self.corrVars.baseline_correlation_products_n_chans - 1
            self.channels = (plot_startchan, plot_endchan)
            self.logger.info('Given channel range: %s' % str(self.channels))

    @staticmethod
    def network_interfaces():
        """
        Get system interfaces and IP list
        """
        def format_ip(addr):
            return "%s.%s.%s.%s" % (ord(addr[0]), ord(addr[1]), ord(addr[2]), ord(addr[3]))

        max_possible = 128  # arbitrary. raise if needed.
        bytes = max_possible * 32
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        names = array.array('B', '\0' * bytes)
        outbytes = struct.unpack('iL', fcntl.ioctl(s.fileno(), 0x8912,  # SIOCGIFCONF
                                                   struct.pack('iL', bytes, names.buffer_info()[0])))[0]
        namestr = names.tostring()
        lst = [format_ip(namestr[i + 20:i + 24]) for i in range(0, outbytes, 40)]
        return lst

    @staticmethod
    def corr_config(config_file=None, **kwargs):
        """
        Retrieve running correlator information from config file

        Parameters
        ----------
        config_file: string
            Running correlator config file.

        Returns
        -------
        config_info: dict
            Dictionary containing all defined requirements
        """
        logLevel = kwargs.get('log_level', 'INFO')
        assert config_file
        corr_instance = corr2.fxcorrelator.FxCorrelator('bob', config_source=config_file,
            logLevel=logLevel)
        corr_instance.initialise(configure=False, program=False, require_epoch=False, logLevel=logLevel)
        assert hasattr(corr_instance, "get_data_stream")
        fengine_conf = corr_instance.configd.get('fengine')
        assert isinstance(fengine_conf, dict)
        xengine_conf = corr_instance.configd.get('xengine')
        assert isinstance(xengine_conf, dict)
        output_products = xengine_conf.get("output_products")

        config_info = {}
        config_info['{}-destination'.format(output_products)] = corr_instance.get_data_stream(
            output_products).destination
        config_info["n-xengs"] = int(xengine_conf.get('x_per_fpga', 4)) * len(
            (xengine_conf.get('hosts')).split(','))
        assert hasattr(corr_instance, "n_antennas")
        config_info["n-ants"] = corr_instance.n_antennas
        assert hasattr(corr_instance, "xops")
        assert hasattr(corr_instance.xops, "get_baseline_ordering")
        config_info['{}-bls-ordering'.format(output_products)] = corr_instance.xops.get_baseline_ordering()
        config_info['{}-n-bls'.format(output_products)] = len(corr_instance.xops.get_baseline_ordering())
        config_info["{}-n-chans".format(output_products)] = int(fengine_conf.get('n_chans'))
        config_info["{}-n-chans-per-substream".format(output_products)] = int(int(
            fengine_conf.get('n_chans')) / config_info["n-xengs"])
        config_info['n-accs'] = corr_instance.xeng_accumulation_len * corr_instance.accumulation_len
        config_info['output_products'] = output_products
        config_info = {key.replace('-', '_'): value for key, value in config_info.items()}
        return config_info

    @staticmethod
    def get_sensors(servlet_ip=None, servlet_port=None,
        product_name='baseline-correlation-products'
    ):
        """
        Retrieve running instruments sensors.

        Parameters
        ----------
        servlet_ip: str
            IP address of the cmc?

        servlet_port: str
            katcp port number [defaults: 7148]

        product_name: str
            Instrument product name

        Return
        ------
        sensors: dict
            Dictionary containing all the predefined information
        """
        try:
            assert servlet_ip, servlet_port
        except AssertionError:
            raise RuntimeError('servlet_ip or servlet_port cannot be `None`')

        client = katcp.BlockingClient(servlet_ip, servlet_port)
        client.setDaemon(True)
        client.start()
        is_connected = client.wait_connected(10)
        if not is_connected:
            client.stop()
            raise RuntimeError('Could not connect to corr2_servlet, timed out.')
        reply, informs = client.blocking_request(katcp.Message.request('sensor-value'), timeout=5)
        client.stop()
        if not reply.reply_ok():
            raise RuntimeError('Could not read sensors from corr2_servlet, request failed.')
        sensors_required = ['{}-n-chans'.format(product_name),
                            '{}-n-accs'.format(product_name),
                            # '{}-destination'.format(product_name),
                            '{}-n-bls'.format(product_name),
                            '{}-bls-ordering'.format(product_name),
                            '{}-n-accs'.format(product_name),
                            'n-ants',
                            'n-xengs',
                            'scale-factor-timestamp',
                            'sync-time',
                            ]
        search = re.compile('|'.join(sensors_required))
        sensors = {}
        for inf in informs:
            if search.match(inf.arguments[2]):
                try:
                    sensors[inf.arguments[2].replace('-', '_')] = eval(inf.arguments[4])
                except Exception:
                    sensors[inf.arguments[2].replace('-', '_')] = inf.arguments[4]

        return sensors



if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Receive data from a corr2 correlator.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--config', dest='config', action='store', default='',
        help='Specify a config file (instead of a servlet).')
    parser.add_argument(
        '--servlet', dest='servlet', action='store', default='127.0.0.1:7601',
        help='ip and port of running corr2_servlet')
    parser.add_argument(
        '--product', dest='prodname', action='store',
        default='baseline-correlation-products',
        help='name of correlation product')
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
        '--channels', dest='channels', action='store', default='-1,-1',
        type=str, help='a (start,end) tuple, -1 means 0, n_chans respectively')
    parser.add_argument(
        '--warmup_cap', dest='warmup_capture', action='store_true', default=False,
        help=('This runs a capture once with only one substream.'
              'It seems to be needed to get larger captures to work.'
              'After the warm-up loop the normal loop runs'))
    parser.add_argument(
        '--log', dest='log', action='store_true', default=False,
        help='Logarithmic y axis.')
    parser.add_argument(
        '--ion', dest='ion', action='store_true', default=False,
        help='Animate the plot automatically.')
    parser.add_argument(
        '--scale', dest='scale', action='store_true', default=False,
        help='Scale the data by the number of accumulations.')
    parser.add_argument(
        '--legend', dest='legend', action='store_true', default=False,
        help='Show a plot legend.')
    parser.add_argument(
        '--loglevel', dest='log_level', action='store', default='INFO',
        help='log level to use, default INFO, options INFO, DEBUG, ERROR')
    parser.add_argument(
        '--speadloglevel', dest='spead_log_level', action='store', default='ERROR',
        help=('log level to use in spead receiver, default ERROR, options INFO, DEBUG, ERROR'))
    parser.add_argument(
        '--ri', dest='ri', action='store_true',
        default=False, help='plot/print real and imag rather than pwr and phs.')
    args = parser.parse_args()

    log_level = None
    if args.log_level:
        try:
            log_level = args.log_level.strip().upper()
            logger = LoggingClass(log_level=log_level).logger
        except AttributeError:
            raise RuntimeError('No such log level: %s' % log_level)

    spead_log_level = None
    if args.spead_log_level:
        spead_log_level = args.spead_log_level.strip().upper()
        spead2._logger.setLevel(getattr(logging, spead_log_level))

    # start the receiver thread
    logger.info('Initialising SPEAD transports for data:')
    corr_rx = CorrReceiver(
        config_file=args.config,
        baselines=args.baselines,
        channels=args.channels,
        warmup_capture=args.warmup_capture,
        realimag=args.ri,
        log_level=log_level,
    )

    # if there are baselines to plot, set up a plotter that will pull
    # data from a data queue
    baselines = corr_rx.corrVars.baseline_correlation_products_bls_ordering
    plotsumer = None
    if args.plot:
        if not len(baselines):
            raise RuntimeError('plot requested, but no baselines specified.')
        if args.ion:
            figure = plt.figure()
            figure.add_subplot(2, 1, 1)
            figure.add_subplot(2, 1, 2)
            plotsumer = PlotConsumer(figure=figure, legend=args.legend, baselines=baselines, animated=args.ion)
            plt.show(block=False)
        else:
            plotsumer = PlotConsumer(figure=None, legend=args.legend, baselines=baselines, animated=args.ion)
        logger.info('Plot started, waiting for data.')
        corr_rx.set_plot_queue(plotsumer.data_queue, plotsumer.need_data_flag)

    # are we printing data to the screen?
    printsumer = None
    if args.printdata:
        printsumer = PrintConsumer(baselines)
        corr_rx.set_print_queue(printsumer.data_queue, printsumer.need_data_flag)

    try:
        corr_rx.start()
        while corr_rx.isAlive():
            if plotsumer:
                plotsumer.plot_data(logger)
            if printsumer:
                printsumer.print_data(logger)
            time.sleep(0.1)
            sys.stdout.flush()
        logger.warn('RX process ended.')
        corr_rx.join()
    except KeyboardInterrupt:
        import gc
        gc.collect()
        corr_rx.quit_event.set()
        logger.warn('Stopping, waiting for thread to exit...')
        sys.stdout.flush()
        while corr_rx.quit_event.is_set():
            gc.collect()
            print('.', end='')
            sys.stdout.flush()
            time.sleep(0.1)
        logger.info('all done.')

# end
