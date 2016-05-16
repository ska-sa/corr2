from casperfpga.tengbe import IpAddress
import logging

LOGGER = logging.getLogger(__name__)


class DataSource(object):
    """
    A data source from an IP. Holds all the information we need to use
    that data source.
    """
    def __init__(self, name, ip_string, ip_range, port):
        """

        :param name: the name of this data source
        :param ip_string: the ip address at which it can be found - a dotted
        decimal STRING
        :param ip_range: the consecutive number of IPs over which it is spread
        :param port: the port to which it is sent
        :return:
        """
        self.name = name
        self.ip_address = IpAddress(ip_string)
        self.ip_range = ip_range
        self.port = port

    @classmethod
    def from_mcast_string(cls, mcast_string):
        try:
            _bits = mcast_string.split(':')
            port = int(_bits[1])
            address, number = _bits[0].split('+')
            number = int(number) + 1
            assert(len(address.split('.')) == 4)
        except ValueError:
            raise RuntimeError('The address %s is not correctly formed. Expect '
                               '1.2.3.4+50:7777. Bailing.', mcast_string)
        return cls('<unnamed>', address, number, port)

    def is_multicast(self):
        """
        Does the data source's IP address begin with 239?
        :return:
        """
        return (int(self.ip_address) >> 24) == 239

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'DataSource(%s) @ %s+%i port(%i)' % (
            self.name, self.ip_address, self.ip_range-1, self.port)
