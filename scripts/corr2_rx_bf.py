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
import math

import coloredlogs
import katcp
import matplotlib.pyplot as plt
import numpy as np
import spead2
import spead2.recv as s2rx

import casperfpga
import corr2
from casperfpga.network import IpAddress
from corr2 import data_stream
from IPython import embed


assert hasattr(corr2, "fxcorrelator")
assert hasattr(corr2.fxcorrelator, "FxCorrelator")
assert hasattr(casperfpga, "network")
assert hasattr(casperfpga.network, "IpAddress")

interface_prefix = "10.100"
_file_name = os.path.basename(sys.argv[0])

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
            coloredlogs.install(level=getattr(logging, self.log_level),
                fmt=log_format, datefmt='%Y.%m.%d %H:%M:%S')
            return logger
        except AttributeError:
            raise RuntimeError('No such log level: %s' % self.log_level)


class PlotConsumer(object):

    def __init__(self, channels, figure=None,log=False,plot_y_pol=False):
        """
        The Plot consumer - plots the contents it finds in the plot queue
        :param figure:
        :param log: Specify to do logarithmic scaling
        :return:
        """
        self.figure = figure
        self.data_queue = Queue.Queue(maxsize=1)
        self.need_data_flag = threading.Event()
        self.need_data_flag.set()
        self.running = threading.Event()
        self.plot_counter = 0
        self.log=log
        self.channels=channels
        self.plot_y_pol = plot_y_pol
        # callbacks could be useful?
        # self.figure.canvas.mpl_connect('close_event', self.on_close)
        # self.figure.canvas.mpl_connect('key_release_event', self.redraw)

    def plot_data(self, logger):
        try:
            plotdata = self.data_queue.get_nowait()
        except Queue.Empty:
            return
        # sys.stdout.flush()

        self.figure.subplots_adjust(hspace=0.5)
        sbplt = self.figure.axes
        sbplt[0].cla()
        if(self.plot_y_pol):
            sbplt[0].set_title('Y Polarisation Average Power - %s' % self.plot_counter)
        else:
            sbplt[0].set_title('X Polarisation Average Power - %s' % self.plot_counter)
        sbplt[0].grid(True)
        lines = []
        names = []
        if(self.log):
            plotdata[[plotdata==0]]=1
            plotdata = 20*np.log(plotdata);
            sbplt[0].set_ylim(bottom = 0, top=np.amax(plotdata)*1.1)
            sbplt[0].plot(range(self.channels[0],self.channels[1]+1),plotdata)
            sbplt[0].set_ylabel("Log Scale")
        else:
            sbplt[0].plot(range(self.channels[0],self.channels[1]+1),plotdata)
            sbplt[0].set_ylabel("Linear Scale")
        sbplt[0].set_xlabel("Bin Number")
        sbplt[0].set_xlim(left = self.channels[0],right=self.channels[1])
        self.plot_counter += 1
        figure.canvas.draw()
        self.need_data_flag.set()


class CorrReceiver(LoggingClass, threading.Thread):
    """
    Receive thread to process heaps received by a SPEAD2 stream.
    """

    def __init__(
        self, servlet="127.0.0.1:7601", config_file=None, channels=(0, 4095),plot_y_pol=False,
        **kwargs
    ):
        """

        Parameters
        ----------

        :param port: the port on which to receive data
        :param base_ip: the base IP address to subscribe to
        :param quit_event: quit if this thread_safe event is set
        :param track_list: a list of items to track
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
        # a quit event to stop the thread if needed
        self.quit_event = threading.Event()
        if log_level == 'DEBUG':
            spead2._logger.setLevel(getattr(logging, log_level))

        try:
            assert isinstance(self._config_file, str)
        except AssertionError:
            self.logger.error("No Config File defined!!!")
            raise

        self._config_info = self.corr_config(self._config_file, **kwargs)
        self._sensors_info = {}

        self.corrVars = DictObject(DictObject._dictsMerger(self._sensors_info,  self._config_info))
        self.corrVars.sync_time=0
        self.corrVars.scale_factor_timestamp=1712e6
        self._get_plot_limits(channels)
        self.n_channels_per_substream=-1
        self.plot_y_pol=plot_y_pol;
        self.need_plot_data = None

        threading.Thread.__init__(self)

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

        strm = self._spead_stream()
        self._mcast_subs(strm)


        # make the ItemGroup and some local vars
        item_group = spead2.ItemGroup()
        idx = 0
        last_cnt = -1 * self.corrVars.n_xengs

        heap_contents = {}

        # process received heaps
        for heap in strm:
            # should we quit?
            if self.quit_event.is_set():
                self.logger.warn('Got a signal from main(), exiting rx loop...')
                break
            item_group.update(heap)
            cnt_diff = heap.cnt - last_cnt
            last_cnt = heap.cnt
            self.logger.debug('Contents dict is now %i long' % len(heap_contents))
            if len(heap.get_items()) == 0:
                self.logger.error('Empty heap - was this descriptors?')
                continue
            # do we need to process more data?
            need_plot = self.need_plot_data.is_set()
            data = self.process_beng_data(heap_contents, item_group, self.channels)
            if type(data)==np.ndarray:
                self.logger.info('Received Data from all streams. Updating plot now')
                try:
                    offset = self.channels[0]-self._strt_substream*self.n_channels_per_substream
                    length = self.channels[1]-self.channels[0];
                    #embed()
                    self.plot_queue.put(data[offset:offset+length+1])
                except Queue.Full:
                    self.plot_queue.get()
                    self.plot_queue.put(data)
            # count processed heaps
            idx += 1

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
        if(self.plot_y_pol):
            base_ip = self.corrVars.tied_array_channelised_voltage_0y_destination
        else:
            base_ip = self.corrVars.tied_array_channelised_voltage_0x_destination

        self._interface_address = ''.join([ethx for ethx in self.network_interfaces()
                                           if ethx.startswith(interface_prefix)])

        #Determine IP address range to subscribe to
        plot_channels = self.channels
        total_channels = self.corrVars.baseline_correlation_products_n_chans
        self.n_channels_per_substream = total_channels/self.corrVars.n_xengs;
        self._strt_substream = int(math.floor(float(plot_channels[0])/self.n_channels_per_substream));
        self._stop_substream = int(math.floor(float(plot_channels[1])/self.n_channels_per_substream));
        self.logger.info('RXing data with base IP address: %s' % (base_ip))

        if self._stop_substream >= self.corrVars.n_xengs:
            self._stop_substream = self.corrVars.n_xengs - 1
        self.n_substreams = self._stop_substream - self._strt_substream + 1
        
        assert hasattr(base_ip, 'ip_address')
        start_ip = IpAddress(base_ip.ip_address.ip_int + self._strt_substream).ip_str
        end_ip = IpAddress(base_ip.ip_address.ip_int + self._stop_substream).ip_str
        
        self.logger.info('Subscribing to %s substream/s in the range %s to %s' % (self.n_substreams, start_ip, end_ip))
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

    def process_beng_data(self, heap_data, ig, channels, acc_scale=False):
        """
        Assemble data for the the plotting/printing thread to deal with.
        :param heap_data: heaps of data from the x-engines
        :param ig: the SPEAD2 item group
        :param channels: the channels in which we are interested
        :param acc_scale: boolean, scale the data down or not
        :return:
        """
        
        if 'bf_raw' not in ig.keys():
            self.logger.debug("CBF non-data heap received on stream ?")
            return None

        if ig['bf_raw'] is None:
            self.logger.warning("CBF Xengine data Null and Void.")
            return None

        beng_raw = ig['bf_raw'].value
        if beng_raw is None:
            self.logger.warning("CBF Xengine data Null and Void.")
            return None

        if 'timestamp' not in ig.keys():
            self.logger.warning("CBF heap without timestamp received on stream ?",)
            return None

        if 'frequency' not in ig.keys():
            self.logger.warning("CBF heap without frequency received on stream ?")
            return None


        this_freq = ig['frequency'].value

        # start a new heap for this frequency if it's not in our data
        #the timestamps for these different heaps are aligned. This allows us to capture a wider spectrum
        if this_freq not in heap_data:
            heap_data[this_freq] = beng_raw;
        # loop through the times we know about and process the complete ones
        rvs = None
        lendata = len(heap_data.keys())
        if(lendata == self.n_substreams):
            rvs = np.empty(0,dtype=int)
            for frequency in sorted(heap_data.keys()):
                samples_temp = np.square(heap_data.pop(frequency).astype(int)).sum(axis=(1,2))
                rvs = np.append(rvs,samples_temp)
        return rvs

    def _get_plot_limits(self, channels):
        if (not channels):
            self.logger.error('Print requested, but no channels specified.')

        if channels:
            plot_startchan, plot_endchan = [int(channel) for channel in channels.split(',')]
            if plot_startchan == -1:
                plot_startchan = 0
            if plot_endchan == -1 or (plot_endchan>self.corrVars.baseline_correlation_products_n_chans - 1):
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
        beam0_conf = corr_instance.configd.get('beam0');
        assert isinstance(beam0_conf, dict)
        beam1_conf = corr_instance.configd.get('beam1');
        assert isinstance(beam1_conf, dict)

        #X-Engine Config
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

        #Beam 0 Config
        output_products = beam0_conf.get("output_products")
        config_info['{}-destination'.format(output_products)] = corr_instance.get_data_stream(
            output_products).destination

        #Beam 1 Config
        output_products = beam1_conf.get("output_products")
        config_info['{}-destination'.format(output_products)] = corr_instance.get_data_stream(
            output_products).destination


        output_products = [xengine_conf.get("output_products"),beam0_conf.get("output_products"),beam1_conf.get("output_products")]
        config_info['output_products'] = output_products
        config_info = {key.replace('-', '_'): value for key, value in config_info.items()}
        config_info = {key.replace('.', '_'): value for key, value in config_info.items()}
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
        description='Receive beamformer data from a corr2 correlator.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--config', dest='config', action='store', default='',
        help='Specify a config file (instead of a servlet).')
    parser.add_argument(
        '--servlet', dest='servlet', action='store', default='127.0.0.1:7601',
        help='ip and port of running corr2_servlet')
    parser.add_argument(
        '--channels', dest='channels', action='store', default='-1,-1',
        type=str, help='a (start,end) tuple, -1 means 0, n_chans respectively')
    parser.add_argument(
        '--log', dest='log', action='store_true', default=False,
        help='Logarithmic y axis.')
    parser.add_argument(
        '-x','--x_pol', dest='x_pol', action='store_true', default=False,
        help='Plot the x polarisation.')
    parser.add_argument(
        '-y','--y_pol', dest='y_pol', action='store_true', default=False,
        help='Plot the y polarisation.')
    parser.add_argument(
        '--loglevel', dest='log_level', action='store', default='INFO',
        help='log level to use, default INFO, options INFO, DEBUG, ERROR')
    parser.add_argument(
        '--speadloglevel', dest='spead_log_level', action='store', default='ERROR',
        help=('log level to use in spead receiver, default ERROR, options INFO, DEBUG, ERROR'))

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

    plot_y_pol = False;
    if(args.x_pol == True and args.y_pol == True):
        logger.info('Both X and Y polarisations specified, plotting X polarisation only.')
    elif(args.y_pol == False):
        logger.info('Plotting X polarisation')
    else:
        logger.info('Plotting Y polarisation')
        plot_y_pol = True;

    # start the receiver thread
    logger.info('Initialising SPEAD transports for data:')
    corr_rx = CorrReceiver(
        config_file=args.config,
        channels=args.channels,
        log_level=log_level,
        plot_y_pol=plot_y_pol,
    )

    plotsumer = None
    figure = plt.figure()
    figure.add_subplot(1, 1, 1)
    plotsumer = PlotConsumer(corr_rx.channels,figure=figure,log=args.log,plot_y_pol=plot_y_pol)
    plt.show(block=False)
    logger.info('Plot started, waiting for data.')
    corr_rx.set_plot_queue(plotsumer.data_queue, plotsumer.need_data_flag)       

    #try:
    corr_rx.daemon = True
    corr_rx.start()
    while corr_rx.isAlive():
        if plotsumer:
            plotsumer.plot_data(logger)
        time.sleep(0.1)
        sys.stdout.flush()
    logger.warn('RX process ended.')
    corr_rx.join()

# end
