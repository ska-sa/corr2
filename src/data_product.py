import logging
import spead2
import spead2.send as sptx
import struct
import socket

from net_address import NetAddress
from fxcorrelator_speadops import SPEAD_ADDRSIZE

LOGGER = logging.getLogger(__name__)

DIGITISER_ADC_SAMPLES = 0
FENGINE_CHANNELISED_DATA = 1
XENGINE_CROSS_PRODUCTS = 2
BEAMFORMER_FREQUENCY_DOMAIN = 3
BEAMFORMER_TIME_DOMAIN = 4


def _setup_spead(meta_address):
    """
    Set up a SPEAD ItemGroup and transmitter.
    :param meta_address:
    :return:
    """
    meta_ig = sptx.ItemGroup(flavour=spead2.Flavour(4, 64, SPEAD_ADDRSIZE))
    streamconfig = sptx.StreamConfig(max_packet_size=4096, max_heaps=8)
    streamsocket = socket.socket(family=socket.AF_INET,
                                 type=socket.SOCK_DGRAM,
                                 proto=socket.IPPROTO_IP)
    ttl_bin = struct.pack('@i', 2)
    streamsocket.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_TTL,
        ttl_bin)
    meta_tx = sptx.UdpStream(spead2.ThreadPool(),
                             str(meta_address.ip),
                             meta_address.port,
                             streamconfig,
                             51200000,
                             streamsocket)
    return meta_ig, meta_tx


class DataProduct(object):
    """
    A data product produced by some instrument function. A name, a category,
    a NetAddress for data and one for metadata. Some callbacks to do things
    when these addresses change.
    """
    def __init__(self, name, category,
                 destination,
                 meta_destination,
                 tx_enable_method=None,
                 tx_disable_method=None,
                 destination_cb=None,
                 meta_destination_cb=None):
        """
        :param name: the name of this data product
        :param destination: a NetAddress for the stream data destination
        :param meta_destination: a NetAddress for the meta information
        :param destination_cb: a callback to run when this data product
        destination is updated
        :param meta_destination_cb: a callback to run when this data
        product meta destination is updated
        :param tx_enable_method: method to call to start transmission of this
        product
        :param tx_disable_method: method to call to stop transmission of this
        product
        :return:
        """
        self.name = name
        self.category = category
        # tx enable and disable methods
        self.en_cb = tx_enable_method
        self.dis_cb = tx_disable_method
        # destination
        self.destination = destination
        self.destination_cb = destination_cb
        # metadata
        self.meta_destination = meta_destination
        self.meta_destination_cb = meta_destination_cb
        # spead itemgroup and transmitter for metadata
        self.meta_ig, self.meta_tx = _setup_spead(self.meta_destination)

    def set_destination(self, ip, port):
        """
        Change the destination IP and port for this data product
        :param ip:
        :param port:
        :return:
        """
        if (ip == str(self.destination.ip)) and (port == self.destination.port):
            LOGGER.info('%s: destination already %s' %
                        (self.name, self.destination))
            return
        self.destination = NetAddress(ip, port)
        if self.destination_cb:
            self.destination_cb(self)
        LOGGER.info('%s: set destination to %s' %
                    (self.name, self.destination))

    def set_meta_destination(self, ip, port):
        """
        Change the meta destination IP and port for this data product
        :param ip:
        :param port:
        :return:
        """
        if (ip == str(self.meta_destination.ip)) and \
                (port == self.meta_destination.port):
            LOGGER.info('%s: meta_destination already %s' %
                        (self.name, self.meta_destination))
            return
        self.meta_destination = NetAddress(ip, port)
        self.meta_ig, self.meta_tx = _setup_spead(self.meta_destination)
        if self.meta_destination_cb:
            self.meta_destination_cb(self)
        LOGGER.info('%s: set meta destination to %s' % (
            self.name, self.meta_destination))

    def meta_issue(self):
        """
        Call the meta destination update callback, then transmit the metadata.
        :return:
        """
        self.meta_destination_cb(self)
        self.meta_transmit()

    def meta_transmit(self):
        """
        Send the metadata for this data product.
        :return:
        """
        if not self.meta_ig:
            LOGGER.info('SPEAD meta itemgroup for data product %s is '
                        'unavailable, not sending metadata.' %
                        self.name)
            return
        if not self.meta_tx:
            LOGGER.info('SPEAD meta transmitter for data product %s is '
                        'unavailable, not sending metadata.' %
                        self.name)
            return
        self.meta_tx.send_heap(self.meta_ig.get_heap())
        LOGGER.info('DataProduct %s sent SPEAD metadata to %s' % (
            self.name, self.meta_destination))

    def tx_enable(self):
        """
        Enable TX for this data product
        :return:
        """
        try:
            heapgen = sptx.HeapGenerator(self.meta_ig)
            self.meta_tx.send_heap(heapgen.get_start())
        except AttributeError:
            LOGGER.warning('Installed version of SPEAD2 doesn\'t seem to'
                           'support stream start packets?')
        self.en_cb(self)
        LOGGER.info('DataProduct %s - output enabled' % self.name)

    def tx_disable(self):
        """
        Disable TX for this data product
        :return:
        """
        self.dis_cb(self)
        try:
            heapgen = sptx.HeapGenerator(self.meta_ig)
            self.meta_tx.send_heap(heapgen.get_end())
        except AttributeError:
            LOGGER.warning('Installed version of SPEAD2 doesn\'t seem to'
                           'support stream stop packets?')
        LOGGER.info('DataProduct %s - output disabled' % self.name)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'DataProduct(%s:%i), data(%s) meta(%s)' % (
            self.name, self.category, self.destination, self.meta_destination)
