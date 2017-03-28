#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
 Capture utility for a relatively generic packetised correlator data output stream.
"""
import copy
import logging
import numpy as np
import Queue
import re
import spead2
import spead2.recv as s2rx
import subprocess
import sys
import threading
import time

from casperfpga import tengbe
from corr2 import utils, data_stream
from inspect import currentframe
from inspect import getframeinfo

LOGGER = logging.getLogger(__name__)

def confirm_multicast_subs(mul_ip='239.100.0.10' ,interface='eth2'):
    """
    Confirm whether the multicast subscription was a success or fail.
    :param str: multicast ip
    :param str: network interface
    :retur str: successful or failed
    """
    list_inets = subprocess.check_output(['ip','maddr','show', interface])
    return 'Successful' if str(mul_ip) in list_inets else 'Failed'

def process_xeng_data(self, heap_data, ig):
    """
    Assemble data for the the plotting/printing thread to deal with.
    :param self: corr_rx object
    :param heap_data: heaps of data from the x-engines
    :param ig: the SPEAD2 item group
    :return:
    """
    if 'xeng_raw' not in ig.keys():
        return None
    if ig['xeng_raw'] is None:
        return None
    xeng_raw = ig['xeng_raw'].value
    if xeng_raw is None:
        return None

    this_time = ig['timestamp'].value
    this_freq = ig['frequency'].value

    if this_time in heap_data:
        if this_freq in heap_data[this_time]:
            # already have this frequency - this seems to be a bug
            old_data = heap_data[this_time][this_freq]
            if np.shape(old_data) != np.shape(xeng_raw):
                self.logger.error('Got repeat freq %i for time %i, with a '
                             'DIFFERENT SHAPE?!\n\tFile:%s Line:%s' % (this_freq, this_time,
                                getframeinfo(currentframe()).filename.split('/')[-1],
                                getframeinfo(currentframe()).lineno))
            else:
                if (xeng_raw == old_data).all():
                    self.logger.error('Got repeat freq %i with SAME data for time '
                                 '%i\n\tFile:%s Line:%s' % (this_freq, this_time,
                                    getframeinfo(currentframe()).filename.split('/')[-1],
                                    getframeinfo(currentframe()).lineno))
                else:
                    self.logger.error('Got repeat freq %i with DIFFERENT data '
                                 'for time %i\n\tFile:%s Line:%s' % (
                                    this_freq, this_time,
                                    getframeinfo(currentframe()).filename.split('/')[-1],
                                    getframeinfo(currentframe()).lineno))
        else:
            heap_data[this_time][this_freq] = xeng_raw
    else:
        heap_data[this_time] = {this_freq: xeng_raw}

    # housekeeping - are the older heaps in the data?
    if len(heap_data) > 5:
        self.logger.info('Culling stale timestamps:')
        heaptimes = heap_data.keys()
        heaptimes.sort()
        for ctr in range(0, len(heaptimes)-5):
            heap_data.pop(heaptimes[ctr])
            self.logger.info('\ttime heaptimes[ctr] culled')

    def process_heaptime(htime, hdata):
        """

        :param htime:
        :param hdata:
        :return:
        """
        freqs = hdata.keys()
        freqs.sort()
        if freqs != range(0, self.n_chans, self.n_chans / self.NUM_XENG):
            self.logger.error('Did not get all frequencies from the x-engines for '
                         'time %i: %s' % (htime, str(freqs)))
            heap_data.pop(htime)
            return None
        vals = []
        for freq, xdata in hdata.items():
            vals.append((htime, freq, xdata))
        vals = sorted(vals, key=lambda val: val[1])
        xeng_raw = np.concatenate([val[2] for val in vals], axis=0)
        time_s = ig['timestamp'].value / (self.n_chans * 2 * self.n_accs)
        self.logger.info('Processing xeng_raw heap with time %i (%i) and '
                    'shape: %s' % (ig['timestamp'].value, time_s,
                                   str(np.shape(xeng_raw))))
        heap_data.pop(htime)
        return (htime, xeng_raw)
        # return {'timestamp': htime,
        #         'xeng_raw': xeng_raw}
    # loop through the times we know about and process the complete ones
    rvs = {}
    heaptimes = heap_data.keys()

    for heaptime in heaptimes:
        if len(heap_data[heaptime]) == self.NUM_XENG:
            rv = process_heaptime(
                heaptime, heap_data[heaptime])
            if rv:
                rvs['timestamp'] = rv[0]
                rvs['dump_timestamp'] = (self.sync_time + float(rv[0]) / self.scale_factor_timestamp)
                rvs['xeng_raw'] = rv[1]
    return rvs


class CorrRx(threading.Thread):
    """Run a spead receiver in a thread; provide a Queue.Queue interface
    Places each received valid data dump (i.e. contains xeng_raw values) as a pyspead
    ItemGroup into the `data_queue` attribute. If the Queue is full, the newer dumps will
    be discarded.
    """
    def __init__(self, product_name='baseline-correlation-products', servlet_ip='127.0.0.1',
                 servlet_port=7601, port=8888, queue_size=1000):
        self.logger = LOGGER
        self.quit_event = threading.Event()
        self.data_queue = Queue.Queue(maxsize=queue_size)
        self.running_event = threading.Event()
        self.data_port = int(port)
        self.product_name = product_name
        self.servlet_ip = servlet_ip
        self.servlet_port = int(servlet_port)
        self.multicast_subs()
        threading.Thread.__init__(self)

    def multicast_subs(self):
        # before doing much of anything, need to get metadata from sensors
        product_name = self.product_name
        try:
            import katcp
            client = katcp.BlockingClient(self.servlet_ip, self.servlet_port)
            client.setDaemon(True)
            client.start()
            is_connected = client.wait_connected(10)
            if not is_connected:
                client.stop()
                raise RuntimeError('Could not connect to corr2_servlet, timed out.')
            reply, informs = client.blocking_request(
                katcp.Message.request('sensor-value'), timeout=5)
            client.stop()
            client = None
            if not reply.reply_ok():
                raise RuntimeError('Could not read sensors from corr2_servlet, '
                                   'request failed.')
            sensors_required = [
                                'n-ants',
                                'scale-factor-timestamp',
                                'sync-time',
                                '{}-bls-ordering'.format(product_name),
                                '{}-destination'.format(product_name),
                                '{}-n-accs'.format(product_name),
                                '{}-n-accs'.format(product_name),
                                '{}-n-bls'.format(product_name),
                                '{}-n-chans'.format(product_name),
                                ]
            sensors = {}
            srch = re.compile('|'.join(sensors_required))
            for inf in informs:
                if srch.match(inf.arguments[2]):
                    sensors[inf.arguments[2]] = inf.arguments[4]
            self.n_chans = int(sensors['{}-n-chans'.format(product_name)])
            self.n_accs = int(sensors['{}-n-accs'.format(product_name)])
            self.n_ants = int(sensors['n-ants'])
            self.sync_time = float(sensors['sync-time'])
            self.scale_factor_timestamp = float(sensors['scale-factor-timestamp'])
        except Exception:
            msg = 'Failed to connect to corr2_servlet and retrieve sensors values'
            self.logger.exception(msg)
            raise RuntimeError(msg)
        else:
            output = {
                'product': product_name,
                'address': data_stream.StreamAddress.from_address_string(
                    sensors['{}-destination'.format(product_name)])
            }
            self.NUM_XENG = output['address'].ip_range

            def confirm_multicast_subs(mul_ip='239.100.0.10', interface='eth2'):
                """
                Confirmation as to the multicast subscription.
                """
                list_inets = subprocess.check_output(['ip','maddr','show', interface])
                if mul_ip in list_inets:
                    self.logger.info('Successfully subscribed to multicast.')
                    return True
                else:
                    self.logger.error('Failed to subscribed to multicast.')
                    return False

            if output['address'].ip_address.is_multicast():
                import socket
                import struct
                self.logger.info('Source is multicast: %s' % output['address'])

                # look up multicast group address in name server
                # and find out IP version
                addrinfo = socket.getaddrinfo(
                    str(output['address'].ip_address), None)[0]
                ip_version = addrinfo[0]

                # create a socket
                mcast_sock = socket.socket(ip_version, socket.SOCK_DGRAM)
                mcast_sock.setblocking(False)
                # mcast_sock.bind(('', 8888))
                # # Allow multiple copies of this program on one machine
                # # (not strictly needed)
                # mcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                #
                # # bind it to the port
                # mcast_sock.bind(('', data_port))
                # print 'Receiver bound to port %i.' % data_port

                def join_group(address):
                    group_bin = socket.inet_pton(ip_version, address)
                    if ip_version == socket.AF_INET:  # IPv4
                        mreq = group_bin + struct.pack('=I', socket.INADDR_ANY)
                        mcast_sock.setsockopt(socket.IPPROTO_IP,
                                              socket.IP_ADD_MEMBERSHIP, mreq)
                        self.logger.info('Subscribing to %s.' % address)
                    else:
                        mreq = group_bin + struct.pack('@I', 0)
                        mcast_sock.setsockopt(socket.IPPROTO_IPV6,
                                              socket.IPV6_JOIN_GROUP, mreq)

                # join group
                for addrctr in range(output['address'].ip_range):
                    self._addr = int(output['address'].ip_address) + addrctr
                    self._addr = tengbe.IpAddress(self._addr)
                    join_group(str(self._addr))
                return confirm_multicast_subs(mul_ip=str(self._addr))
            else:
                mcast_sock = None
                self.logger.info('Source is not multicast: %s' % output['src_ip'])
                return False

    def stop(self):
        self.quit_event.set()
        if hasattr(self, 'strm'):
            self.strm.stop()
            self.logger.info("SPEAD receiver stopped")
            if self.quit_event.isSet():
                self._Thread__stop()
                self.logger.info("FORCEFULLY Stopped SPEAD receiver")

    def stopped(self):
        return self._Thread__stopped

    def start(self, timeout=None):
        threading.Thread.start(self)
        if timeout is not None:
            self.running_event.wait(timeout)
        self.logger.info("SPEAD receiver started")

    def run(self):
        logger = self.logger
        logger.info('Data reception on port %i.' % self.data_port)

        self.strm = strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0,
                           max_heaps=40, ring_heaps=40)
        strm.add_udp_reader(port=self.data_port, max_size=9200,
                            buffer_size=51200000)
        self.running_event.set()

        try:
            ig = spead2.ItemGroup()
            idx = -1
            # we need these bits of meta data before being able to assemble and transmit
            # signal display data
            last_cnt = -1 * self.NUM_XENG
            heap_contents = {}
            for heap in self.strm:
                idx += 1
                updated = ig.update(heap)
                cnt_diff = heap.cnt - last_cnt
                last_cnt = heap.cnt
                logger.debug('PROCESSING HEAP idx(%i) cnt(%i) cnt_diff(%i) '
                             '@ %.4f' % (idx, heap.cnt, cnt_diff, time.time()))
                logger.debug('Contents dict is now %i long' % len(heap_contents))
                # output item values specified

                data = process_xeng_data(self, heap_contents, ig)
                ig_copy = copy.deepcopy(data)
                if ig_copy:
                    try:
                        self.data_queue.put(ig_copy)
                    except Queue.Full:
                        logger.info('Data Queue full, disposing of heap %s.'%idx)

                # should we quit?
                if self.quit_event.is_set():
                    logger.info('Got a signal from main(), exiting rx loop...')
                    break
        finally:
            try:
                strm.stop()
                logger.info("SPEAD receiver stopped")
            except Exception:
                logger.exception('Exception trying to stop self.rx')
            self.quit_event.clear()
            self.running_event.clear()

    def get_clean_dump(self, dump_timeout=10, discard=2):
        """
        Discard any queued dumps, discard one more, then return the next dump
        """
        try:
            while True:
                dump = self.data_queue.get_nowait()
        except Queue.Empty:
            pass

        # discard next dump too, in case
        for i in xrange(discard):
            LOGGER.info('Discarding #%s dump(s):'%i)
            try:
                _dump = self.data_queue.get(timeout=dump_timeout)
            except Queue.Empty:
                _stat = confirm_multicast_subs(self._addr)
                _errmsg = ('Data queue empty, Multicast subscription %s.'%_stat)
                self.logger.exception(_errmsg)
                raise RuntimeError(_errmsg)
            except Exception:
                self.logger.exception()
        try:
            LOGGER.info('Waiting for a clean dump:')
            _dump = self.data_queue.get(timeout=dump_timeout)
            assert _dump['xeng_raw'].shape[0] == self.n_chans
        except AssertionError:
            errmsg = ('No of channels in the spead data is inconsistent with the no of'
                      ' channels (%s) expected' %self.n_chans)
            self.logger.error(errmsg)
            raise RuntimeError(errmsg)
        else:
            LOGGER.info('Received clean dump.')
            return _dump