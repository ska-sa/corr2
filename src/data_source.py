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
    A DataSource that is specifically used to send data to an f-engine
    """
    def __init__(self, host, source_number, eq, name, ip, iprange, port):
        """
        Create a FengineSource object
        :param host: the host on which this data is received
        :param source_number: the correlator-wide source number/index
        :param name: the correlator-wide source name
        :param ip: the ip address from which this source is received
        :param iprange: the ip range across which it is received
        :param port: the port on which it is received
        :param eq: the eq setting and bram associated with this source
        :return:
        """
        self.host = host
        self.source_number = source_number
        self.eq = eq
        self.name = name
        self.ip = ip
        self.iprange = iprange
        self.port = port
        self._update_name_cb = None

    def update_name(self, newname):
        """
        The name is quite important - so provide a method for a callback to be registered for this
        DataSource, so that when the names changes, you can do other stuff too.
        :param newname: the new name for this DataSource
        :return:
        """
        if newname == self.name:
            return
        if self._update_name_cb is not None:
            self._update_name_cb(self.name, newname)
        self.name = newname

    @classmethod
    def from_datasource(cls, host, source_number, eq, dsource_object):
        """
        Make a FengineSource object from an existing DataSource object
        :param host:
        :param source_number:
        :param eq:
        :param dsource_object:
        :return:
        """
        return cls(host, source_number, eq,
                   dsource_object.name, dsource_object.ip, dsource_object.iprange, dsource_object.port)

    def __str__(self):
        return 'FengineSource(%s:%i:%s) @ %s+%i port(%i)' % (self.host.name, self.source_number,
                                                             self.name, self.ip, self.iprange, self.port)