import logging
import time

from katcp import Sensor, Message

import data_stream

LOGGER = logging.getLogger(__name__)


class Corr2Sensor(Sensor):
    @classmethod
    def integer(cls, name, description=None, unit='', params=None,
                default=None, initial_status=None,
                manager=None, executor=None):
        return cls(cls.INTEGER, name, description, unit, params,
                   default, initial_status, manager, executor)

    @classmethod
    def float(cls, name, description=None, unit='', params=None,
              default=None, initial_status=None,
              manager=None, executor=None):
        return cls(cls.FLOAT, name, description, unit, params,
                   default, initial_status, manager, executor)

    @classmethod
    def boolean(cls, name, description=None, unit='',
                default=None, initial_status=None,
                manager=None, executor=None):
        return cls(cls.BOOLEAN, name, description, unit, None,
                   default, initial_status, manager, executor)

    @classmethod
    def lru(cls, name, description=None, unit='',
            default=None, initial_status=None,
            manager=None, executor=None):
        return cls(cls.LRU, name, description, unit, None,
                   default, initial_status, manager, executor)

    @classmethod
    def string(cls, name, description=None, unit='',
               default=None, initial_status=None,
               manager=None, executor=None):
        return cls(cls.STRING, name, description, unit, None,
                   default, initial_status, manager, executor)

    def __init__(self, sensor_type, name, description=None, units='',
                 params=None, default=None, initial_status=None,
                 manager=None, executor=None):
        if '_' in name:
            LOGGER.warning(
                'Sensor names cannot have underscores in them, so {name} '
                'becomes {name_conv}'.format(name=name,
                                             name_conv=name.replace('_', '-')
                                             ))
            name = name.replace('_', '-')
        self.manager = manager
        self.executor = executor
        super(Corr2Sensor, self).__init__(sensor_type, name, description,
                                          units, params, default,
                                          initial_status)

    def set(self, timestamp, status, value):
        """
        Set the value of a sensor.
        :param timestamp:
        :param status:
        :param value:
        :return:
        """
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
                 katcp_sensors=True, kcs_sensors=True):
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
            LOGGER.info('SENSOR_DEBUG: sensor-status ' + str(time.time()) +
                        ' ' + sensor.name + ' ' +
                        str(sensor.STATUSES[sensor.status()]) + ' ' +
                        str(sensor.value()))
            return
        assert self.kcs_sensors
        supdate_inform = Message.inform('sensor-status', time.time(), 1,
                                        sensor.name,
                                        sensor.STATUSES[sensor.status()],
                                        sensor.value())
        self.katcp_server.mass_inform(supdate_inform)

    def _kcs_sensor_create(self, sensor):
        """
        Create a sensor the katcp server with a sensor-list inform:

        #sensor-list sensor-name description units type

        :param sensor: A katcp.Sensor object
        :return:
        """
        descr = sensor.description.replace(' ', '\_')
        if self._debug_mode:
            LOGGER.info('SENSOR_DEBUG: sensor-list ' + sensor.name + ' ' +
                        descr + ' ' + sensor.units + ' ' + str(sensor.type))
            return
        assert self.kcs_sensors
        screate_inform = Message.inform('sensor-list',
                                        sensor.name, descr,
                                        sensor.units, sensor.type)
        self.katcp_server.mass_inform(screate_inform)
        self._kcs_sensor_set(sensor)

    def do_sensor(self, sensor_type, name, description,
                  initial_status=Sensor.NOMINAL, unit='',
                  executor=None):
        """
        Bundle sensor creation and updating into one method.
        :param sensor_type: The Sensor class to instantiate if the sensor
        does not already exist.
        :param name: The name of the Sensor.
        :param description: A brief textual description.
        :param initial_status: Other than NOMINAL.
        :param unit: A str, if given.
        :param executor: an executor (thread, future, etc)
        :return:
        """
        if '_' in name:
            LOGGER.warning('Sensor names cannot have underscores in them, so '
                           '{name} becomes {name_conv}'.format(
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
                'The IP, range and port to which data for this stream is sent.',
                Sensor.UNKNOWN)
            sensor.set_value(stream.destination)

    def sensors_tengbe_interfacing(self):
        """
        Information about the host 10gbe interfaces.
        :return:
        """
        def iface_sensors_for_host(host, eng, iface):
            dpref = 'Engine {eng} interface {iface} '.format(
                eng=eng, iface=iface)

            sensor = self.do_sensor(
                Corr2Sensor.string,
                '{eng}-{iface}-ip'.format(eng=eng, iface=iface),
                '{prf} IP address'.format(prf=dpref))
            sensor.set_value(str(host.tengbes[iface].ip_address))

            sensor = self.do_sensor(
                Corr2Sensor.string,
                '{eng}-{iface}-mac'.format(eng=eng, iface=iface),
                '{prf} MAC address'.format(prf=dpref))
            sensor.set_value(str(host.tengbes[iface].mac))

            sensor = self.do_sensor(
                Corr2Sensor.string,
                '{eng}-{iface}-multicast-subscriptions'.format(
                    eng=eng, iface=iface),
                '{prf} multicast subscriptions'.format(prf=dpref))
            sensor.set_value(str(host.tengbes[iface].multicast_subscriptions))

            sensor = self.do_sensor(
                Corr2Sensor.integer,
                '{eng}-{iface}-port'.format(eng=eng, iface=iface),
                '{prf} port'.format(prf=dpref))
            sensor.set_value(host.tengbes[iface].port)

        for ctr, host in enumerate(self.instrument.fhosts):
            for gbe in host.tengbes:
                iface_sensors_for_host(host, 'feng{0}'.format(ctr), gbe.name)

        for ctr, host in enumerate(self.instrument.xhosts):
            for gbe in host.tengbes:
                iface_sensors_for_host(host, 'xeng{0}'.format(ctr), gbe.name)

        # TODO
        # if self.instrument.bhosts:
        #     for ctr, host in enumerate(self.instrument.bhosts):
        #         for gbe in host.tengbes:
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
        val = 0 if val < 0 else val
        sensor = self.do_sensor(Corr2Sensor.integer, 'sync-time',
                                'The time at which the digitisers were '
                                'synchronised. Seconds since the Unix Epoch.',
                                Sensor.UNKNOWN, 's')
        sensor.set_value(val)

    def sensors_transient_buffer_ready(self):
        """
        Is the transient buffer ready to trigger?
        :return:
        """
        sensor = self.do_sensor(
            Corr2Sensor.boolean, 'transient-buffer-ready',
            'The transient buffer is ready to be triggered.',
            Sensor.UNKNOWN, 's')
        sensor.set_value(True)

    def sensors_input_labels(self):
        """
        Update all sensors that are affected by input labels.
        :return:
        """
        mapping = self.instrument.get_input_mapping()
        sensor = self.do_sensor(
            Corr2Sensor.string, 'input-mapping',
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
                'of correlation pairs given by input label.', Sensor.UNKNOWN)
            sensor.set_value(self.instrument.baselines)

    def sensors_xeng_acc_time(self):
        """

        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.XENGINE_CROSS_PRODUCTS)
        for stream in streams:
            strmnm = stream.name
            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-accs'.format(strmnm),
                'The number of spectra that are accumulated per X-engine '
                'output.', Sensor.UNKNOWN)
            spec_acclen = (self.instrument.accumulation_len *
                           self.instrument.xeng_accumulation_len)
            sensor.set_value(spec_acclen)

            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-int-time'.format(strmnm),
                'The time, in seconds, for which the X-engines accumulate.',
                Sensor.UNKNOWN, 's')
            sensor.set_value(self.instrument.xops.get_acc_time())

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
                'Number of accumulations performed internal to the X-engine.',
                Sensor.UNKNOWN)
            sensor.set_value(self.instrument.xeng_accumulation_len)

            sensor = self.do_sensor(
                Corr2Sensor.integer,
                '{}-xeng-out-bits-per-sample'.format(strmnm),
                'X-engine output bits per sample. Per number, not complex '
                'pair. Real and imaginary parts are both this wide.',
                Sensor.UNKNOWN)
            sensor.set_value(self.instrument.xeng_outbits)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-clock-rate'.format(strmnm),
                'Target clock rate of X-engines.', Sensor.UNKNOWN, 'Hz')
            sensor.set_value(self.instrument.xeng_clk)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-bls'.format(strmnm),
                'The number of baselines produced by this correlator '
                'instrument.', Sensor.UNKNOWN)
            sensor.set_value(len(self.instrument.baselines))

        self.sensors_xeng_acc_time()

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
                # TODO - this must be per-input, not system-wide
                sensor = self.do_sensor(
                    Corr2Sensor.integer, '{}-fft0-shift'.format(pref),
                    'The FFT bitshift pattern for the <n>th FFT in the design. '
                    'n=0 is first in the RF chain (closest to source).',
                    Sensor.UNKNOWN)
                sensor.set_value(self.instrument.fft_shift)

    def sensors_feng_eq(self):
        streams = self.instrument.get_data_streams_by_type(
            data_stream.FENGINE_CHANNELISED_DATA)
        assert len(streams) == 1
        for stream in streams:
            strmnm = stream.name
            for feng in self.instrument.fops.fengines:
                pref = '{strm}-input{npt}'.format(strm=strmnm,
                                                  npt=feng.input_number)
                sensor = self.do_sensor(
                        Corr2Sensor.string, '{}-eq'.format(pref),
                        'The unitless, per-channel digital scaling factors '
                        'implemented prior to requantisation. Complex. If one '
                        'value has been applied to all channels, only one is '
                        'shown by the sensor.',
                        Sensor.UNKNOWN)
                sensor.set_value(str(feng.eq_poly))

    def sensors_feng_delays(self):
        """
        F-engine delay sensors
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
                Corr2Sensor.float, '{}-delay-set'.format(pref),
                'The last delay values set for this input.',
                Sensor.UNKNOWN)
            if feng.delay.load_time:
                sensor.set_value(feng.delay.delay)

            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-delay-delta-set'.format(pref),
                'The last delay delta values set for this input.',
                Sensor.UNKNOWN)
            if feng.delay.load_time:
                sensor.set_value(feng.delay.delay_delta)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-loadtime'.format(pref),
                'The given load time for a set of delay-tracking '
                'coefficients for this input.',
                Sensor.UNKNOWN)
            if feng.delay.load_time:
                sensor.set_value(feng.delay.load_time)

            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-phase-set'.format(pref),
                'The last phase values set for this input.',
                Sensor.UNKNOWN)
            if feng.delay.load_time:
                sensor.set_value(feng.delay.phase_offset)

            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-phase-delta-set'.format(pref),
                'The last phase delta values set for this input.',
                Sensor.UNKNOWN)
            if feng.delay.load_time:
                sensor.set_value(feng.delay.phase_offset_delta)

    def sensors_feng_streams(self):
        """
        F-engine stream sensors
        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.FENGINE_CHANNELISED_DATA)

        assert len(streams) == 1

        for stream in streams:
            strmnm = stream.name

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-feng-pkt-len'.format(strmnm),
                'Payload size of 10GbE packet exchange between F and X '
                'engines in 64 bit words. Usually equal to the number of '
                'spectra accumulated inside X engine. F-engine correlator '
                'internals.',
                Sensor.UNKNOWN)
            pkt_len = int(self.instrument.configd['fengine']['10gbe_pkt_len'])
            sensor.set_value(pkt_len)

            # TODO - per engine, not just hardcoded
            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-feng-out-bits-per-sample'
                                     ''.format(strmnm),
                'F-engine output bits per sample.',
                Sensor.UNKNOWN)
            bits = int(self.instrument.quant_format.split('.')[0])
            sensor.set_value(bits)

            # TODO - per engine, not just hardcoded
            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-center-freq'.format(strmnm),
                'The CBF center frequency of the digitised band.',
                Sensor.UNKNOWN)
            sensor.set_value(self.instrument.analogue_bandwidth / 2.0)

            # TODO - per engine, not just hardcoded
            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-chans'.format(strmnm),
                'Number of channels in the output spectrum.',
                Sensor.UNKNOWN)
            sensor.set_value(self.instrument.n_chans)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-coarse-chans'.format(strmnm),
                'Number of channels in the first PFB in a cascaded-PFB design.',
                Sensor.UNKNOWN)
            sensor.set_value(-1)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-current-coarse-chan'.format(strmnm),
                'The selected coarse channel in a cascaded-PFB design.',
                Sensor.UNKNOWN)
            sensor.set_value(-1)

            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-ddc-mix-freq'.format(strmnm),
                'The F-engine DDC mixer frequency, where used. -1 when n/a.',
                Sensor.UNKNOWN)
            sensor.set_value(-1)

        self.sensors_feng_fft_shift()
        self.sensors_feng_eq()
        self.sensors_feng_delays()

    def sensors_beng_weights(self):
        """

        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.BEAMFORMER_FREQUENCY_DOMAIN)
        for stream in streams:
            strmnm = stream.name
            beam = self.instrument.bops.beams[strmnm]
            for feng in beam.source_streams:
                pref = '{strm}-input{npt}'.format(strm=strmnm,
                                                  npt=feng.input_number)
                sensor = self.do_sensor(
                    Corr2Sensor.float, '{}-weight'.format(pref),
                    'The summing weight applied to this input on this beam.',
                    Sensor.UNKNOWN)
                sensor.set_value(beam.source_streams[feng]['weight'])

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
                'this beam.',
                Sensor.UNKNOWN)
            sensor.set_value(beam.quant_gain)

    def sensors_beng_passband(self):
        """

        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.BEAMFORMER_FREQUENCY_DOMAIN)
        for stream in streams:
            strmnm = stream.name
            beam = self.instrument.bops.beams[strmnm]
            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-bandwidth'.format(strmnm),
                'Bandwidth of selected beam passband.',
                Sensor.UNKNOWN)
            sensor.set_value(beam.bandwidth)

            sensor = self.do_sensor(
                Corr2Sensor.float, '{}-center-freq'.format(strmnm),
                'Center frequency of selected beam passband.',
                Sensor.UNKNOWN)
            sensor.set_value(beam.center_freq)

            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-n-chans'.format(strmnm),
                'Number of channels in selected beam passband.',
                Sensor.UNKNOWN)
            sensor.set_value(beam.active_channels())

    def sensors_beng_streams(self):
        """
        B-engine stream sensors
        :return:
        """
        streams = self.instrument.get_data_streams_by_type(
            data_stream.BEAMFORMER_FREQUENCY_DOMAIN)

        for stream in streams:
            strmnm = stream.name
            beam = self.instrument.bops.beams[strmnm]

            # TODO - where is this found?
            sensor = self.do_sensor(
                Corr2Sensor.integer, '{}-beng-out-bits-per-sample'
                                     ''.format(strmnm),
                'B-engine output bits per sample.',
                Sensor.UNKNOWN)
            sensor.set_value(16)

        self.sensors_beng_passband()
        self.sensors_beng_weights()
        self.sensors_beng_gains()

    def setup_mainloop_sensors(self):
        """
        Set up compound sensors to be reported to CAM from the main katcp servlet
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

        # sensors from list @ https://docs.google.com/spreadsheets/d/12AWtHXPXmkT5e_VT-H__zHjV8_Cba0Y7iMkRnj2qfS8/edit#gid=0

        self.sensors_tengbe_interfacing()

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
            name='n-chans',
            description='The number of frequency channels in an integration.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.n_chans)

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
            name='ticks-between-spectra',
            description='Number of sample ticks between spectra.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.n_chans * 2)

        sensor = Corr2Sensor.integer(
            name='f-per-fpga', description='The number of F-engines per host.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.f_per_fpga)

        sensor = Corr2Sensor.integer(
            name='x-per-fpga', description='The number of X-engines per host.',
            initial_status=Sensor.UNKNOWN, manager=self)
        self.sensor_create(sensor)
        sensor.set_value(self.instrument.x_per_fpga)

        sensor = Corr2Sensor.integer(
            name='b-per-fpga', description='The number of B-engines per host.',
            initial_status=Sensor.UNKNOWN, manager=self)
        if self.instrument.found_beamformer:
            sensor.set_value(self.instrument.bops.beng_per_host)
        else:
            sensor.set_value(-1)

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
        n_xeng = len(self.instrument.xhosts)
        chans_per_x = n_chans / n_xeng
        for _x in self.instrument.xhosts:
            bid = self.instrument.xops.board_ids[_x.host]
            sensor = Corr2Sensor.string(
                name='xeng-host{}-rx-fchan-range'.format(bid),
                description='The range of frequency channels processed '
                            'by {host}:{brd}.'.format(host=_x.host, brd=bid),
                initial_status=Sensor.UNKNOWN,
                manager=self)
            sensor.set_value('({start},{end})'.format(
                start=bid*chans_per_x, end=(bid+1)*chans_per_x))

        hosts = [('fengine', self.instrument.fhosts[0]),
                 ('xengine', self.instrument.xhosts[0])]
        for _htype, _h in hosts:
            if 'git' in _h.rcs_info:
                filectr = 0
                for gitfile, gitparams in _h.rcs_info['git'].items():
                    namepref = 'git-' + _htype + '-' + str(filectr)
                    for param, value in gitparams.items():
                        sensname = namepref + '-' + param
                        sensname = sensname.replace('_', '-')
                        sensor = Corr2Sensor.string(
                            name=sensname,
                            description='Git info: %s' % sensname,
                            initial_status=Sensor.UNKNOWN,
                            manager=self)
                        sensor.set_value(str(value))
                    filectr += 1

        self.sensors_xeng_streams()

        self.sensors_feng_streams()

        self.sensors_beng_streams()

# end
