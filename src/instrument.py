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

        # The instrument might well have a sensor manager
        self.sensor_manager = None

        # an instrument knows about hosts, but specifics are left to
        # child classes
        self.hosts = []

        # an instrument was synchronised at some UNIX time - -1 means unset
        self._synchronisation_epoch = -1

        # an instrument provides data streams, keyed on unique name
        self.data_streams = []

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

    def add_data_stream(self, data_stream):
        """
        Add a data stream produced by this instrument.
        :param data_stream - the DataStream to be added
        :return:
        """
        if self.check_data_stream(data_stream.name):
            raise RuntimeError('DataStream %s already in self.data_streams' %
                               data_stream.name)
        self.data_streams.append(data_stream)
        self.logger.info('DataStream %s added.' % data_stream.name)

    def check_data_stream(self, stream_name):
        """
        Does a given stream name exist on this instrument?
        :param stream_name: an instrument data stream name
        :return: True if found
        """
        try:
            self.get_data_stream(stream_name)
            return True
        except ValueError:
            return False

    def get_data_stream(self, stream_name):
        """
        Does a given stream name exist on this instrument?
        :param stream_name:
        :return:
        """
        for stream in self.data_streams:
            if stream.name == stream_name:
                return stream
        raise ValueError('stream %s is not in stream list: %s' % (
            stream_name, self.data_streams))

    def get_data_streams_by_type(self, stream_type):
        """
        Get all streams of this type
        :param stream_type:
        :return:
        """
        rv = []
        for stream in self.data_streams:
            if stream.category == stream_type:
                rv.append(stream)
        return rv

    def stream_set_destination(self, stream_name, address):
        """
        Set the destination for a data stream.
        :param stream_name:
        :param address: A dotted-decimal string representation of the
        IP address, range and port. e.g. '1.2.3.4+0:7890'
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

    def stream_issue_descriptors(self, stream_name=None):
        """
        Send the descriptors for all streams on this instrument
        :param stream_name: if none is given, do all streams
        :return:
        """
        if stream_name is None:
            streams = self.data_streams
        else:
            streams = [self.get_data_stream(stream_name)]
        for stream in self.data_streams:
            stream.descriptors_issue()

    @property
    def synchronisation_epoch(self):
        # LOGGER.info('@synchronisation_epoch getter')
        return self._synchronisation_epoch

    @synchronisation_epoch.setter
    def synchronisation_epoch(self, new_synch_time):
        """
        Set the last sync time for this system
        :param new_synch_time: UNIX time
        :return: <nothing>
        """
        # LOGGER.info('@synchronisation_epoch setter')
        time_now = time.time()
        if new_synch_time > time_now:
            _err = 'Synch time in the future makes no sense? %d > %d' % (
                new_synch_time, time_now)
            self.logger.error(_err)
            raise RuntimeError(_err)
        self._synchronisation_epoch = new_synch_time
        if self.sensor_manager:
            self.sensor_manager.sensors_sync_time()
        self.logger.info('Set synch epoch to %d.' % new_synch_time)

# end
