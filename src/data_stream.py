import logging
import spead2
import spead2.send
import struct
import socket

from casperfpga.tengbe import IpAddress

from fxcorrelator_speadops import SPEAD_ADDRSIZE

LOGGER = logging.getLogger(__name__)

DIGITISER_ADC_SAMPLES = 0  # baseband-voltage
FENGINE_CHANNELISED_DATA = 1  # antenna-channelised-voltage
XENGINE_CROSS_PRODUCTS = 2  # baseline-correlation-products
BEAMFORMER_FREQUENCY_DOMAIN = 3  # tied-array-channelised-voltage
BEAMFORMER_TIME_DOMAIN = 4  # tied-array-voltage
BEAMFORMER_INCOHERENT = 5  # incoherent-beam-total-power
FLYS_EYE = 6  # antenna-correlation-products
ANTENNA_VOLTAGE_BUFFER = 7  # antenna-voltage-buffer

SPEAD_PKT_TTL = 2


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
        return '%s+%i:%i' % (self.ip_address, self.ip_range-1, self.port)

    def __str__(self):
        return '%s+%i:%i' % (self.ip_address, self.ip_range-1, self.port)


def _setup_spead_tx(ip_string, port):
    """
    Set up a SPEAD transmitter.
    :param ip_string: where are messages on this socket sent?
    :param port: and on which port?
    :return:
    """
    streamconfig = spead2.send.StreamConfig(
        max_packet_size=4096, max_heaps=8, rate=100e6)
    streamsocket = socket.socket(
        family=socket.AF_INET, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_IP)
    ttl_bin = struct.pack('@i', SPEAD_PKT_TTL)
    streamsocket.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_TTL,
        ttl_bin)
    tx = spead2.send.UdpStream(
        spead2.ThreadPool(), ip_string, port,
        streamconfig, 64 * 1024, streamsocket)
    return tx


class SPEADStream(object):
    """
    A DataStream that is also a SPEAD stream.
    Sends SPEAD data descriptors on tx_enable.
    """
    def __init__(self, name, category, destination):
        """
        Make a SPEAD stream.
        :param name: the name of the stream
        :param category: what kind of stream is this
        :param destination: where is it going?
        :return:
        """
        self.name = name
        self.category = category
        self.destination = None
        self.source = None
        self.descr_tx = None
        self.tx_enabled = False
        self.descr_ig = spead2.send.ItemGroup(
            flavour=spead2.Flavour(4, 64, SPEAD_ADDRSIZE))
        self.descriptors_setup()
        self.set_destination(destination)

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
            LOGGER.warning('%s: stream destination not set' % self.name)
            return
        if not hasattr(new_dest, 'ip_address'):
            new_dest = StreamAddress.from_address_string(new_dest)
        self.destination = new_dest
        # make the SPEAD transmitters, one for every address
        self.descr_tx = []
        for dest_ctr in range(self.destination.ip_range):
            ip = IpAddress.ip2str(int(self.destination.ip_address) + dest_ctr)
            LOGGER.info('Making speadtx for stream %s: %s:%d' % (
                self.name, str(ip), self.destination.port))
            tx = _setup_spead_tx(ip, self.destination.port)
            self.descr_tx.append(tx)

    def descriptors_issue(self):
        """
        Issue the data descriptors for this data stream
        :return:
        """
        if (not self.descr_ig) or (not self.descr_tx):
            LOGGER.debug('%s: descriptors have not been set up for '
                         'stream yet.' % self.name)
            return
        ctr = 0
        for tx in self.descr_tx:
            tx.send_heap(self.descr_ig.get_heap(descriptors='all', data='all'))
            ctr += 1
        LOGGER.info('SPEADStream %s: sent descriptors to %d destination%s' % (
            self.name, ctr, '' if ctr == 1 else 's'))

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
