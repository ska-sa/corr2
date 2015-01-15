__author__ = 'paulp'

import logging

LOGGER = logging.getLogger(__name__)


class DataSource(object):
    """
    A data source from an IP. Holds all the information we need to use that data source.
    """
    def __init__(self, name, ip, iprange, port):
        """

        :param name: the name of this data source
        :param ip: the ip address at which it can be found
        :param iprange: the consecutive number of IPs over which it is spread
        :param port: the port to which it is sent
        :return:
        """
        self.name = name
        self.ip = ip
        self.iprange = iprange
        self.port = port

    @classmethod
    def from_mcast_string(cls, mcast_string):
        try:
            _bits = mcast_string.split(':')
            port = int(_bits[1])
            address, number = _bits[0].split('+')
            number = int(number) + 1
        except ValueError:
            raise RuntimeError('The address %s is not correctly formed. Expect 1.2.3.4+50:7777. Bailing.', mcast_string)
        return cls('<unnamed>', address, number, port)

    def __str__(self):
        return 'DataSource(%s) @ %s+%i port(%i)' % (self.name, self.ip, self.iprange, self.port)


class FengineSource(DataSource):
    """
    A data source for an f-engine. Holds all the information we need to use that data source.
    """
    def __init__(self, name, ip, iprange, port):
        """
        A DataSource representation of antenna data to an f-engine. So it has eq poly and bram
        :param name: the name of this data source
        :param ip: the ip address at which it can be found
        :param iprange: the consecutive number of IPs over which it is spread
        :param port: the port to which it is sent
        :return:
        """
        DataSource.__init__(self, name, ip, iprange, port)
        self.source_number = None
        self.eq_poly = None
        self.eq_bram = None

    def get_eq(self, hostdevice=None):
        """
        Get the EQ for this source.
        :param hostdevice:
        :return:
        """
        if hostdevice is not None:
            return hostdevice.read_eq(self.eq_bram)
        else:
            return self.eq_poly

    def set_eq(self, complex_gain=None, hostdevice=None):
        """
        The the EQ for this source
        :param complex_gain: this can be an int, complex or list
        :param hostdevice: the device to which to try and write
        :return:
        """
        if complex_gain is not None:
            self.eq_poly = complex_gain
            try:
                eq_poly = 'list(%d, ...)' % self.eq_poly[0]
            except TypeError:
                eq_poly = self.eq_poly
            LOGGER.info('\tSource %s updated gain to %s' % (self, eq_poly))
        if hostdevice is not None:
            length_written = hostdevice.write_eq(self.eq_poly, self.eq_bram)
            LOGGER.info('\tSource %s applied gain to hardware - wrote %i bytes' % (self, length_written))

    def __str__(self):
        try:
            eq_poly = 'list(%d, ...)' % self.eq_poly[0]
        except TypeError:
            eq_poly = self.eq_poly
        return 'DataSource(%i,%s) @ %s+%i port(%i) eq(%s,%s)' % (self.source_number, self.name, self.ip,
                                                                 self.iprange, self.port,
                                                                 eq_poly, self.eq_bram)
