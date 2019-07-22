# import logging
# Yes, I know it's just an integer value
from logging import INFO
import time



from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid

from katcp import Sensor, Message

from corr2.corr2LogHandlers import getKatcpLogger

import data_stream

# LOGGER = logging.getLogger(__name__)


class Corr2Sensor(Sensor):

    @classmethod
    def integer(cls, name, description=None, unit='', params=None,
                default=None, initial_status=None,
                manager=None, executor=None,
                *args, **kwargs):
        return cls(cls.INTEGER, name, description, unit, params,
                   default, initial_status, manager, executor,
                   *args, **kwargs)

    @classmethod
    def float(cls, name, description=None, unit='', params=None,
              default=None, initial_status=None,
              manager=None, executor=None,
             *args, **kwargs):
        return cls(cls.FLOAT, name, description, unit, params,
                   default, initial_status, manager, executor,
                   *args, **kwargs)

    @classmethod
    def boolean(cls, name, description=None, unit='',
                default=None, initial_status=None,
                manager=None, executor=None,
                *args, **kwargs):
        return cls(cls.BOOLEAN, name, description, unit, None,
                   default, initial_status, manager, executor,
                   *args, **kwargs)

    @classmethod
    def lru(cls, name, description=None, unit='',
            default=None, initial_status=None,
            manager=None, executor=None,
            *args, **kwargs):
        return cls(cls.LRU, name, description, unit, None,
                   default, initial_status, manager, executor,
                   *args, **kwargs)

    @classmethod
    def string(cls, name, description=None, unit='',
               default=None, initial_status=None,
               manager=None, executor=None,
               *args, **kwargs):
        return cls(cls.STRING, name, description, unit, None,
                   default, initial_status, manager, executor,
                   *args, **kwargs)

    @classmethod
    def device_status(cls, name, description=None, unit='',
               default=None, initial_status=None,
               manager=None, executor=None,
               *args, **kwargs):
        return cls(cls.DISCRETE, name=name, description=description, 
                   units=unit, params=['ok','fail','degraded'],
                   default=default, initial_status='ok', manager=manager, 
                   executor=executor,*args, **kwargs)

    def __init__(self, sensor_type, name, description=None, units='',
                 params=None, default=None, initial_status=None,
                 manager=None, executor=None,
                 *args, **kwargs):

        # Log to the parent SensorManager.logger for now
        self.logger = manager.logger

        if '_' in name:
            self.logger.debug('Sensor names cannot have underscores in them, '
                         'so {name} becomes {name_conv}'.format(
                             name=name, name_conv=name.replace('_', '-')))
            name = name.replace('_', '-')
        self.manager = manager
        self.executor = executor
        super(Corr2Sensor, self).__init__(sensor_type, name, description,
                                          units, params, default,
                                          initial_status)

    def set(
            self,
            timestamp=None,
            status=None,
            value=None,
            errif=None,
            warnif=None):
        """
        Set the value of a sensor.
        :param timestamp: when was the reading taken? default to time.time()
        :param status: defaults to Sensor.NOMINAL.
        :param value: defaults to None
        :param errif: set status to ERROR if value 'changed' or 'notchanged'.
        :param warnif: set status to WARNING if value 'changed' or 'notchanged'.
        :return:
        """

        status_none = 0
        if value is None:
            raise ValueError('Cannot set a sensor to None')
        if timestamp is None:
            timestamp = time.time()
        if status is None:
            status_none = 1
            status = Sensor.NOMINAL
        (old_timestamp, old_status, old_value) = self.read()
        if (old_status == status) and (old_value == value):
            self.logger.debug('Sensor values unchanged, ignoring')
            return

        if (value == False):
            if (errif == 'False'):
                self.logger.error('Sensor error: {} is False'.format(self.name))
                if(status_none == 1):
                    status = Sensor.ERROR
            elif (warnif == 'False'):
                self.logger.warn('Sensor warning: {} is False'.format(self.name))
                if(status_none == 1):
                    status = Sensor.WARN
            else:
                if(status_none == 1):
                    status = Sensor.NOMINAL

        elif (value):
            if (errif == 'True'):
                self.logger.error('Sensor error: {} is True'.format(self.name))
                if(status_none == 1):
                    status = Sensor.ERROR
            elif warnif == 'True':
                self.logger.warn('Sensor warning: {} is True'.format(self.name))
                if(status_none == 1):
                    status = Sensor.WARN
            else:
                if(status_none == 1):
                    status = Sensor.NOMINAL

        if old_value != value:
            if errif == 'changed':
                self.logger.error(
                    'Sensor error: {} changed {} -> {}'.format(self.name, old_value, value))
                if(status_none == 1):
                    status = Sensor.ERROR
            elif warnif == 'changed':
                self.logger.warn(
                    'Sensor warning: {} changed {} -> {}'.format(self.name, old_value, value))
                if(status_none == 1):
                    status = Sensor.WARN
        else:
            if errif == 'notchanged':
                if(status_none == 1):
                    status = Sensor.ERROR
                self.logger.error(
                    'Sensor error: {} not changing {} -> {}'.format(self.name, old_value, value))
            elif warnif == 'notchanged':
                if(status_none == 1):
                    status = Sensor.WARN
                self.logger.warn(
                    'Sensor warning: {} not changing {} -> {}'.format(self.name, old_value, value))
        super(Corr2Sensor, self).set(timestamp, status, value)
        if self.manager:
            self.manager.sensor_set_cb(self)

    def deactivate(self):
        """
        Deactivate this sensor - used mostly when names change.
        :return:
        """
        self.set(time.time(), self.INACTIVE, None)


class SensorManager(object):
    """
    A place to store information and functionality relevant to corr2 sensors.
    """

    def __init__(self, katcp_server, instrument,
                 katcp_sensors=True, kcs_sensors=True,
                 *args, **kwargs):
        """
        Start a Sensor Manager
        :param katcp_server: a KATCP server instance
        :param instrument: a corr2 instance
        :param katcp_sensors: add sensors to the Katcp server itself
        :param kcs_sensors: manually emit informs to the attached KCS
        :return:
        """
        self.katcp_server = katcp_server
        self.instrument = instrument

        if instrument is None:
            # You are a strong, independent SensorManager
            self.getLogger = getKatcpLogger
            logger_name = '{}_sens_man'.format(katcp_server.host.host)
        else:
            # The instrument already has a getLogger attribute
            self.getLogger = instrument.getLogger
            logger_name = '{}_sens_man'.format(instrument.descriptor)

        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)
        result, self.logger = self.getLogger(logger_name=logger_name,
                                             log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format()
            raise ValueError(errmsg)

        self.katcp_sensors = katcp_sensors
        self.kcs_sensors = kcs_sensors
        self._sensors = {}
        self._debug_mode = False

    def sensors(self):
        return self._sensors

    def sensors_clear(self):
        """
        Clear the current sensors
        :return:
        """
        self._sensors = {}

    def sensor_add(self, sensor):
        """
        Add a sensor to the dictionary of instrument sensors
        :param sensor:
        :return:
        """
        if sensor.name in self._sensors.keys():
            raise KeyError('Sensor {} already exists'.format(sensor.name))
        self._sensors[sensor.name] = sensor

    def sensor_create(self, sensor):
        """
        Wrapper to create a sensor in the relevant places
        :param sensor: A katcp.Sensor
        :return:
        """
        self.sensor_add(sensor)
        if self.katcp_sensors:
            self.katcp_server.add_sensor(sensor)
        if self.kcs_sensors:
            self._kcs_sensor_create(sensor)

    def sensor_get(self, sensor_name):
        """
        Get a sensor from the dictionary of instrument sensors
        :param sensor_name:
        :return:
        """
        if sensor_name not in self._sensors.keys():
            raise KeyError('Sensor {} does not exist'.format(sensor_name))
        return self._sensors[sensor_name]

    def sensor_deactivate(self, sensor):
        """
        Remove a sensor from the list of sensors we're managing, after setting
        its state to inactive.
        :param sensor: the sensor, or sensor name, to deactivate
        :return:
        """
        if not hasattr(sensor, 'set'):
            sensor = self.sensor_get(sensor)
        sensor.deactivate()
        self._sensors.pop(sensor.name)

    def sensor_set(self, sensor, value, status=Corr2Sensor.NOMINAL,
                   timestamp=None):
        """
        Set the value, status and timestamp of a sensor.
        :param sensor: the sensor, or sensor name, to set
        :param value:
        :param status:
        :param timestamp:
        :return:
        """
        if not hasattr(sensor, 'set'):
            sensor = self.sensor_get(sensor)
        sensor.set(timestamp or time.time(), status, value)

    def sensor_set_cb(self, sensor):
        """
        Called by a Corr2Sensor AFTER it has been updated.
        :param sensor: A Corr2Sensor
        :return:
        """
        if self.kcs_sensors:
            self._kcs_sensor_set(sensor)

    def _kcs_sensor_set(self, sensor):
        """
        Generate #sensor-status informs to update sensors"

        #sensor-status timestamp 1 sensor-name status value

        :param sensor: A katcp.Sensor object
        :return:
        """
        if self._debug_mode:
            self.logger.info('SENSOR_DEBUG: sensor-status ' + str(time.time()) +
                        ' ' + sensor.name + ' ' +
                        str(sensor.STATUSES[sensor.status()]) + ' ' +
                        str(sensor.value()))
            return
        assert self.kcs_sensors
        supdate_inform = Message.inform(
            'sensor-status', time.time(), 1, sensor.name,
            sensor.STATUSES[sensor.status()], sensor.value())
        self.katcp_server.mass_inform(supdate_inform)

    def _kcs_sensor_create(self, sensor):
        """
        Create a sensor on the katcp server with a sensor-list inform.

        #sensor-list sensor-name description units type

        :param sensor: A katcp.Sensor object
        :return:
        """
        # descr = sensor.description.replace(' ', '\_')
        descr = sensor.description
        if self._debug_mode:
            self.logger.info('SENSOR_DEBUG: sensor-list ' + sensor.name + ' ' +
                        descr + ' ' + sensor.units + ' ' + str(sensor.type))
            return
        assert self.kcs_sensors
        screate_inform = Message.inform(
            'sensor-list', sensor.name, descr,
            sensor.units, sensor.type)
        self.katcp_server.mass_inform(screate_inform)
        self._kcs_sensor_set(sensor)

    def do_sensor(self, sensor_type, name, description,
                  initial_status=Sensor.UNKNOWN, unit='',
                  executor=None):
        """
        Bundle sensor creation and updating into one method.
        :param sensor_type: The Sensor class to instantiate if the sensor
        does not already exist.
        :param name: The name of the Sensor.
        :param description: A brief textual description.
        :param initial_status: UNKNOWN by default.
        :param unit: A str, if given.
        :param executor: an executor (thread, future, etc)
        :return:
        """
        if '_' in name:
            self.logger.warning(
                'Sensor names cannot have underscores in them, so {name} '
                'becomes {name_conv}'.format(
                    name=name, name_conv=name.replace('_', '-')))
            name = name.replace('_', '-')
        try:
            sensor = self.sensor_get(name)
        except KeyError:
            sensor = sensor_type(
                name=name,
                description=description,
                unit=unit, initial_status=initial_status, manager=self,
                executor=executor)
            self.sensor_create(sensor)
        return sensor


class Corr2SensorManager(SensorManager):
    """
    An implementation of SensorManager with some extra functionality for
    correlator-specific sensors.
    """

    def sensors_stream_destinations(self):
        """
        Sensors for all stream destinations.
        :return:
        """
        for stream in self.instrument.data_streams:
            sensor = self.do_sensor(
                Corr2Sensor.string, '{}-destination'.format(stream.name),
                'The IP, range and port to which data for this stream is sent.')
            sensor.set_value(stream.destination)

            if stream.category is not data_stream.DIGITISER_ADC_SAMPLES:
                sensor = self.do_sensor(
                    Corr2Sensor.string, '{}-source'.format(stream.name),
                    'The sources from which data is received to create this stream')
                sensor.set_value(stream.source or '')

    def sensors_gbe_interfacing(self):
        """
        Information about the host 10gbe interfaces.
        :return:
        """
        def iface_sensors_for_host(host, eng, iface):
            dpref = 'Engine {eng} interface {iface} '.format(
                eng=eng, iface=iface)
            sensor_value = '({mac},{ip},{port})'.format(
                mac=str(host.gbes[iface].mac),
                ip=str(host.gbes[iface].ip_address),
                port=str(host.gbes[iface].port))
            sensor = self.do_sensor(
                Corr2Sensor.string,
                '{eng}-{iface}-details'.format(eng=eng, iface=iface),
                '{prf} (MAC,IP,port)'.format(prf=dpref))
            sensor.set_value(sensor_value)

        for ctr, host in enumerate(self.instrument.fhosts):
            for gbe in host.gbes:
                iface_sensors_for_host(host, 'fhost{0}'.format(ctr), gbe.name)

        for ctr, host in enumerate(self.instrument.xhosts):
            for gbe in host.gbes:
                iface_sensors_for_host(host, 'xhost{0}'.format(ctr), gbe.name)

        # TODO
        # if self.instrument.bhosts:
        #     for ctr, host in enumerate(self.instrument.bhosts):
        #         for gbe in host.gbes:
        #             iface_sensors_for_host(host, 'beng{}'.format(ctr), gbe.name)

    def sensors_host_mapping(self):
        """
        Host-to-engine mapping sensors.
        :return:
        """
        instr = self.instrument
        map_list = instr.fops.fengine_to_host_mapping()
        map_list.update(instr.xops.xengine_to_host_mapping())
        map_str = str(map_list)

        sensor = self.do_sensor(Corr2Sensor.string, 'host-mapping',
                                'Indicates on which physical host a set of '
                                'engines can be found.')
        sensor.set_value(map_str)

    def sensors_sync_time(self):
        """
        The instrument synchronisation time.
        :return:
        """
        val = self.instrument.synchronisation_epoch
        val = 0.0 if val < 0.0 else float(val)
        sensor = self.do_sensor(
            Corr2Sensor.float, 'sync-time',
            'The time at which the digitisers were synchronised. Seconds '
            'since the Unix Epoch.', unit='s')
        sensor.set_value(val)

    def sensors_transient_buffer_ready(self):
        """
        Is the transient buffer ready to trigger?
        :return:
        """
        sensor = self.do_sensor(
            Corr2Sensor.boolean, 'transient-buffer-ready',
            'The transient buffer is ready to be triggered.', unit='s')
        sensor.set_value(True)

    def sensors_input_labels(self):
        """
        Update all sensors that are affected by input labels.
        :return:
        """
        mapping = self.instrument.get_input_mapping()
        sensor = self.do_sensor(
            Corr2Sensor.string, 'input-labelling',
            'Mapping of input labels to hardware LRUs and input numbers: '
            '(input-label, input-index, LRU host, index-on-host)')
        sensor.set_value(str(mapping))

    def sensors_baseline_ordering(self):
        """

        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.XENGINE_CROSS_PRODUCTS)
        for stream in streams:
            sensor = self.do_sensor(
                Corr2Sensor.string, '{}-bls-ordering'.format(stream.name),
                'A string showing the output ordering of baseline data '
                'produced by the X-engines in this instrument, as a list '
                'of correlation pairs given by input label.')
            sensor.set_value(self.instrument.xops.get_baseline_ordering())

    def sensors_xeng_acc_time(self):
        """
        Create a sensor to display the current accumulation time
        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.XENGINE_CROSS_PRODUCTS)
        for stream in streams:
            strmnm = stream.name
            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-accs'.format(strmnm),
                'The number of spectra that are accumulated per X-engine '
                'output.')
            spec_acclen = (self.instrument.accumulation_len *
                           self.instrument.xeng_accumulation_len)
            sensor.set_value(int(spec_acclen))
            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-int-time'.format(strmnm),
                'The time, in seconds, for which the X-engines accumulate.',
                unit='s')
            sensor.set_value(self.instrument.xops.get_acc_time())

    # def sensors_xeng_stream_destination(self):
    #     """
    #     Set the sensors to display where the x-engine streams go
    #     :return:
    #     """
    #     streams = self.instrument.get_data_streams_by_type(
    #         data_stream.XENGINE_CROSS_PRODUCTS)
    #     for stream in streams:
    #         strmnm = stream.name
    #         txip = str(stream.destination.ip_address)
    #         txport = stream.destination.port
    #         sensor = self.do_sensor(
    #             Corr2Sensor.string, '{}-destination'.format(strmnm),
    #             'IP and port of stream destination')
    #         sensor.set_value('{ip}:{port}'.format(ip=txip, port=txport))
    #
    # def sensors_feng_stream_destination(self):
    #     """
    #     Set the sensors to display where the f-engine streams go
    #     :return:
    #     """
    #     streams = self.instrument.get_data_streams_by_type(
    #         data_stream.FENGINE_CHANNELISED_DATA)
    #     for stream in streams:
    #         strmnm = stream.name
    #         txip = str(stream.destination.ip_address)
    #         txport = stream.destination.port
    #         sensor = self.do_sensor(
    #             Corr2Sensor.string, '{}-destination'.format(strmnm),
    #             'IP and port of stream destination')
    #         sensor.set_value('{ip}:{port}'.format(ip=txip, port=txport))

    def sensors_xeng_streams(self):
        """
        X-engine stream sensors
        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.XENGINE_CROSS_PRODUCTS)

        for stream in streams:
            strmnm = stream.name
            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-xeng-acc-len'.format(strmnm),
                'Number of accumulations performed internal to the X-engine.')
            sensor.set_value(self.instrument.xeng_accumulation_len)

            sensor = self.do_sensor(
                Corr2Sensor.integer,
                '{}-xeng-out-bits-per-sample'.format(strmnm),
                'X-engine output bits per sample. Per number, not complex '
                'pair. Real and imaginary parts are both this wide.')
            sensor.set_value(self.instrument.xeng_outbits)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-bls'.format(strmnm),
                'The number of baselines produced by this correlator '
                'instrument.')
            sensor.set_value(len(self.instrument.xops.get_baseline_ordering()))

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-chans'.format(strmnm),
                'Number of channels in the integration.')
            sensor.set_value(self.instrument.n_chans)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-chans-per-substream'.format(strmnm),
                'Number of channels in each x-engine substream.')
            n_xeng = len(self.instrument.xhosts) * self.instrument.x_per_fpga
            sensor.set_value(self.instrument.n_chans / n_xeng)

            sensor = self.do_sensor(
                sensor_type=Corr2Sensor.integer,
                name='{}-payload-len'.format(strmnm),
                description='The payload size of the X-engine data stream pkts')
            sensor.set_value(self.instrument.x_stream_payload_len)

        self.sensors_xeng_acc_time()
        self.sensors_baseline_ordering()

    def sensors_feng_fft_shift(self):
        """
        Update the fft-shift sensors
        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.FENGINE_CHANNELISED_DATA)
        assert len(streams) == 1
        for stream in streams:
            strmnm = stream.name
            for feng in self.instrument.fops.fengines:
                pref = '{strm}-input{npt}'.format(strm=strmnm,
                                                  npt=feng.input_number)
                sensor = self.do_sensor(
                    Corr2Sensor.integer, '{}-fft0-shift'.format(pref),
                    'The FFT bitshift pattern for the <n>th FFT in the design. '
                    'n=0 is first in the RF chain (closest to source).')
                sensor.set_value(feng.host.get_fft_shift())

    def sensors_feng_eq(self, feng):
        streams = self.instrument.get_data_streams_by_type(
            data_stream.FENGINE_CHANNELISED_DATA)
        assert len(streams) == 1
        strmnm = streams[0].name
        pref = '{strm}-input{npt}'.format(strm=strmnm, npt=feng.input_number)
        sensor = self.do_sensor(
            Corr2Sensor.string, '{}-eq'.format(pref),
            'The unitless, per-channel digital scaling factors '
            'implemented prior to requantisation. Complex.')
        sensor.set_value(str(feng.last_eq))

    def sensors_feng_delays(self, feng):
        """
        F-engine delay sensors
        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.FENGINE_CHANNELISED_DATA)
        if len(streams) != 1:
            raise RuntimeError(
                'Expecting one Feng stream, got %i?' %
                (len(streams)))
        strmnm = streams[0].name
        pref = '{strm}-input{npt}'.format(strm=strmnm, npt=feng.input_number)
        sensor = self.do_sensor(
            Corr2Sensor.string, '{}-delay'.format(pref),
            'The delay settings for this input: (loadmcnt <ADC sample count when model was loaded>, delay <in seconds>, '
            'delay-rate <unit-less, or, seconds-per-second>, phase <radians>, phase-rate <radians per second>).')
       # err_sensor = self.do_sensor(
       #     Corr2Sensor.boolean, '{}-delay-ok'.format(pref),
       #     'Delays for this input are functioning correctly.')

        if feng.last_delay is not None:
            import numpy
            delay = feng.last_delay.delay / self.instrument.sample_rate_hz
            delay_delta = feng.last_delay.delay_delta
            phase_offset = feng.last_delay.phase_offset * numpy.pi
            phase_offset_delta = feng.last_delay.phase_offset_delta * (
                numpy.pi * self.instrument.sample_rate_hz)
            load_mcnt = feng.last_delay.load_mcnt
            _val = '({:d}, {:.10e}, {:.10e}, {:.10e}, {:.10e})'.format(
                load_mcnt, delay, delay_delta, phase_offset, phase_offset_delta)
            _timestamp = self.instrument.time_from_mcnt(
                feng.last_delay.load_mcnt)
            _status = Sensor.NOMINAL if feng.last_delay.last_load_success else Sensor.ERROR
            sensor.set_value(value=_val, status=_status, timestamp=_timestamp)
#            err_sensor.set_value(feng.last_delay.last_load_success)
            load_time = self.instrument.time_from_mcnt(
                feng.last_delay.load_mcnt)
            self.logger.debug(
                '{}: Delay update @mcnt {} ({}), {:.10e}, {:.10e}, {:.10e}, {:.10e}'.format(
                    feng.name,
                    load_mcnt,
                    load_time,
                    delay,
                    delay_delta,
                    phase_offset,
                    phase_offset_delta))

    def sensors_feng_streams(self):
        """
        F-engine stream sensors
        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.FENGINE_CHANNELISED_DATA)

        assert len(streams) == 1
        import numpy
        for stream in streams:
            strmnm = stream.name

            sensor = self.do_sensor(
                Corr2Sensor.integer,
                '{}-feng-out-bits-per-sample'.format(strmnm),
                'F-engine output bits per sample.')
            bits = int(numpy.floor(self.instrument.quant_format))
            sensor.set_value(bits)

            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-center-freq'.format(strmnm),
                'The CBF center frequency of the digitised band.')
            sensor.set_value(self.instrument.analogue_bandwidth / 2.0)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-chans'.format(strmnm),
                'Number of channels in the output spectrum.')
            sensor.set_value(self.instrument.n_chans)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-chans-per-substream'.format(strmnm),
                'Number of channels in each substream.')
            n_xeng = len(self.instrument.xhosts) * self.instrument.x_per_fpga
            sensor.set_value(self.instrument.n_chans / n_xeng)

            sensor = self.do_sensor(
                Corr2Sensor.integer,
                '{}-coarse-chans'.format(strmnm),
                'Number of channels in the first PFB in a cascaded-PFB design.')
            sensor.set_value(-1)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-current-coarse-chan'.format(strmnm),
                'The selected coarse channel in a cascaded-PFB design.')
            sensor.set_value(-1)

            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-ddc-mix-freq'.format(strmnm),
                'The F-engine DDC mixer frequency, where used. 1 when n/a.')
            sensor.set_value(1)

            sensor = Corr2Sensor.integer(
                name='{}-n-samples-between-spectra'.format(strmnm),
                description='Number of samples between spectra.',
                unit='samples',
                initial_status=Sensor.UNKNOWN, manager=self)
            self.sensor_create(sensor)
            sensor.set_value(self.instrument.n_chans * 2)

            sensor = Corr2Sensor.integer(
                name='{}-pfb-group-delay'.format(strmnm),
                description='Group delay for PFB.', unit='samples',
                initial_status=Sensor.UNKNOWN, manager=self)
            self.sensor_create(sensor)
            sensor.set_value(self.instrument.pfb_group_delay)

            sensor = self.do_sensor(
                sensor_type=Corr2Sensor.integer, name='{}-payload-len'.format(strmnm),
                description='The payload size of the F-engine data stream pkts')
            sensor.set_value(self.instrument.f_stream_payload_len)


        self.sensors_feng_fft_shift()
        for feng in self.instrument.fops.fengines:
            self.sensors_feng_eq(feng)
            self.sensors_feng_delays(feng)

    def sensors_beng_weights(self):
        """

        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.BEAMFORMER_FREQUENCY_DOMAIN)
        for stream in streams:
            strmnm = stream.name
            beam = self.instrument.bops.beams[strmnm]
            sensor = self.do_sensor(
                Corr2Sensor.string, '{strm}-weight'.format(strm=strmnm),
                'The summing weights applied to the inputs of this beam.')
            sensor.set_value(
                str(self.instrument.bops.get_beam_weights(strmnm)))

    def sensors_beng_gains(self):
        """

        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.BEAMFORMER_FREQUENCY_DOMAIN)
        for stream in streams:
            strmnm = stream.name
            beam = self.instrument.bops.beams[strmnm]
            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-quantiser-gain'.format(strmnm),
                'The non-complex post-summation quantiser gain applied to '
                'this beam.')
            sensor.set_value(self.instrument.bops.get_beam_quant_gain(strmnm))

#    def sensors_beng_passband(self):
#        """
#
#        :return:
#        """
#        streams = self.instrument.get_data_streams_by_type(
#            data_stream.BEAMFORMER_FREQUENCY_DOMAIN)
#        for stream in streams:
#            strmnm = stream.name
#            beam = self.instrument.bops.beams[strmnm]
#            # beam_bw, beam_cf = beam.get_beam_bandwidth()
#            # sensor = self.do_sensor(
#            #     Corr2Sensor.float, '{}-bandwidth'.format(strmnm),
#            #     'Bandwidth of selected beam passband.')
#            # sensor.set_value(beam_bw)
#            # sensor = self.do_sensor(
#            #     Corr2Sensor.float, '{}-center-freq'.format(strmnm),
#            #     'Center frequency of selected beam passband.')
#            # sensor.set_value(beam_cf)
#            sensor = self.do_sensor(
#                Corr2Sensor.integer, '{}-n-chans'.format(strmnm),
#                'Number of channels in selected beam passband.')
#            sensor.set_value(self.instrument.n_chans)

    def sensors_beng_streams(self):
        """
        B-engine stream sensors
        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.BEAMFORMER_FREQUENCY_DOMAIN)

        instrument_inputs = self.instrument.get_input_labels()

        for stream in streams:
            strmnm = stream.name
            beam = self.instrument.bops.beams[strmnm]

            sensor = self.do_sensor(
                Corr2Sensor.integer,
                '{}-beng-out-bits-per-sample'.format(strmnm),
                'B-engine output bits per sample.')
            sensor.set_value(self.instrument.beng_outbits)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-chans-per-substream'.format(strmnm),
                'Number of channels in each substream.')
            n_xeng = len(self.instrument.xhosts) * self.instrument.x_per_fpga
            sensor.set_value(self.instrument.n_chans / n_xeng)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-spectra-per-heap'.format(strmnm),
                'Number of consecutive spectra in each heap.')
            sensor.set_value(self.instrument.xeng_accumulation_len)

            sensor = self.do_sensor(
                Corr2Sensor.string, '{}-source-indices'.format(strmnm),
                'The global input indices of the sources summed in this beam.')
            tmp = beam.source_indices
            sensor.set_value(str(tmp))

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-chans'.format(strmnm),
                'Number of channels in the stream.')
            sensor.set_value(self.instrument.n_chans)

            sensor = self.do_sensor(
                sensor_type=Corr2Sensor.integer,
                name='{}-payload-len'.format(strmnm),
                description='The payload size of the B-engine data stream pkts')
            sensor.set_value(self.instrument.b_stream_payload_len)

        self.sensors_beng_weights()
        self.sensors_beng_gains()

    def setup_mainloop_sensors(self):
        """
        Set up compound sensors to be reported to CAM from the main
            katcp servlet.
        :return:
        """
        # # Set up a 1-worker pool per host to
        # # serialise interactions with each host
        # host_executors = {
        #     host.host: futures.ThreadPoolExecutor(max_workers=1)
        #     for host in instrument.fhosts + instrument.xhosts
        # }
        # general_executor = futures.ThreadPoolExecutor(max_workers=1)

        if not self.instrument.initialised():
            raise RuntimeError('Cannot set up sensors until instrument is '
                               'initialised.')
        if self.katcp_sensors:
            ioloop = getattr(self.instrument, 'ioloop', None)
            if not ioloop:
                ioloop = getattr(self.katcp_server, 'ioloop', None)
            if not ioloop:
                raise RuntimeError('IOLoop-containing katcp version required. '
                                   'Can go no further.')
        self.sensors_clear()
        # sensors from list @
        # https://docs.google.com/spreadsheets/d/12AWtHXPXmkT5e_VT-H__zHjV8_Cba0Y7iMkRnj2qfS8/edit#gid=0
        self.sensors_stream_destinations()
        self.sensors_gbe_interfacing()
        self.sensors_host_mapping()

        sensor = Corr2Sensor.integer(
            name='adc-bits', description='ADC sample bitwidth.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.adc_bitwidth)

        sensor = Corr2Sensor.float(
            name='adc-sample-rate',
            description='Sample rate of the ADC, in Hz.', unit='Hz',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.sample_rate_hz)

        sensor = Corr2Sensor.float(
            name='bandwidth',
            description='The analogue bandwidth of the digitised band.',
            unit='Hz', initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.analogue_bandwidth)

        sensor = Corr2Sensor.float(
            name='scale-factor-timestamp',
            description='Factor by which to divide instrument timestamps '
                        'to convert to unix seconds.',
            unit='Hz', initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.get_scale_factor())

        self.sensors_sync_time()
        self.sensors_transient_buffer_ready()

        sensor = Corr2Sensor.integer(
            name='n-ants',
            description='The number of antennas in the instrument.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.n_antennas)

        sensor = Corr2Sensor.integer(
            name='n-inputs', description='The number of single polarisation '
                                         'inputs to the instrument.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(len(self.instrument.fops.fengines))

        self.sensors_input_labels()

        sensor = Corr2Sensor.integer(
            name='n-fengs',
            description='The number of F-engines in the instrument.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        val = len(self.instrument.fhosts) * self.instrument.f_per_fpga
        sensor.set_value(val)

        sensor = Corr2Sensor.integer(
            name='n-xengs',
            description='The number of X-engines in the instrument.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        val = len(self.instrument.xhosts) * self.instrument.x_per_fpga
        sensor.set_value(val)

        sensor = Corr2Sensor.integer(
            name='n-bengs',
            description='The number of B-engines in the instrument.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        if self.instrument.found_beamformer:
            n_bengs = len(self.instrument.bops.hosts) * \
                self.instrument.bops.beng_per_host
            sensor.set_value(n_bengs)
        else:
            sensor.set_value(-1)

        sensor = Corr2Sensor.integer(
            name='n-feng-hosts',
            description='The number of F-engine hosts in the instrument.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(len(self.instrument.fhosts))

        sensor = Corr2Sensor.integer(
            name='n-xeng-hosts',
            description='The number of X-engine hosts in the instrument.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(len(self.instrument.xhosts))

        sensor = Corr2Sensor.integer(
            name='n-beng-hosts',
            description='The number of B-engine hosts in the instrument.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        if self.instrument.found_beamformer:
            sensor.set_value(len(self.instrument.xhosts))
        else:
            sensor.set_value(-1)

        n_chans = self.instrument.n_chans
        n_xhosts = len(self.instrument.xhosts)
        chans_per_xhost = n_chans / n_xhosts
        for _x in self.instrument.xhosts:
            bid = self.instrument.xops.board_ids[_x.host]
            sensor = Corr2Sensor.string(
                name='xeng-host{}-chan-range'.format(bid),
                description='The range of frequency channels processed '
                            'by xeng board {brd}, inclusive.'.format(brd=bid),
                initial_status=Sensor.UNKNOWN,
                manager=self)
            self.sensor_create(sensor)
            sensor.set_value('({start},{end})'.format(
                start=bid * chans_per_xhost, end=(bid + 1) * chans_per_xhost - 1))

            sensor = Corr2Sensor.string(
                name='beng-host{}-chan-range'.format(bid),
                description='The range of frequency channels processed '
                            'by beng board {brd}, inclusive.'.format(brd=bid),
                initial_status=Sensor.UNKNOWN,
                manager=self)
            self.sensor_create(sensor)
            sensor.set_value('({start},{end})'.format(
                start=bid * chans_per_xhost, end=(bid + 1) * chans_per_xhost - 1))

        #TODO: This is a bit nasty. Should detect what type of engines are in
        #      the build, and get version info for those engines types only.
        hosts = [('f', self.instrument.fhosts[0]),
                 ('b', self.instrument.xhosts[0]),
                 ('x', self.instrument.xhosts[0])]

        for _htype, _h in hosts:
            if 'git' in _h.rcs_info:
                filectr = 0
                for gitfile, gitparams in _h.rcs_info['git'].items():
                    for param, value in gitparams.items():
                        if param != "tag":
                            sensname = 'git-' + _htype + '-' + str(filectr)
                            sensor = Corr2Sensor.string(
                                name=sensname, description='Git info.',
                                initial_status=Sensor.UNKNOWN,
                                manager=self)
                            self.sensor_create(sensor)
                            sensor.set_value(str(param) + ':' + str(value))
                            filectr += 1

            sensor = Corr2Sensor.string(
                name="{}engine-bitstream".format(_htype), description="FPGA bitstream file.",
                initial_status=Sensor.UNKNOWN,
                manager=self)
            self.sensor_create(sensor)
            sensor.set_value(str(_h.bitstream))

        self.sensors_xeng_streams()

        self.sensors_feng_streams()

        self.sensors_beng_streams()


def boolean_sensor_do(host, sensor, funclist):
    """

    :param host:
    :param sensor:
    :param funclist:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(*funclist)
        sensor.sensor_set_on_condition(result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(value=False)
    except Exception as e:
        host.logger.error('Error updating {} for {} - '
                     '{}'.format(sensor.name, host.host, e.message))
        sensor.set(value=False)

# end
