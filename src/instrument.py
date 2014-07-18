# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Created on Feb 28, 2013

@author: paulp
"""

import logging
import time

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
        self.configd = None

        # an instrument knows about hosts, but specifics are left to child classes
        self.hosts = []

        # an instrument was synchronised at some UNIX time
        self.synchronisation_epoch = -1

        if self.config_source is not None:
            if not self._read_config():
                raise RuntimeError('Failed to configure using %s' % self.config_source)

        LOGGER.info('%s %s created.' % (self.classname, self.descriptor))

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if the instrument read a config successfully, raise an error if not?
        """
        if self.config_source is None:
            raise RuntimeError('Running _read_config with no config source. Explosions.')
        # file?
        if self._read_config_file():
            return True
        # or is it a (host,port) tuple?
        elif self._read_config_server():
            return True
        raise RuntimeError('Supplied config_source %s is invalid' % self.config_source)

    def set_synch_time(self, new_synch_time):
        """
        Set the last sync time for this system
        :param new_synch_time: UNIX time
        :return: <nothing>
        """
        if new_synch_time > time.time():
            raise RuntimeError('Synch time in the future makes no sense?')
        self.synchronisation_epoch = new_synch_time

    def _read_config_file(self):
        """
        To be implemented by the child class.
        :return: True if we read the file successfully, False if not
        """
        raise NotImplementedError

    def _read_config_server(self):
        """
        To be implemented by the child class.
        :return: True if we read the config successfully, False if not
        """
        raise NotImplementedError

    def initialise(self):
        """
        To be implemented by the child class.
        :return:
        """
        raise NotImplementedError

# end
