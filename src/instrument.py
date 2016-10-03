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
    Instruments produce data streams.
    """
    def __init__(self, descriptor, identifier=-1, config_source=None,
                 logger=None):
        """
        An abstract base class for instruments.
        :param descriptor: A text description of the instrument. Required.
        :param identifier: An optional integer identifier.
        :param config_source: The instrument configuration source, can be a
        text file, hostname, whatever.
        :return: <nothing>
        """
        self.classname = self.__class__.__name__
        if descriptor is None:
            raise RuntimeError('Cannot instantiate an Instrument without a '
                               'meaningful descriptor.')
        self.descriptor = descriptor
        self.identifier = identifier
        self.config_source = config_source
        self.configd = None
        self.logger = logger or LOGGER

        # an instrument knows about hosts, but specifics are left to
        # child classes
        self.hosts = []

        # an instrument was synchronised at some UNIX time - -1 means unset
        self._synchronisation_epoch = -1

        # an instrument provides data streams, keyed on unique name
        self.data_streams = {}

        self._initialised = False

        if self.config_source is not None:
            try:
                self._read_config()
            except:
                raise
        self.logger.info('%s %s created.' % (self.classname, self.descriptor))

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if the instrument read a config successfully,
        raise an error if not?
        """
        if self.config_source is None:
            raise RuntimeError('Running _read_config with no config source. '
                               'Explosions.')
        try:
            # file?
            self._read_config_file()
            return
        except (IOError, ValueError) as excep:
            self.logger.error(excep.message)
            # try:
            #     # server?
            #     self._read_config_server()
            #     return
            # except:
            #     raise
        raise RuntimeError('Supplied config_source %s is '
                           'invalid' % self.config_source)

    def set_synch_time(self, new_synch_time):
        """
        Set the last sync time for this system
        :param new_synch_time: UNIX time
        :return: <nothing>
        """
        time_now = time.time()
        if new_synch_time > time_now:
            _err = 'Synch time in the future makes no sense? %d > %d' % (
                new_synch_time, time_now)
            self.logger.error(_err)
            raise RuntimeError(_err)
        self._synchronisation_epoch = new_synch_time
        self.logger.info('Set synch epoch to %d' % new_synch_time)

    def get_synch_time(self):
        """
        Get the last sync time for this system
        :return: the current UNIX-time synch epoch
        """
        return self._synchronisation_epoch

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

    def initialised(self):
        """
        Has initialise successfully passed?
        :return:
        """
        return self._initialised

    def register_data_stream(self, data_stream):
        """
        Register a data stream produced by this instrument
        :param data_stream - the DataStream to be registered
        :return:
        """
        if data_stream.name in self.data_streams:
            raise RuntimeError('DataStream %s already in self.data_streams' %
                               data_stream.name)
        self.data_streams[data_stream.name] = data_stream
        self.logger.info('DataStream %s registered.' % data_stream.name)

    def check_data_stream(self, stream_name):
        """
        Does a given stream name exist on this instrument?
        :param stream_name: an instrument data stream name
        :return: True if found
        """
        return stream_name in self.data_streams

    def get_data_stream(self, stream_name):
        """
        Does a given stream name exist on this instrument?
        :param stream_name:
        :return:
        """
        if stream_name not in self.data_streams:
            raise ValueError('stream %s is not in stream list: %s' % (
                stream_name, self.data_streams))
        return self.data_streams[stream_name]

    def stream_set_destination(self, stream_name, txip_str=None, txport=None):
        """
        Set the destination for a data stream produced by this instrument.
        :param stream_name:
        :param txip_str: A dotted-decimal string representation of the
        IP address. e.g. '1.2.3.4'
        :param txport: An integer port number.
        :return: <nothing>
        """
        raise NotImplementedError

    def stream_tx_enable(self, stream_name):
        """
        Enable tranmission for a stream produced by this instrument.
        :param stream_name:
        :return:
        """
        self.get_data_stream(stream_name).tx_enable()

    def stream_tx_disable(self, stream_name):
        """
        Disable tranmission for a stream produced by this instrument.
        :param stream_name:
        :return:
        """
        self.get_data_stream(stream_name).tx_disable()

    def stream_issue_metadata(self, stream_name=None):
        """
        Issue metadata for a stream produced by this instrument.
        :param stream_name:
        :return:
        """
        if stream_name is None:
            streams = self.data_streams.keys()
        else:
            streams = [stream_name]
        for stream in streams:
            self.get_data_stream(stream).meta_issue()

# end
