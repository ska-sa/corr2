# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Created on Feb 28, 2013

@author: paulp
"""
from logging import INFO
from corr2LogHandlers import getLogger as _getLogger
import time


class Instrument(object):
    """
    Instruments have links to hosts.
    These Hosts host processing Engines that do work.
    Instruments produce data streams.
    """

    def __init__(self, descriptor, config_source, identifier=-1, getLogger=_getLogger, **kwargs):
        """
        An abstract base class for instruments.
        :param descriptor: A text description of the instrument. Required.
        :param identifier: An optional integer identifier.
        :param config_source: The instrument configuration source, can be a
        text file, hostname, whatever.
        :return: <nothing>
        """
        self.classname = self.__class__.__name__
        try:
            # Just in case some numpty decides to give a descriptor that isn't a string.
            self.descriptor = descriptor.strip().replace(' ', '_').lower()
        except AttributeError:
            raise TypeError('Cannot instantiate an Instrument without a meaningful (string) descriptor.')

        self.identifier = identifier
        self.config_source = config_source
        self.configd = None

        self.getLogger = getLogger
        # TODO: decide whether 'Instrument'-level logs should default to INFO?
        log_level = kwargs.get('logLevel', INFO)
        result, self.logger = self.getLogger(logger_name=self.descriptor, log_level=log_level, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(self.descriptor)
            raise RuntimeError(errmsg)
        
        self._read_config()

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

        

        self.logger.info('%s %s created.' % (self.classname, self.descriptor))

        # an instrument has hosts
        self._create_hosts(**kwargs)

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if the instrument read a config successfully,
        raise an error if not?
        """
        raise NotImplementedError

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

    def _create_hosts(self, **kwargs):
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
        :param stream_name: string, name of the stream to query
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
        :param stream_name: string, name of the stream to query
        :param address: A dotted-decimal string representation of the
        IP address, range and port. e.g. '1.2.3.4+0:7890'
        :return: <nothing>
        """
        raise NotImplementedError

    def stream_tx_enable(self, stream_name):
        """
        Enable tranmission for a stream produced by this instrument.
        :param stream_name: string, name of the stream to query
        :return:
        """
        self.get_data_stream(stream_name).tx_enable()

    def stream_tx_disable(self, stream_name):
        """
        Disable tranmission for a stream produced by this instrument.
        :param stream_name: string, name of the stream to query
        :return:
        """
        self.get_data_stream(stream_name).tx_disable()

    def stream_tx_status(self, stream_name):
        """
        Return True if the stream is enabled and transmitting, else False.
        :param stream_name: string, name of the stream to query
        :return:
        """
        return self.get_data_stream(stream_name).tx_enabled

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

        i = 0
        #for stream in self.data_streams:
        for stream in streams:
            i += 1
            stream.descriptors_issue()

    def stream_enable_descriptor_issue(self, stream_name=None, enable=True):
        """
        Enable or disable sending of descriptors for the specfied stream
        :param stream_name: 
        :param enable: True/False
        :return:
        """
        if stream_name != None:
            stream = self.get_data_stream(stream_name)
            stream.enable_descriptor_issue = enable

    def stream_get_number_of_descriptors(self):
        """
        Return the total number of descriptors across all streams
        :return: Returns number of descriptors
        """
        streams = self.data_streams

        num_descriptors = 0
        for stream in self.data_streams:
            num_descriptors_in_current_stream = stream.get_num_descriptors()
            if(num_descriptors_in_current_stream > 0):
                num_descriptors += num_descriptors_in_current_stream

        return num_descriptors

    def stream_issue_descriptor_single(self, index):
        """
        Send a single descriptors from a single stream on this instrument
        :param index: returns the descriptor index
        :return:
        """

        streams = self.data_streams

        position = 0
        stream_num = 0
        for stream in self.data_streams:
            num_descriptors_in_current_stream = stream.get_num_descriptors()
            stream_num += 1
            if(num_descriptors_in_current_stream <= 0):
                continue
            if(num_descriptors_in_current_stream + position > index):
                #self.logger.error('Index %i Stream %i Stream Index %i' % (index, stream_num-1, index-position))
                stream.descriptor_issue_single((index - position))
                return
            else:
                position += num_descriptors_in_current_stream

    def set_sensor_manager(self, sensor_manager):
        """
        Set the sensor manager for this instrument
        :param sensor_manager: a SensorManager instance
        :return:
        """
        self.sensor_manager = sensor_manager

    @property
    def synchronisation_epoch(self):
        return self._synchronisation_epoch

    @synchronisation_epoch.setter
    def synchronisation_epoch(self, new_synch_time):
        """
        Set the last sync time for this system
        :param new_synch_time: UNIX time
        :return: <nothing>
        """
        time_now = time.time()
        if hasattr(self, 'timestamp_bits'):
            if new_synch_time < time_now - (2**self.timestamp_bits):
                errmsg = 'Synch epoch supplied is too far in the past: ' \
                         'now(%.3f) epoch(%.3f)' % (time_now, new_synch_time)
                self.logger.error(errmsg)
                raise RuntimeError(errmsg)
        if new_synch_time > time_now:
            errmsg = 'Synch time in the future makes no sense? %d > %d' % (
                new_synch_time, time_now)
            self.logger.error(errmsg)
            raise RuntimeError(errmsg)
        self._synchronisation_epoch = float(new_synch_time)
        if hasattr(self.sensor_manager, 'sensors_sync_time'):
            self.sensor_manager.sensors_sync_time()
        self.logger.info('Set synch epoch to %.5f.' % new_synch_time)

    def get_version_info(self):
        """
        Get the version information for this instrument.
        :return: a list of items: [(name, (version, build-state)), ]
        """
        return []

# end
