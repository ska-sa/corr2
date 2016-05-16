from casperfpga.tengbe import IpAddress
import logging

LOGGER = logging.getLogger(__name__)


class NetAddress(object):
    """
    An IP and port combo.
    """
    def __init__(self, ip, port):
        """

        :param ip: the ipaddress
        :param port: the port
        :return:
        """
        self.ip = IpAddress(ip)
        self.port = int(port)

    def is_multicast(self):
        """
        Does the data product's IP address begin with 239?
        :return:
        """
        return (int(self.ip) >> 24) == 239

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return '%s:%i' % (self.ip, self.port)
