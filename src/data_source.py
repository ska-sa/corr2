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
