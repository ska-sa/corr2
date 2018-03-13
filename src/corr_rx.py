#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
 Capture utility for a relatively generic packetised correlator data output stream.
"""
import array
import copy
import fcntl
import logging
import numpy as np
import Queue
import re
import socket
import spead2
import spead2.recv as s2rx
import struct
import threading
import time

from subprocess import check_output
from casperfpga import network
from casperfpga import tengbe
from corr2 import data_stream
from corr2 import utils

LOGGER = logging.getLogger(__name__)
interface_prefix = "10.100"

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
                             'DIFFERENT SHAPE?!\n' % (this_freq, this_time))
            else:
                if (xeng_raw == old_data).all():
                    self.logger.error('Got repeat freq %i with SAME data for time %i' % (
                                      this_freq, this_time))
                else:
                    self.logger.error('Got repeat freq %i with DIFFERENT data '
                                      'for time %i\n\tFile:%s Line:%s' % (this_freq, this_time))
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
            self.logger.error('Did not get all frequencies from the x-engines for time %i: %s' % (
                htime, str(freqs)))
            heap_data.pop(htime)
            return None
        vals = []
        for freq, xdata in hdata.items():
            vals.append((htime, freq, xdata))
        vals = sorted(vals, key=lambda val: val[1])
        xeng_raw = np.concatenate([val[2] for val in vals], axis=0)
        time_s = ig['timestamp'].value / (self.n_chans * 2 * self.n_accs)
        self.logger.info('Processing xeng_raw heap with time %i (%i) and shape: %s' % (
                        ig['timestamp'].value, time_s, str(np.shape(xeng_raw))))
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
                _dump_timestamp = (self.sync_time + float(rv[0]) / self.scale_factor_timestamp)
                _dump_timestamp_readable = time.strftime("%H:%M:%S", time.localtime(
                    _dump_timestamp))
                rvs['timestamp'] = rv[0]
                rvs['dump_timestamp'] = _dump_timestamp
                rvs['dump_timestamp_readable'] = _dump_timestamp_readable
                rvs['xeng_raw'] = rv[1]
    return rvs

def network_interfaces():
    """
    Get system interfaces and IP list
    """
    def format_ip(addr):
        return "%s.%s.%s.%s" %(ord(addr[0]), ord(addr[1]), ord(addr[2]), ord(addr[3]))

    max_possible = 128  # arbitrary. raise if needed.
    bytes = max_possible * 32
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    names = array.array('B', '\0' * bytes)
    outbytes = struct.unpack('iL', fcntl.ioctl(s.fileno(), 0x8912,  # SIOCGIFCONF
               struct.pack('iL', bytes, names.buffer_info()[0])))[0]
    namestr = names.tostring()
    lst = [format_ip(namestr[i + 20:i + 24]) for i in range(0, outbytes, 40)]
    return lst


class CorrRx(threading.Thread):
    """Run a spead receiver in a thread; provide a Queue.Queue interface
    Places each received valid data dump (i.e. contains xeng_raw values) as a pyspead
    ItemGroup into the `data_queue` attribute. If the Queue is full, the newer dumps will
    be discarded.
    """
    def __init__(self, product_name='baseline-correlation-products', katcp_ip='127.0.0.1',
                 katcp_port=7147, port=7148, queue_size=3):
        self.logger = LOGGER
        self.quit_event = threading.Event()
        self.data_queue = Queue.Queue(maxsize=queue_size)
        self.running_event = threading.Event()
        self.data_port = int(port)
        self.product_name = product_name
        self.katcp_ip = katcp_ip
        self.katcp_port = int(katcp_port)
        self.get_sensors()
        threading.Thread.__init__(self)

    def confirm_multicast_subs(self, mul_ip='239.100.0.10'):
        """
        Confirm whether the multicast subscription was a success or fail.
        :param str: multicast ip
        :retur str: successful or failed
        """
        list_inets = check_output(['ip','maddr','show'])
        return 'Successful' if str(mul_ip) in list_inets else 'Failed'

    def get_sensors(self):
        """
        Before doing much of anything, We need to get information from sensors
        """
        product_name = self.product_name
        try:
            import katcp
            client = katcp.BlockingClient(self.katcp_ip, self.katcp_port)
            client.setDaemon(True)
            client.start()
            is_connected = client.wait_connected(10)
            if not is_connected:
                client.stop()
                raise RuntimeError('Could not connect to katcp, timed out.')

            reply, informs = client.blocking_request(katcp.Message.request('sensor-value'),
                timeout=5)
            assert reply.reply_ok()
            client.stop()
            client = None

            sensors_required = ['n-ants',
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
            try:
                self.n_accs = int(sensors['{}-n-accs'.format(product_name)])
            except Exception:
                self.n_accs = int(float(sensors['{}-n-accs'.format(product_name)]))
            self.n_ants = int(sensors.get('n-ants', 0))
            self.sync_time = float(sensors.get('sync-time', 0))
            self.scale_factor_timestamp = float(sensors.get('scale-factor-timestamp', 0))
        except Exception:
            msg = 'Failed to connect to katcp and retrieve sensors values'
            self.logger.exception(msg)
            raise RuntimeError(msg)
        else:
            output = {
                        'product': product_name,
                        'address': data_stream.StreamAddress.from_address_string(
                            sensors['{}-destination'.format(product_name)])
                     }
            self.NUM_XENG = output['address'].ip_range
            self.data_ip = output['address'].ip_address

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
        self.logger.info('RXing data on %s+%i, port %i.' % (self.data_ip, self.NUM_XENG, self.data_port))
        self.interface_address = ''.join([ethx for ethx in network_interfaces()
                                         if ethx.startswith(interface_prefix)])
        self.logger.info("Interface Address: %s" % self.interface_address)
        self.strm = strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0, max_heaps=self.NUM_XENG,
                            ring_heaps=40)
        for ctr in range(self.NUM_XENG):
            self._addr = network.IpAddress(self.data_ip.ip_int + ctr).ip_str
            strm.add_udp_reader(multicast_group=self._addr,
                                port=self.data_port,
                                max_size=9200,
                                buffer_size=5120000,
                                interface_address=self.interface_address
                                )

        try:
            self.running_event.set()
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
                self.logger.debug('PROCESSING HEAP idx(%i) cnt(%i) cnt_diff(%i) @ %.4f' % (
                    idx, heap.cnt, cnt_diff, time.time()))
                self.logger.debug('Contents dict is now %i long' % len(heap_contents))
                # output item values specified
                data = process_xeng_data(self, heap_contents, ig)
                ig_copy = copy.deepcopy(data)
                if ig_copy:
                    try:
                        self.data_queue.put(ig_copy)
                    except Queue.Full:
                        self.logger.info('Data Queue full, disposing of heap %s.'%idx)

                # should we quit?
                if self.quit_event.is_set():
                    self.logger.info('Got a signal from main(), exiting rx loop...')
                    break
        finally:
            try:
                strm.stop()
                self.logger.info("SPEAD receiver stopped")
            except Exception:
                self.logger.exception('Exception trying to stop self.rx')
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
        for i in xrange(int(discard)):
            self.logger.info('Discarding #%s dump(s):'%i)
            try:
                _dump = self.data_queue.get(timeout=dump_timeout)
                assert _dump is not None
            except AssertionError:
                _errmsg = ('Dump data type cannot be nonetype, '
                           'confirm you are subscribed to multicast group.')
                self.logger.exception(_errmsg)
            except Queue.Empty:
                _stat = self.confirm_multicast_subs(self._addr)
                _errmsg = ('Data queue empty, Multicast subscription %s.'%_stat)
                self.logger.exception(_errmsg)
            except Exception:
                self.logger.exception()
        try:
            self.logger.info('Waiting for a clean dump:')
            _dump = self.data_queue.get(timeout=dump_timeout)
            _errmsg = ('No of channels in the spead data is inconsistent with the no of'
                      ' channels (%s) expected' %self.n_chans)
            assert _dump['xeng_raw'].shape[0] == self.n_chans, _errmsg
            _errmsg = ('Dump data type cannot be nonetype, confirm you are subscribed to multicast group.')
            assert _dump is not None, _errmsg
        except AssertionError:
            self.logger.error(_errmsg)
            raise RuntimeError(_errmsg)
        except Queue.Empty:
            _stat = self.confirm_multicast_subs(self._addr)
            _errmsg = ('Data queue empty, Multicast subscription %s.'%_stat)
            self.logger.exception(_errmsg)
        else:
            self.logger.info('Received clean dump.')
            return _dump
