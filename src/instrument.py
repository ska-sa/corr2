# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Created on Feb 28, 2013

@author: paulp
"""

import logging
LOGGER = logging.getLogger(__name__)


class Instrument(object):
    """
    Instruments have links to hosts.
    These Hosts host processing Engines that do work.
    Instruments produce data products.
    """
    def __init__(self, descriptor, identifier=-1, config_source=None):
        """
        An abstract base class for instruments.
        :param descriptor: A text description of the instrument. Required.
        :param identifier: An optional integer identifier.
        :param config_source: The instrument configuration source, can be a text file, hostname, whatever.
        :return: <nothing>
        """
        self.classname = self.__class__.__name__
        if descriptor is None:
            raise RuntimeError('Cannot instantiate an Instrument without a meaningful descriptor.')
        self.descriptor = descriptor
        self.identifier = identifier
        self.config_source = config_source
        self.config = None

        # an instrument knows about hosts and engines, but specifics are left to child classes
        self.hosts = []
        self.engines = []

        # an instrument was synchronised at some UNIX time
        self.synchronisation_epoch = -1

        if self.config_source is not None:
            self._read_config()
        LOGGER.info('%s %s initialised' % (self.classname, self.descriptor))

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return: <nothing>
        """
        if self.config_source is None:
            raise RuntimeError('Running _read_config with no config source. Explosions.')
        # is it a file?
        try:
            open(self.config_source, 'r').close()
            file_io = True
        except IOError:
            file_io = False
            pass
        if file_io:
            self._read_config_file()
            return
        # or is it a (host,port) tuple?
        if isinstance(self.config_source, tuple):
            if isinstance(self.config_source[0], basestring) and isinstance(self.config_source[1], int):
                self._read_config_server()
        else:
            raise RuntimeError('config_source %s is invalid' % self.config_source)
        return



    def _read_config_server(self):
        """
        To be implemented by the child class.
        :return:
        """
        raise NotImplementedError

    def initialise(self):
        """
        To be implemented by the child class.
        :return:
        """
        raise NotImplementedError

# end
