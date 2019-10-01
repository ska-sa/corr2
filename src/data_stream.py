from logging import INFO
import struct
import socket
import time

import lazy_import
lazy_import.lazy_module("spead2")
lazy_import.lazy_module("spead2.send")

import spead2
import spead2.send

from casperfpga.network import IpAddress

from fxcorrelator_speadops import SPEAD_ADDRSIZE
# from corr2LogHandlers import getLogger

DIGITISER_ADC_SAMPLES = 0  # baseband-voltage
FENGINE_CHANNELISED_DATA = 1  # antenna-channelised-voltage
XENGINE_CROSS_PRODUCTS = 2  # baseline-correlation-products
BEAMFORMER_FREQUENCY_DOMAIN = 3  # tied-array-channelised-voltage
BEAMFORMER_TIME_DOMAIN = 4  # tied-array-voltage
BEAMFORMER_INCOHERENT = 5  # incoherent-beam-total-power
FLYS_EYE = 6  # antenna-correlation-products
ANTENNA_VOLTAGE_BUFFER = 7  # antenna-voltage-buffer

SPEAD_PKT_TTL = 5


class StreamAddress(object):
    """
    A data source from an IP. Holds all the information we need to use
    that data source.
    """

    def __init__(self, ip_string, ip_range, port):
        """

        :param ip_string: the ip address at which it can be found - a dotted
        decimal STRING
        :param ip_range: the consecutive number of IPs over which it is spread
        :param port: the port to which it is sent
        :return:
        """
        self.ip_address = IpAddress(ip_string)
        self.ip_range = ip_range
        self.port = port

    @staticmethod
    def _parse_address_string(address_string):
        """

        :param address_string:
        :return:
        """
        try:
            _bits = address_string.split(':')
            port = int(_bits[1])
            if '+' in _bits[0]:
                address, number = _bits[0].split('+')
                number = int(number) + 1
            else:
                address = _bits[0]
                number = 1
            assert(len(address.split('.')) == 4)
        except ValueError:
            raise RuntimeError('The address %s is not correctly formed. Expect '
                               '1.2.3.4+50:7777. Bailing.', address_string)
        return address, number, port

    @classmethod
    def from_address_string(cls, address_string):
        """
        Parse a 1.2.3.4+50:7777 string and return a StreamAddress
        :param address_string:
        :return:
        """
        address, number, port = StreamAddress._parse_address_string(
            address_string)
        return cls(address, number, port)

    def is_multicast(self):
        """
        Does the data source's IP address begin with 239?
        :return:
        """
        return self.ip_address.is_multicast()

    def __eq__(self, other):
        """
        Override the default Equals behavior
        """
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        """
        Define a non-equality test
        """
        if isinstance(other, self.__class__):
            return not self.__eq__(other)
        return NotImplemented

    def __repr__(self):
        return '%s+%i:%i' % (self.ip_address, self.ip_range - 1, self.port)

    def __str__(self):
        return '%s+%i:%i' % (self.ip_address, self.ip_range - 1, self.port)


def _setup_spead_tx(threadpool, ip_string, port, max_pkt_size):
    """
    Set up a SPEAD transmitter.
    :param ip_string: where are messages on this socket sent?
    :param port: and on which port?
    :param max_pkt_size: maximum packet size for this stream
    :return:
    """
    streamconfig = spead2.send.StreamConfig(
        max_packet_size=max_pkt_size, max_heaps=8, rate=100e6)
    streamsocket = socket.socket(
        family=socket.AF_INET, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_IP)
    ttl_bin = struct.pack('@i', SPEAD_PKT_TTL)
    streamsocket.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_TTL,
        ttl_bin)
    tx = spead2.send.UdpStream(
        threadpool, ip_string, port,
        streamconfig, 8192, streamsocket)
    return tx


class SPEADStream(object):
    """
    A DataStream that is also a SPEAD stream.
    Sends SPEAD data descriptors on tx_enable.
    """

    def __init__(self, name, category, destination, max_pkt_size=4096, *args, **kwargs):
        """
        Make a SPEAD stream.
        :param name: the name of the stream
        :param category: what kind of stream is this
        :param destination: where is it going?
        :param max_pkt_size: maximum packet size for this stream
        :return:
        """
        # This will always be a kwarg
        self.getLogger = kwargs['getLogger']
        try:
            instrument_descriptor = kwargs['instrument_descriptor']
            logger_name = '{}.{}_SPEADStream'.format(instrument_descriptor, name)
        except KeyError:
            logger_name = '{}_SPEADStream'.format(name)
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)
        result, self.logger = self.getLogger(logger_name=logger_name,
                                        log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        self.logger.debug('Successfully created logger for {}'.format(logger_name))

        self.name = name
        self.category = category
        self.destination = None
        self.source = None
        self.tx_enabled = False
        self.tx_sockets = None
        self.threadpool = spead2.ThreadPool()
        self.descr_ig = spead2.send.ItemGroup(
            flavour=spead2.Flavour(4, 64, SPEAD_ADDRSIZE))
        self.descriptors_setup()
        self.max_pkt_size = max_pkt_size;
        self.set_destination(new_dest=destination)

    def descriptors_setup(self):
        """
        Set up the item descriptors for this stream. This must be implemented
        by the subclass.
        :return:
        """
        raise NotImplementedError

    def set_source(self, new_source):
        """
        Set the source(s) for this stream
        :param new_source: a single IP or list of IPs
        :return:
        """
        if not hasattr(new_source, 'append'):
            new_source = [new_source]
        srcs = []
        for src in new_source:
            if hasattr(src, 'ip_address'):
                srcs.append(src)
            else:
                srcs.append(StreamAddress.from_address_string(src))
        self.source = srcs

    def set_destination(self, new_dest):
        """
        Set the destination for this stream
        :param new_dest: the new destination to use
        :return:
        """
        if new_dest is None:
            self.logger.warning('%s: stream destination not set' % self.name)
            return
        if not hasattr(new_dest, 'ip_address'):
            new_dest = StreamAddress.from_address_string(new_dest)
        self.destination = new_dest
        self.tx_sockets = []
        ctr = 0
        for dest_ctr in range(self.destination.ip_range):
            ip = IpAddress.ip2str(int(self.destination.ip_address) + dest_ctr)
            self.tx_sockets.append(_setup_spead_tx(threadpool=self.threadpool,
                                                   ip_string=ip,
                                                   port=self.destination.port,
                                                   max_pkt_size=self.max_pkt_size))
            #################Determining Packet ID start location#################
            #IP Component of Packet ID
            ip_arr = ip.split('.')
            ip_int = (int(ip_arr[0]) << 24) + (int(ip_arr[1]) << 16) + (int(ip_arr[2]) << 8) + (int(ip_arr[3]) << 0)
            #Time Component of Packet ID
            time_int = int(round(time.time()))
            #Combine these to create a single 48 bit packet id
            time_int = time_int & 0xffff
            ip_int = ip_int & 0xffffffff
            packet_id_int = ((ip_int << 16) + (time_int << 0)) & 0xffffffffffff
            self.tx_sockets[-1].set_cnt_sequence(packet_id_int,1)
            ################Packet ID Set###############
            ctr += 1

    def descriptors_issue(self):
        """
        Issue the data descriptors for this data stream
        :return:
        """
        if (not self.descr_ig) or (not self.destination):
            self.logger.debug('%s: descriptors have not been set up for '
                         'stream yet.' % self.name)
            return
        if (not self.tx_sockets):
            self.logger.debug('%s: tx sockets have not been set up for '
                         'stream yet.' % self.name)
            return

        i = 0
        for dest_ctr in range(self.destination.ip_range):
            i += 1
            self.tx_sockets[dest_ctr].send_heap(self.descr_ig.get_heap(descriptors='all', data='all'))

        self.logger.debug('SPEADStream %s: sent descriptors to %i destinations' % (self.name, dest_ctr + 1))

    def descriptor_issue_single(self, index):
        """
        Issue a single data descriptor
        :return:
        """
        if (not self.descr_ig) or (not self.destination):
            self.logger.debug('%s: descriptors have not been set up for '
                         'stream yet.' % self.name)
            return
        if (not self.tx_sockets):
            self.logger.debug('%s: tx sockets have not been set up for '
                         'stream yet.' % self.name)
            return

        dest_ctr = self.destination.ip_range
        if (index < 0 or index >= self.destination.ip_range):
            self.logger.error('%s: Tried to issue discriptor out of range (%i descriptors, index: %i).' % (self.name, dest_ctr, index))
            return
        
        if(self.tx_enabled):
            self.tx_sockets[index].send_heap(self.descr_ig.get_heap(descriptors='all', data='all'))
            self.logger.debug('SPEADStream %s: sent descriptor %i of %i destinations' % (self.name, index, dest_ctr))
        else:
            self.logger.debug('SPEADStream %s: DId not send descriptor %i of %i destinations, beam disabled' % (self.name, index, dest_ctr))

    def get_num_descriptors(self):
        """
        Issue a single data descriptor
        :return: returns number of descriptors
        """
        if (not self.descr_ig) or (not self.destination):
            self.logger.debug('%s: descriptors have not been set up for '
                         'stream yet.' % self.name)
            return -1
        if (not self.tx_sockets):
            self.logger.debug('%s: tx sockets have not been set up for '
                         'stream yet.' % self.name)
            return -1

        return self.destination.ip_range

    def tx_enable(self):
        """
        Enable TX for this data stream
        :return:
        """
        # when implementing this, you should issue descriptors
        # before enabling the hardware.
        raise NotImplementedError

    def tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        raise NotImplementedError

    def __str__(self):
        return 'SPEADStream %s:%i -> %s' % (
            self.name, self.category, self.destination)

    def __repr__(self):
        return 'SPEADStream(%s:%i:%s)' % (
            self.name, self.category, self.destination)
