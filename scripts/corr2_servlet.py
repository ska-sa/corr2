#!/usr/bin/env python

from __future__ import print_function
import os, sys, logging, time
import signal, pkginfo, Queue
import traceback2 as traceback

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from katcp import DeviceServer
from katcp.kattypes import request, return_reply, Float, Int, Str, Bool
from tornado import gen
from tornado.ioloop import IOLoop
from concurrent import futures

from corr2.fxcorrelator import FxCorrelator
from corr2.sensors import Corr2Sensor, Corr2SensorManager
from corr2.utils import parse_ini_file, process_new_eq
from corr2 import corr_monitoring_loop as corr_mon_loop

from corr2.corr2LogHandlers import getKatcpLogger, \
                                servlet_log_level_request, \
                                create_katcp_and_file_handlers, \
                                check_logging_level, \
                                get_all_loggers, \
                                reassign_log_handlers

_DEFAULT_LOG_DIR = '/var/log/corr'

class Corr2Server(DeviceServer):

    # Interface version information.
    VERSION_INFO = ('corr2 instrument servlet', 0, 1)

    # Device server build / instance information.
    BUILD_INFO = ('corr2', 0, 1, 'alpha')

    def __init__(self, *args, **kwargs):
        try:
            start_time_str = str(time.time())
            
            use_tornado = kwargs.pop('tornado')

            self.config_filename = kwargs.pop('config', None)
            
            config_file_dict = parse_ini_file(self.config_filename)
            self.log_file_dir = config_file_dict.get('FxCorrelator').get('log_file_dir', _DEFAULT_LOG_DIR)
            assert os.path.isdir(self.log_file_dir)
            
            if 'ini' in os.path.basename(self.config_filename):
                self.config_filename = os.path.basename(self.config_filename).rsplit('.', 1)[0]
            # else: Continue!
            self.log_filename = '{}_{}_servlet.log'.format(
                                    os.path.basename(self.config_filename), start_time_str)
            self.log_level = kwargs.pop('log_level', logging.WARN)

            super(Corr2Server, self).__init__(*args, **kwargs)
            if use_tornado:
                self.set_concurrency_options(thread_safe=False, handler_thread=False)
            
            create_katcp_and_file_handlers(self._logger, self.mass_inform,
                                            self.log_filename, self.log_file_dir,
                                            self.log_level)

            self.instrument = None
            self.metadata_cadence = 5
            self.descriptor_cadence = 5
            self.executor = futures.ThreadPoolExecutor(max_workers=1)
            self._created = False
            self._initialised = False
            self.delays_disabled = False

            self.mon_loop = None
            self.mon_loop_running = None

        except AssertionError as ex:
            stack_trace = traceback.format_exc()
            errmsg = 'Logging directory does not exist: {}'.format(self.log_file_dir)
            self._log_stacktrace(stack_trace, errmsg)
        except Exception as ex:
            # Oh dear
            stack_trace = traceback.format_exc()
            self._log_stacktrace(stack_trace, 'Failed to create servlet')

    def _log_excep(self, excep, msg=''):
        """
        Log an error and return fail
        :param excep: the exception that caused us to fail
        :param msg: the error message to log
        :return:
        """
        message = msg
        if excep is not None:
            template = '\nAn exception of type {0} occured. Arguments: {1!r}'
            message += template.format(type(excep).__name__, excep.args)
        self._logger.error(message)
        return 'fail', message

    def _log_stacktrace(self, stack_trace, msg=''):
        """
        Log a stack_trace and return fail
        - Unfortunately the stack-trace needs to be formatted when the
          exception is caught, hence the creation of a new method
          rather than a change to _log_excep
        :param stack_trace: String formatted using traceback2 utility
        :param msg: the error message to log
        :return:
        """
        log_message = '{} \n {}'.format(msg, stack_trace)
        self._logger.error(log_message)
        return 'fail', log_message

    @request()
    @return_reply()
    def request_ping(self, sock):
        """
        Just ping the server
        :param sock:
        :return: 'ok'
        """
        return 'ok',

    @staticmethod
    def rv_to_liststr(rv):
        rv = str(rv)
        rv = rv.replace('(', '').replace(')', '')
        rv = rv.replace('[', '').replace(']', '')
        rv = rv.replace(',', '')
        return rv.split(' ')

    @request(Str(), Str(default=''), Int(default=1000))
    @return_reply()
    def request_create(self, sock, config_file, instrument_name, log_len):
        """
        Create the instrument using the detail in config_file
        :param sock:
        :param config_file: The instrument config file to use
        :param instrument_name: a sub-array-unique instrument name
        :param log_len: how many lines should the log keep
        :return:
        """
        if self._created:
            return 'fail', 'Cannot run ?create twice.'
        try:
            # For completeness
            time_str = str(time.time())
            iname = instrument_name or 'corr_{}'.format(time_str)

            # Parse ini file to check for log_file_dir
            config_file_dict = parse_ini_file(config_file)
            
            # While we have the config-file parsed:
            # - To be used when initialising log-levels of instrument groups
            self.log_level_dict = config_file_dict.get('log-level', None)

            self.instrument = FxCorrelator(iname, config_source=config_file,
                              getLogger=getKatcpLogger, mass_inform_func=self.mass_inform,
                              log_filename=self.log_filename, log_file_dir=self.log_file_dir)
            self._created = True

            # Function created to reassign all non-conforming log-handlers
            loggers_changed = reassign_log_handlers(mass_inform_func=self.mass_inform,
                                                    log_filename=self.log_filename,
                                                    log_file_dir=self.log_file_dir,
                                                    instrument_name=self.instrument.descriptor)

            return 'ok',
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed to create instrument.')
     
    
    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        pass

    @request(Bool(default=True), Bool(default=True), Bool(default=True),
             Bool(default=True))
    @return_reply()
    def request_initialise(self, sock, program, configure, require_epoch,
                           monitor_instrument):
        """
        Initialise self.instrument
        :param sock:
        :param program: program the FPGA boards if True
        :param configure: setup the FPGA registers if True
        :param require_epoch: the synch epoch MUST be set before init if True
        :param monitor_instrument: start the instrument monitoring ioloop
        :return:
        """
        if self._initialised:
            return 'fail', 'Cannot run ?initialise twice.'
        try:
            self.instrument.initialise(
                program=program, configure=configure, require_epoch=require_epoch,
                mass_inform_func=self.mass_inform, getLogger=getKatcpLogger,
                log_filename=self.log_filename, log_file_dir=self.log_file_dir)

            # update the servlet's version list with version information
            # from the running firmware
            self.extra_versions.update(self.instrument.get_version_info())
            # add a sensor manager
            sensor_manager = Corr2SensorManager(self, self.instrument,
                                        mass_inform_func=self.mass_inform,
                                        log_filename=self.log_filename,
                                        log_file_dir=self.log_file_dir)

            self.instrument.set_sensor_manager(sensor_manager)
            # set up the main loop sensors
            sensor_manager.setup_mainloop_sensors()
 
            # Add build time sensors
            self.sensors = {}

            IOLoop.current().add_callback(self.periodic_issue_descriptors)
            # IOLoop.current().add_callback(self.periodic_issue_metadata)
            #if monitor_instrument:
                # create the monitoring loop object
                #self.mon_loop = corr_mon_loop.MonitoringLoop(check_time=-1,
                #                                             fx_correlator_object=self.instrument)
                ## start the monitoring loop
                #self.mon_loop.start()
                #self.mon_loop_running = True
            self._initialised = True

            # Once more, for completeness
            loggers_changed = reassign_log_handlers(mass_inform_func=self.mass_inform,
                                                    log_filename=self.log_filename,
                                                    log_file_dir=self.log_file_dir,
                                                    instrument_name=self.instrument.descriptor)

            # Reset the gbe counters otherwise they don't start
            self.instrument.fops.gbe_counter_rst()
            self.instrument.xops.gbe_counter_rst()

            # Last thing to do, check if any default log-levels are specified in the config_file
            # - Change the corresponding group's log-level accordingly
            if self.log_level_dict is None:
                # All is well
                return 'ok',
            # else: More work to do!
            for logger_group_name, log_level in self.log_level_dict.items():
                result, return_msg = servlet_log_level_request(corr_obj=self.instrument,
                                                               log_level=log_level,
                                                               logger_group_name=logger_group_name)
                if not result:
                    # Problem
                    return 'fail', return_msg
                # else: Great success

            return 'ok',
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed to initialise {}'.format(
                self.instrument.descriptor))
            
    @request(Str(multiple=True))
    @return_reply()
    def request_testfail(self, sock, *multiargs):
        """
        Just a command that fails. For testing.
        :param sock:
        :return: 'fail' and a test fail message
        """
        print(multiargs)
        return self._log_excep(None, 'A test failure, like it should')

    @request(Float(default=-1.0))
    @return_reply(Float())
    def request_sync_epoch(self, sock, synch_time):
        """
        Set/Get the digitiser synch time, UNIX time.
        :param sock:
        :param synch_time: unix time float
        :return: the currently set synch time
        """
        if synch_time > -1.0:
            try:
                self.instrument.synchronisation_epoch = synch_time
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(
                    stack_trace, 'Failed to set digitiser synch epoch.')
        return 'ok', self.instrument.synchronisation_epoch

    @request(Str(), Str())
    @return_reply()
    def request_meta_destination(self, sock, stream_name, ipportstr):
        """
        Set/Get the capture AND meta destination for this instrument
        :param sock:
        :param stream_name: an instrument data stream name
        :param ipportstr: ip and port, in the form 1.2.3.4:7890
        :return:
        """
        return self._log_excep(
            None,
            'This has been deprecated. Use capture-destination to set both '
            'capture and meta destinations at the same time')

    @request(Str(), Str(default=''))
    @return_reply(Str(multiple=True))
    def request_capture_destination(self, sock, stream_name, ipportstr):
        """
        Set/Get the capture AND meta destination for this instrument
        :param sock:
        :param stream_name: an instrument data stream name
        :param ipportstr: ip and port, in the form 1.2.3.4:7890
        :return:
        """
        if ipportstr != '':
            try:
                self.instrument.stream_set_destination(stream_name, ipportstr)
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(stack_trace, 
                    'Failed to set capture AND meta destination for {}.'.format(stream_name))
        else:
            dstrm = self.instrument.data_streams[stream_name]
            ipportstr = '{}:{}'.format(dstrm.destination.ip, dstrm.destination.port)
        return 'ok', stream_name, ipportstr

    @request(Str(default=''))
    @return_reply()
    def request_capture_list(self, sock, stream_name):
        """
        List available streams and their destination IP:port
        :param sock:
        :param stream_name: an instrument data stream name
        :return:
        """
        stream_names = []
        if stream_name != '':
            stream_names.append(stream_name)
        else:
            stream_names.extend([stream.name
                                 for stream in self.instrument.data_streams])
        for strm in stream_names:
            if not self.instrument.check_data_stream(strm):
                failmsg = 'Failed: stream {0} not in instrument data streams: {1}'.format(strm,
                    self.instrument.data_streams)
                return self._log_excep(None, failmsg)
            dstrm = self.instrument.get_data_stream(strm)
            _enabled = 'up' if dstrm.tx_enabled else 'down'
            sock.inform(strm, str(dstrm.destination), _enabled)
        return 'ok',

    @request(Str(default=''))
    @return_reply(Str())
    def request_capture_start(self, sock, stream_name):
        """
        Start transmission of a data stream.
        :param sock:
        :param stream_name: an instrument data stream name
        :return:
        """
        if not self.instrument.check_data_stream(stream_name):
            failmsg = 'Failed: stream {0} not in instrument data streams: {1}'.format(stream_name,
                self.instrument.data_streams)
            return self._log_excep(None, failmsg)
        try:
            # Issue metadata deprecated (MM 18-12-17)
            # self.instrument.stream_issue_metadata(stream_name)
            self.instrument.stream_tx_enable(stream_name)
            return 'ok', stream_name
        except RuntimeError as excep:
            stack_trace = traceback.format_exc()
            failmsg = 'Failed: stream {0} could not be started.'.format(stream_name)
            return self._log_stacktrace(stack_trace, failmsg)

    @request(Str(default=''))
    @return_reply(Str())
    def request_capture_stop(self, sock, stream_name):
        """
        Stop transmission of a data stream.
        :param sock:
        :param stream_name: an instrument data stream name
        :return:
        """
        if not self.instrument.check_data_stream(stream_name):
            failmsg = 'Failed: stream {0} not in instrument data streams: ' \
                      '{1}'.format(stream_name, self.instrument.data_streams)
            return self._log_excep(None, failmsg)
        try:
            self.instrument.stream_tx_disable(stream_name)
            return 'ok', stream_name
        except RuntimeError as excep:
            stack_trace = traceback.format_exc()
            failmsg = 'Failed: stream {0} could not be stopped.'.format(stream_name)
            return self._log_stacktrace(stack_trace, failmsg)

    @request(Str(default=''))
    @return_reply(Str(), Int())
    def request_capture_status(self, sock, stream_name):
        """
        Report the capture status of a stream.
        :param sock:
        :param stream_name: an instrument data stream name
        :return: 1 if stream TX is enabled, else 0
        """
        if not self.instrument.check_data_stream(stream_name):
            failmsg = 'Failed: stream {0} not in instrument data streams: ' \
                      '{1}'.format(stream_name, self.instrument.data_streams)
            return self._log_excep(None, failmsg)
        try:
            tx_enabled = self.instrument.stream_tx_status(stream_name)
            return 'ok', stream_name, 1 if tx_enabled else 0
        except RuntimeError as excep:
            stack_trace = traceback.format_exc()
            failmsg = 'Failed: stream {0} could not get TX status.'.format(stream_name)
            return self._log_stacktrace(stack_trace, failmsg)

    @request(Str(default=''))
    @return_reply(Str())
    def request_capture_meta(self, sock, stream_name):
        """
        Issue metadata for a data stream
        :param sock:
        :param stream_name: an instrument data stream name
        :return:
        """
        if not self.instrument.check_data_stream(stream_name):
            failmsg = 'Failed: stream {0} not in instrument data streams: ' \
                      '{1}'.format(stream_name, self.instrument.data_streams)
            return self._log_excep(None, failmsg)
        self.instrument.stream_issue_descriptors(stream_name)
        return 'ok', stream_name

    @request(Str(default=''), Str())
    @return_reply(Str())
    def request_descriptor_issue_toggle(self, sock, stream_name, enable):
        """
        Toggle sending of metadata for a data stream
        :param sock:
        :param stream_name: an instrument data stream name
        :param enable: 0 = disable metadata, 1 = enable metadata
        :return:
        """
        if not self.instrument.check_data_stream(stream_name):
            failmsg = 'Failed: stream {0} not in instrument data streams: ' \
                      '{1}'.format(stream_name, self.instrument.data_streams)
            return self._log_excep(None, failmsg)
        if enable == '0':
            self.instrument.stream_enable_descriptor_issue(stream_name, False)
            return 'ok', stream_name
        elif enable == '1':
            self.instrument.stream_enable_descriptor_issue(stream_name, True)
            return 'ok', stream_name
        else:
            failmsg = 'Failed: invalid parameter: {}, 1=on, 0=off' \
                      ''.format(enable)
            return self._log_excep(None, failmsg)

    @request(Str(default=''), Float())
    @return_reply(Float())
    def request_frequency_select(self, sock, stream_name, centrefreq):
        """
        Select the passband for this instrument
        :param sock:
        :param stream_name: an instrument data stream name
        :param centrefreq: the centre frequency to choose, in Hz
        :return:
        """
        if not self.instrument.check_data_stream(stream_name):
            return 'fail', -1.0
        self.instrument.fops.set_center_freq(centrefreq)
        return 'ok', self.instrument.fops.get_center_freq()

    @request(Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_input_labels(self, sock, *newlist):
        """
        Set and get the input labels on the instrument
        :param sock:
        :return:
        """
        if len(newlist) == 1:
            if newlist[0] == '':
                newlist = []
        if len(newlist) > 0:
            try:
                self.instrument.set_input_labels(newlist)
                return tuple(['ok'] + self.instrument.get_input_labels())
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(stack_trace, 'Failed to set input labels.')
        else:
            return tuple(['ok'] + self.instrument.get_input_labels())

    @request(Str(), Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_gain(self, sock, source_name, *eq_vals):
        """
        Apply and/or get the gain settings for an input
        :param sock:
        :param source_name: the source on which to act
        :param eq_vals: the equaliser values
        :return:
        """
        if source_name.strip() == '':
            return self._log_excep(None, 'No source name given.')
        if len(eq_vals) > 0 and eq_vals[0] != '':
            try:
                neweqvals = process_new_eq(list(eq_vals))
                self.instrument.fops.set_eq(new_eq=neweqvals, input_name=source_name)
                return ('ok', 'gain set for input {}.'.format(source_name))
            except Exception as ex:
                stack_trace = traceback.format_exc()
                failmsg = 'Failed setting eq for source {0}.'.format(source_name)
                return self._log_stacktrace(stack_trace, failmsg)
        else:
            _src = self.instrument.fops.get_eq(source_name)
            return tuple(['ok'] +
                     Corr2Server.rv_to_liststr(_src[source_name]))

    @request(Str(default='', multiple=True))
    @return_reply()
    def request_gain_all(self, sock, *eq_vals):
        """
        Apply the gain settings for an input
        :param sock:
        :param eq_vals: the equaliser values, or 'auto'.
        :return:
        """
        try:
            if len(eq_vals) <= 0:
                neweqvals=None
                self.instrument.logger.info('Applying default gains')
            elif eq_vals[0] == '':
                neweqvals=None
                self.instrument.logger.info('Applying default gains')
            elif eq_vals[0] == 'default':
                neweqvals=None
                self.instrument.logger.info('Applying default gains')
            elif eq_vals[0] == 'auto':
                neweqvals='auto'
                self.instrument.logger.info('Trying to set gains automatically')
            else:
                neweqvals = process_new_eq(list(eq_vals))
            self.instrument.fops.set_eq(new_eq=neweqvals, input_name=None)
        except Exception as ex:
            return self._log_excep(ex, 'Failed setting eq for all sources')
        return 'ok',

      
    @request(Str(), Float(default=-1.0), Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_delays(self, sock, stream_name, loadtime, *delay_strings):
        """
        Set delays for the instrument.
        :param sock:
        :param stream_name: the name of the feng stream to adjust.
        :param loadtime: the load time, in seconds
        :param delay_strings: the coefficient set, as a list of strings,
            described in ICD.
        :return:
        """
        if self.delays_disabled:
            return ('fail', 'delays disabled')
        if stream_name != self.instrument.fops.data_stream.name:
            return tuple(['fail', ' supplied stream name %s does not match expected %s.' % (stream_name, self.instrument.fops.data_stream.name)])
        try:

            self.instrument.fops.delay_set_all(loadtime, delay_strings)
            return tuple(['ok', ' Model updated. Check sensors after next update to confirm application'])
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed setting delays.')


    @request(Float(default=-1.0))
    @return_reply(Float())
    def request_accumulation_length(self, sock, new_acc_time):
        """
        Set & get the accumulation time
        :param sock:
        :param new_acc_time: if this is -1.0, the current acc len will be
        returned, but nothing set
        :return:
        """
        if new_acc_time != -1.0:
            try:
                self.instrument.xops.set_acc_time(new_acc_time)
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(stack_trace, 'Failed to set accumulation length.')
        return 'ok', self.instrument.xops.get_acc_time()

    @request(Int())
    @return_reply()
    def request_xeng_interpacket_gap(self, sock, new_interpacket_gap):
        """
        Set the Xengine interpacket gap to the specified value.
        :param sock:
        :param new_interpacket_gap: 
        :return:
        """
        try:
            for f in self.instrument.xhosts:
                f.registers.gapsize.write(gap_size=new_interpacket_gap)
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed to set interpacket gap size.')
        return 'ok', 

    @request(Str())
    # @return_reply(Str(multiple=True))
    @return_reply()
    def request_quantiser_snapshot(self, sock, source_name):
        """
        Get a list of values representing the quantised spectrum for
        the given source
        :param sock:
        :param source_name: the source to query
        :return:
        """
        if source_name.strip() == '':
            return self._log_excep(None, 'No source name given.')
        try:
            snapdata = self.instrument.fops.get_quant_snap(source_name)
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, ex.message)
        sock.inform(source_name, str(snapdata))
        return 'ok',

    @request(Str(), Int())
    @return_reply()
    def request_quantiser_singlechan_snapshot(self, sock, source_name, channel_select):
        """
        Get a list of values representing the time series for a
        single, specified channel of the given source
        :param sock:
        :param channel_select: the channel for which data is to be retrieved
        :param source_name: the source to query
        :return:
        """
        if source_name.strip() == '':
            return self._log_excep(None, 'No source name given.')
        try:
            snapdata = self.instrument.fops.get_quant_snap(source_name, channel_select)
        except Exception as ex:
            return self._log_excep(ex, ex.message)
        sock.inform(source_name, channel_select, str(snapdata))
        return 'ok',

    @request(Str(), Float(default=-1))
    @return_reply(Int())
    def request_adc_snapshot(self, sock, source_name, capture_time):
        """
        Request a snapshot of ADC data for a specific source, at a
        specific time.
        :param sock:
        :param source_name: the source to query
        :param capture_time: the UNIX time from which to capture data
        :return:
        """
        if source_name.strip() == '':
            return self._log_excep(None, 'No source name given.')
        try:
            data = self.instrument.fops.get_adc_snapshot(
                source_name, capture_time)
            snaptime = data[source_name].timestamp
            rstr = str(data[source_name].data)
            sock.inform(source_name, rstr)
            return 'ok', snaptime
        except ValueError as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, ex.message)

    @request(Bool())
    @return_reply()
    def request_delay_updates_disable(self, sock, disable_delays):
        """
        Disable the delays. If set, this will ignore any incoming delay model updates.
        :param : disable_delays
        :return:
        """
        try:
            self.delays_disabled = disable_delays
            if disable_delays:
                message = "Delay model updates disabled."
            else:
                message = "Delay model updates re-enabled."
            
            self._logger.info(message)
            return 'ok',
        except ValueError as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed to configure delay disable.')

    @request()
    @return_reply(Int())
    def request_transient_buffer_trigger(self, sock):
        """
        Get ADC snapshots for all data sources, hopefully triggered at the
        same time.
        :param sock:
        :return:
        """
        try:
            data = self.instrument.fops.get_adc_snapshot()
            for source in data:
                rstr = str(data[source].data)
                sock.inform(source, rstr)
            snaptime = data[data.keys()[0]].timestamp
            return 'ok', snaptime
        except ValueError as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed to read ADC voltage data from '
                                                     'transient buffers.')

    @request(Str(), Float(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_beam_weights(self, sock, beam_name, *weight_list):
        """
        Set the weights for all inputs of a given beam
        :param sock:
        :param beam_name: required beam stream
        :param weight_list: list of weights to set, one per input
        :return: a list of the weights set
        """
        if not self.instrument.found_beamformer:
            return self._log_excep(None, 'Cannot run beamformer commands with '
                                         'no beamformer')
        if weight_list != '':
            try:
                self.instrument.bops.set_beam_weights(
                    weight_list, beam_name)
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(stack_trace,
                    'Failed setting beamweights for {0}.'.format(beam_name))
        try:
            cur_weights = self.instrument.bops.get_beam_weights(
                beam_name)
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace,
                'Failed reading beamweights for {0}.'.format(beam_name))
        return tuple(['ok'] + Corr2Server.rv_to_liststr(cur_weights))

    @request(Str(), Float(default=''))
    @return_reply(Str(multiple=True))
    def request_beam_quant_gains(self, sock, beam_name, new_gain):
        """
        Set the quantiser gain for a beam.
        :param sock:
        :param beam_name: required beam stream
        :param new_gain: the new gain to apply - a real float
        :return:
        """
        if not self.instrument.found_beamformer:
            return self._log_excep(None, 'Cannot run beamformer commands with '
                                         'no beamformer')
        if new_gain != '':
            try:
                self.instrument.bops.set_beam_quant_gain(new_gain, beam_name)
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(stack_trace,
                        'Failed setting beam gain for beam {0}.'.format(beam_name))
        try:
            cur_gains = self.instrument.bops.get_beam_quant_gain(beam_name)
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace,
                        'Failed reading beam gain for beam {0}.'.format(beam_name))
        return tuple(['ok'] + Corr2Server.rv_to_liststr(cur_gains))

    @request(Str(), Str(default='', multiple=True))
    @return_reply(Str(multiple=True)) 
    def request_beam_delays(self, sock, beam_name, *delay_strings):
        """
        Set beam delays for the instrument.
        :param sock:
        :param beam_name: the name of the beam to delay.
        :param delay_strings: the coefficient set, as a list of strings,
            described in ICD. (delay(seconds), phase(radians))
        :return:
        """
        if delay_strings != '':
            try:
                self.instrument.bops.set_beam_delays(beam_name, delay_strings)
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(stack_trace, 
                        'Failed setting delays for {0}.'.format(beam_name))

        try:
            cur_delays = self.instrument.bops.get_beam_delays(beam_name)
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace,
                'Failed reading delays for {0}.'.format(beam_name))
        return ('ok', cur_delays)

    @request()
    @return_reply()
    def request_vacc_sync(self, sock):
        """
        Initiate a new vacc sync operation on the instrument.
        :param sock:
        :return:
        """
        try:
            self.instrument.xops.vacc_sync()
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed syncing vaccs')
        return 'ok',

    @request()
    @return_reply()
    def request_feng_auto_resync_reset(self, sock):
        """
        Re-initialise auto reset/re-sync mechanism for the f-engine.
        :param sock:
        :return:
        """
        try:
            self.instrument.fops.auto_rst_disable()
            time.sleep(4)
            self.instrument.fops.auto_rst_enable()
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed syncing vaccs')
        return 'ok',

    @request(Str())
    @return_reply()
    def request_fft_shift(self, sock, new_shift):
        """
        Set a new FFT shift schedule.
        :param sock:
        :param new_shift: an integer representation of the new FFT shift
        :return:
        """
        try:
            new_shift=int(new_shift)
        except ValueError:
            pass
        try:
            self.instrument.fops.set_fft_shift_all(new_shift)
            return 'ok',
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'Failed setting fft shift')

    @request(Int(default=-1))
    @return_reply()
    def request_enable_monitoring_loop(self, sock, check_time):
        """
        enable the monitoring loop if it wasn't enabled at initialisation
        :return:
        """

        if self.mon_loop is None:
            # create the monitoring loop object
            self.mon_loop = corr_mon_loop.MonitoringLoop(check_time=check_time,
                                                         fx_correlator_object=self.instrument)
            # start the monitoring loop
            self.mon_loop.start()
            self.mon_loop_running = True
            # enable auto reset / resync for the f-engines (in hardware)
            #self.instrument.fops.auto_rst_enable()
            return 'ok',
        elif not self.mon_loop_running:
            return 'fail', 'monitoring loop already enabled and waiting to be started'
        else:
            return 'fail', 'monitoring loop already enabled and running'

    @request()
    @return_reply()
    def request_start_monitoring_loop(self, sock):
        """
        start the monitoring loop
        :return:
        """

        if self.mon_loop is None:
            return 'fail', 'monitoring loop not enabled'
        else:
            if not self.mon_loop_running:
                self.mon_loop.start()
                self.mon_loop_running = True
                return 'ok',
            else:
                return 'fail', 'monitoring loop already running'

    @request()
    @return_reply()
    def request_stop_monitoring_loop(self, sock):
        """
        stop the monitoring loop
        :return:
        """

        if self.mon_loop_running:
            self.mon_loop.stop()
            self.mon_loop_running = False
            return 'ok',
        else:
            return 'fail', 'monitoring loop is not currently running'

    @request(Float(default=-1))
    @return_reply(Float())
    def request_set_monitoring_loop_time(self, sock, check_time):
        """
        set the cadence for the monitoring loop. note that this stops and
        restarts the loop (in seconds)
        :param check_time: the interval at which the loop runs, seconds
        :return:
        """
        if self.mon_loop is None:
            return 'fail', 'monitoring loop is not enabled'

        if check_time <= 0:
            return 'fail', 'invalid check time for monitoring loop'
        else:
            if self.mon_loop_running:
                self.mon_loop.stop()
                self.mon_loop_running = False
                self.mon_loop.check_time = check_time
                self.mon_loop.start()
                self.mon_loop_running = True
            else:
                self.mon_loop.check_time = check_time

            return 'ok', check_time

    @request()
    @return_reply(Int(min=0))
    def request_get_log(self, sock):
        """
        Fetch and print the instrument log.
        :param sock:
        :return:
        """
        return self._log_excep(None, 'Currently not working.')
        # if self.instrument is None:
        #     return self._log_excep(None, '... you have not connected yet!')
        # print('\nlog:'
        # self.instrument.loghandler.print_messages()
        # logstrings = self.instrument.loghandler.get_log_strings()
        # for logstring in logstrings:
        #     sock.inform('log', logstring)
        # return 'ok', len(logstrings)

    @request(Str(default=''), Str(default='debug'))
    @return_reply(Str())
    def request_set_loglevel_logger(self, sock, logger_name, log_level_str):
        """
        Set the log level of one of the internal loggers.
        :param sock: not sure...
        :param logger_name: the name of the logger to configure
        :param log_level_str: the log-level to set - log-level E {INFO, WARN, ERROR, FATAL}
        """
        if logger_name != '':
            logger = logging.getLogger(logger_name)
        else:
            logger = logging.getLogger()
        result, log_level_numeric = check_logging_level(log_level_str.upper())
        if not result:
            # Problem
            errmsg = 'Unable to set logger: {} to log-level: {}'.format(logger_name, log_level_str)
            return 'fail', errmsg
        # else: Continue
        logger.setLevel(log_level_numeric)
        return ('ok', 'Success: logger {} now logging at log-level {}'.format(logger_name, log_level_str))


    @request()
    @return_reply(Str())
    def request_get_all_loggers(self, sock):
        """
        Get all loggers associated with self.instrument
        :return: Printed list of logger names
        """
        all_loggers = get_all_loggers()

        logger_names = [logger.name for logger in all_loggers.values() if not isinstance(logger, logging.PlaceHolder)]

        return 'ok', logger_names


    @request(Str(default='debug'), Str(default='instrument'))
    @return_reply()
    def request_log_level(self, sock, log_level, logger_group_name):
        """
        Set the log-level of entities matching logger_group_name.
        If logger_group_name is present, get all loggers matching that name
        and update accordingly
        :param log_level: Log-level at which to set loggers to
                          -> This will be a string E {debug|info|warn|error}
        :param logger_group_name: Optional parameter, string
                                  -> Defaulted to 'instrument' group
        :return: Boolean - Success/Fail - True/False
        """

        # Moved all the heavy lifting to corr2LogHandlers
        # - Where it should have been in the first place!
        result, return_msg = servlet_log_level_request(corr_obj=self.instrument,
                                                       log_level=log_level,
                                                       logger_group_name=logger_group_name)
        if not result:
            # Problem
            return 'fail', return_msg
        # else: Great success

        return 'ok',

    @request()
    @return_reply()
    def request_debug_deprogram_all(self, sock):
        """
        Deprogram all the f and x roaches
        :param sock:
        :return:
        """
        try:
            from casperfpga import utils as fpgautils
            fhosts = self.instrument.fhosts
            xhosts = self.instrument.xhosts
            fpgautils.threaded_fpga_function(fhosts, 10, 'deprogram')
            fpgautils.threaded_fpga_function(xhosts, 10, 'deprogram')
        except Exception as ex:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, 'unknown exception')
        return 'ok',

    @request(Str(), Int(), Int(), Int())
    @return_reply(Str(multiple=True))
    def request_debug_gain_range(self, sock, source_name, value, fstart, fstop):
        """
        Apply and/or get the gain settings for an input
        :param sock:
        :param source_name: the source on which to act
        :param value: the equaliser values
        :param fstart: the channel on which to start applying this gain
        :param fstop: the channel at which to stop
        :return:
        """
        if source_name == '':
            return self._log_excep(None, 'no source name given')
        n_chans = self.instrument.n_chans
        eq_vals = [0] * fstart
        eq_vals.extend([value] * (fstop - fstart))
        eq_vals.extend([0] * (n_chans - fstop))
        assert len(eq_vals) == n_chans
        if len(eq_vals) > 0 and eq_vals[0] != '':
            try:
                self.instrument.fops.set_eq(True, source_name, list(eq_vals))
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(stack_trace, 'Failed setting eq for input {0}'.format(source_name))
        _src = self.instrument.fops.get_eq(source_name)
        return tuple(['ok'] + Corr2Server.rv_to_liststr(_src[source_name]))

    @request(Str(default='', multiple=True))
    @return_reply()
    def request_debug_gain_all(self, sock, *eq_vals):
        """
        Apply and/or get the gain settings for an input
        :param sock:
        :param eq_vals: the equaliser values
        :return:
        """
        if len(eq_vals) > 0 and eq_vals[0] != '':
            try:
                self.instrument.fops.set_eq(True, None, list(eq_vals))
            except Exception as ex:
                stack_trace = traceback.format_exc()
                return self._log_stacktrace(stack_trace, 'Failed setting all eqs.')
        else:
            return self._log_excep(None, 'did not give new eq values?')
        return 'ok',

    @request(Str(default='INFO'), Str('CLOWNS EVERYWHERE!!!'))
    @return_reply()
    def request_debug_log(self, sock, level, msg):
        """
        Log a test message - to test the formatter and handler
        :param sock:
        :param level:
        :param msg:
        :return:
        """
        self.instrument.logger.log(eval('logging.{}'.format(level)), msg)
        return 'ok',

    @request()
    @return_reply()
    def request_debug_stdouterr(self, sock):
        """
        Blargh.
        :param sock:
        :return:
        """
        import time
        ts = str(time.time())
        print('This should go to standard out. ' + ts)
        sys.stderr.write('This should go to standard error. {}\n'.format(ts))
        return 'ok',

    # @request(Int())
    # @return_reply()
    # def request_debug_periodic_metadata(self, sock, new_cadence):
    #     """
    #     Change the cadence of sending the periodic metadata.
    #     :param sock:
    #     :param new_cadence: cadence, in seconds. 0 will disable the function
    #     :return:
    #     """
    #     prev = self.metadata_cadence
    #     self.metadata_cadence = new_cadence
    #     if new_cadence == 0:
    #         self._logger.info('Disabled periodic metadata.')
    #     else:
    #         self._logger.info('Enabled periodic metadata @ %i '
    #                      'seconds.' % new_cadence)
    #         if prev == 0:
    #             IOLoop.current().call_later(self.metadata_cadence,
    #                                         self.periodic_issue_metadata)
    #     return 'ok',
    #
    # @gen.coroutine
    # def periodic_issue_metadata(self):
    #     """
    #     Periodically send all instrument metadata.
    #
    #     :return:
    #     """
    #     if self.metadata_cadence == 0:
    #         return
    #     try:
    #         yield self.executor.submit(self.instrument.stream_issue_metadata)
    #     except Exception as ex:
    #         self._log_excep(ex, 'Error sending metadata')
    #     self._logger.debug('self.periodic_issue_metadata ran')
    #     IOLoop.current().call_later(self.metadata_cadence,
    #                                 self.periodic_issue_metadata)

    @request(Int())
    @return_reply()
    def request_debug_periodic_descriptors(self, sock, new_cadence):
        """
        Change the cadence of sending the periodic descriptors.
        :param sock:
        :param new_cadence: cadence, in seconds. 0 will disable the function
        :return:
        """
        prev = self.descriptor_cadence
        self.descriptor_cadence = new_cadence
        if new_cadence == 0:
            self._logger.info('Disabled periodic descriptors.')
        else:
            self._logger.info('Enabled periodic descriptors @ {}seconds.'.format(new_cadence))
            if prev == 0:
                IOLoop.current().call_later(self.descriptor_cadence, self.periodic_issue_descriptors)
        return 'ok',

    @gen.coroutine
    def periodic_issue_descriptors(self):
        """
        Periodically send all instrument descriptors.

        :return:
        """

        number_of_descriptors = self.instrument.stream_get_number_of_descriptors()
        time_step = self.descriptor_cadence / (number_of_descriptors + 5.0)  # 5.0 is just chosen arbitrarily, just needs to be greater than 1.0 and formatted as a double, not an integer

        if self.descriptor_cadence == 0:
            return
        
        for i in range(number_of_descriptors):
            IOLoop.current().call_later(time_step * (i + 1), self.issue_single_descriptor, i)

        #try:
        #    yield self.executor.submit(self.instrument.stream_issue_descriptors)
        #except Exception as ex:
        #    self._log_excep(ex, 'Error sending metadata')

        self._logger.debug('self.periodic_issue_descriptors ran')
        IOLoop.current().call_later(self.descriptor_cadence, self.periodic_issue_descriptors)

    @gen.coroutine
    def issue_single_descriptor(self, index):
        """
        Issue a single descriptor.
        :param index: index of descriptor to issue
        :return:
        """
        try:
            yield self.executor.submit(self.instrument.stream_issue_descriptor_single, index)
        except Exception as exc:
            stack_trace = traceback.format_exc()
            self._log_stacktrace(stack_trace, 'Error sending metadata')

    @request(Str())
    @return_reply(Str())
    def request_debug_getattr(self, sock, attr):
        """
        Get any attribute from the running instrument.
        :param sock:
        :param attr: atrtibute to get
        :return:
        """
        try:
            return 'ok', str(getattr(self.instrument, attr))
        except Exception as exc:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, exc.message)

    @request()
    @return_reply(Str())
    def request_get_config(self, sock):
        """
        Get the contents of the config dictionary from the instrument.
        :param sock:
        :return:
        """
        try:
            return 'ok', str(getattr(self.instrument, 'configd'))
        except Exception as exc:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, exc.message)

    @request()
    @return_reply(Str())
    def request_get_running_config(self, sock):
        """
        Get the calculated/running config dictionary from the instrument.
        :param sock:
        :return:
        """
        try:
            return 'ok', str(getattr(self.instrument, 'running_config'))
        except Exception as exc:
            stack_trace = traceback.format_exc()
            return self._log_stacktrace(stack_trace, exc.message)

    # @request(Str())
    # @return_reply(Str())
    # def request_debug_setattr(self, sock, attr, setvalue):
    #     """
    #     Get any attribute from the running instrument.
    #     :param sock:
    #     :param attr: atrtibute to set
    #     :param setvalue: set the attribute to this (eval'd) value
    #     :return:
    #     """
    #     try:
    #         setattr(self.instrument, attr, eval(setvalue))
    #         return 'ok', str(getattr(self.instrument, attr))
    #     except Exception as exc:
    #         return 'fail', exc.message


# @gen.coroutine
# def send_test_informs(server):
#     supdate_inform = katcp.Message.inform('test-mass-inform',
#                                           'arg0', 1.111, 'arg2',
#                                           time.time())
#     server.mass_inform(supdate_inform)
#     tornado.ioloop.IOLoop.current().call_later(5, send_test_informs, server)


@gen.coroutine
def on_shutdown(ioloop, server):
    """
    Shut down the ioloop sanely.
    :param ioloop: the current tornado.ioloop.IOLoop
    :param server: a katcp.DeviceServer instance
    :return:
    """
    print('corr2 server shutting down')
    yield server.stop()
    ioloop.stop()


if __name__ == '__main__':

    parser = ArgumentParser(
        description='Start a corr2 instrument server.',
        formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-p', '--port', dest='port', action='store', default=1235, type=int,
        help='bind to this port to receive KATCP messages')
    parser.add_argument(
        '--log_level', dest='log_level', action='store', default='INFO',
        help='log level to set')
    parser.add_argument(
        '--log_format_katcp', dest='lfm', action='store_true', default=False,
        help='format log messsages for katcp')
    parser.add_argument(
        '--config', dest='config', type=str, action='store', default=None,
        help='a corr2 config file')
    parser.add_argument(
        '--no_tornado', dest='no_tornado', action='store_true', default=False,
        help='do NOT use the tornado version of the Katcp server')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.log_level)
    except Exception:
        raise RuntimeError('Received nonsensical log level {}'.format(args.log_level))
    
    if args.config is None:
        # Problem
        errmsg = 'No config file specified!'
        raise ValueError(errmsg)

    server = Corr2Server('127.0.0.1', args.port, tornado=(not args.no_tornado),
                        config=args.config, log_level=args.log_level)

    print('Server listening on port {} '.format(args.port, end=''))

    # def boop():
    #     raise KeyboardInterrupt

    if not args.no_tornado:
        ioloop = IOLoop.current()
        signal.signal(
            signal.SIGINT,
            lambda sig, frame: ioloop.add_callback_from_signal(
                on_shutdown, ioloop, server))
        server.set_ioloop(ioloop)
        ioloop.add_callback(server.start)
        # ioloop.call_later(120, boop)
        # ioloop.add_callback(send_test_informs, server)
        print('started with ioloop. Running somewhere in the ether... '
              'exit however you see fit.')
        ioloop.start()
    else:
        queue = Queue.Queue()
        server.set_restart_queue(queue)
        server.start()
        print('started with no ioloop. Running somewhere in the ether... '
              'exit however you see fit.')
        try:
            while True:
                try:
                    device = queue.get(timeout=0.5)
                except Queue.Empty:
                    device = None
                if device is not None:
                    print('Stopping...')
                    device.stop()
                    device.join()
                    print('Restarting...')
                    device.start()
                    print('Started.')
        except KeyboardInterrupt:
            print('Shutting down...')
            server.stop()
            server.join()
# end
