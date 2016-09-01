import logging
import time

from katcp import Sensor, Message

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
        if self.manager:
            self.manager.sensor_create(self)

    def set(self, timestamp, status, value):
        """

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
        self.metasensors = {}

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

    def sensor_set(self, sensor, status, value, timestamp=None):
        """

        :param sensor: the sensor, or sensor name, to set
        :param timestamp:
        :param status:
        :param value:
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

    def _kcs_sensor_set(self, sensor):
        """
        Generate #sensor-status informs to update sensors"

        #sensor-status timestamp 1 sensor-name status value

        :param sensor: A katcp.Sensor object
        :return:
        """
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
        assert self.kcs_sensors
        descr = sensor.description.replace(' ', '\_')
        screate_inform = Message.inform('sensor-list',
                                        sensor.name, descr,
                                        sensor.units, sensor.type)
        self.katcp_server.mass_inform(screate_inform)
        self._kcs_sensor_set(sensor)


def create_source_delay_sensors(src):
    src_name = src.name.replace('_', '-')
    sensor = Corr2Sensor.string(
        name='%s-delay-set' % src_name,
        description='Source %s delay values last set' % src_name,
        initial_status=Corr2Sensor.UNKNOWN,
        default='', manager=src.sensor_manager)
    sensor.set_value('%.5f,%.5f' % (src.delay.delay, src.delay.delay_delta))

    sensor = Corr2Sensor.string(
        name='%s-phase-set' % src_name,
        description='Source %s phase values last set' % src_name,
        initial_status=Corr2Sensor.UNKNOWN,
        default='', manager=src.sensor_manager)
    sensor.set_value('%.5f,%.5f' % (src.delay.phase_offset,
                                    src.delay.phase_offset_delta))

    sensor = Corr2Sensor.float(
        name='%s-loadtime' % src_name,
        description='Source %s delay tracking load time' % src_name,
        initial_status=Corr2Sensor.UNKNOWN,
        default=-1, manager=src.sensor_manager)
    sensor.set_value(src.delay.load_time)


def setup_mainloop_sensors(sensor_manager):
    """
    Set up compound sensors to be reported to CAM from the main katcp servlet
    :param sensor_manager: A SensorManager instance
    :return:
    """
    # # Set up a 1-worker pool per host to serialise interactions with each host
    # host_executors = {
    #     host.host: futures.ThreadPoolExecutor(max_workers=1)
    #     for host in instrument.fhosts + instrument.xhosts
    # }
    # general_executor = futures.ThreadPoolExecutor(max_workers=1)

    if not sensor_manager.instrument.initialised():
        raise RuntimeError('Cannot set up sensors until instrument is '
                           'initialised.')

    ioloop = getattr(sensor_manager.instrument, 'ioloop', None)
    if not ioloop:
        ioloop = getattr(sensor_manager.katcp_server, 'ioloop', None)
    if not ioloop:
        raise RuntimeError('IOLoop-containing katcp version required. Can go '
                           'no further.')

    sensor_manager.sensors_clear()

    # sensors from list @ https://docs.google.com/document/d/1TtXdHVTL6ns8vOCUNKZU2pn4y6Fnocj83YiJpbVHOKU/edit?ts=57751f06

    # synch epoch - CAN CHANGE
    sensor = Corr2Sensor.float(
        name='synch-epoch', description='Instrument synch epoch',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.get_synch_time())

    # scale_factor_timestamp
    sensor = Corr2Sensor.float(
        name='scale-factor-timestamp',
        description='Factor to convert a system time to unix seconds',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.get_scale_factor())

    # f-engine host-specific things
    num_inputs = 0
    for _f in sensor_manager.instrument.fhosts:
        # input labels - CAN CHANGE
        rv = [dsrc.name for dsrc in _f.data_sources]
        num_inputs += len(rv)
        sensor = Corr2Sensor.string(
            name='%s-input-mapping' % _f.host,
            description='F-engine host %s input mapping' % _f.host,
            initial_status=Sensor.NOMINAL,
            default=str(rv), manager=sensor_manager)

        # last delays and phases set - CAN CHANGE
        for src in _f.data_sources:
            src.sensor_manager = sensor_manager
            create_source_delay_sensors(src)

    # n_inputs
    sensor = Corr2Sensor.integer(
        name='n-inputs', description='Number of inputs to the instrument',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(num_inputs)

    # n_chans
    sensor = Corr2Sensor.integer(
        name='n-chans', description='Number of frequency channels',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.n_chans)

    # n_xengs
    sensor = Corr2Sensor.integer(
        name='n-xengines', description='Number of x-engine boards',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(len(sensor_manager.instrument.xhosts))

    # n_fengs
    sensor = Corr2Sensor.integer(
        name='n-fengines', description='Number of f-engine boards',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(len(sensor_manager.instrument.fhosts))

    # x_per_fpga
    sensor = Corr2Sensor.integer(
        name='x-per-fpga', description='Number of x-engines per FPGA host',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.x_per_fpga)

    # f_per_fpga
    sensor = Corr2Sensor.integer(
        name='f-per-fpga', description='Number of f-engines per FPGA host',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.f_per_fpga)

    # center freq
    sensor = Corr2Sensor.float(
        name='center-frequency', description='The on-sky center frequency',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.true_cf)

    # bandwidth
    sensor = Corr2Sensor.float(
        name='bandwidth', description='The total bandwidth digitised',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.analogue_bandwidth)

    # n_accs - CAN CHANGE
    sensor = Corr2Sensor.integer(
        name='n-accs',
        description='Number of accumulations to perform in the VACC',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.accumulation_len)

    # integration time - CAN CHANGE
    sensor = Corr2Sensor.float(
        name='integration-time',
        description='The total time for which the x-engines integrate',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.xops.get_acc_time())

    # xeng_acc_len
    sensor = Corr2Sensor.integer(
        name='xeng-acc-len',
        description='Number of accumulations performed '
                    'internal to the x-engine',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.xeng_accumulation_len)

    # requant_bits
    sensor = Corr2Sensor.string(
        name='requant-bits', description='The f-engine quantiser output format',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.quant_format)

    # stream destination sensors - CAN CHANGE
    for stream in sensor_manager.instrument.data_streams.values():
        sensor = Corr2Sensor.string(
            name='%s-destination' % stream.name,
            description='The output IP and port of the '
                        'data stream %s' % stream.name,
            initial_status=Sensor.UNKNOWN, manager=sensor_manager)
        sensor.set_value(str(stream.destination))
        sensor = Corr2Sensor.string(
            name='%s-meta-destination' % stream.name,
            description='The output IP and port of the '
                        'metadata for stream %s' % stream.name,
            initial_status=Sensor.UNKNOWN, manager=sensor_manager)
        sensor.set_value(str(stream.meta_destination))

    # beamformer weights and gains - CAN CHANGE
    beam_weights = sensor_manager.instrument.bops.get_beam_weights()
    for beam, weights in beam_weights.items():
        sensor = Corr2Sensor.string(
            name='{beam}-weights'.format(beam=beam),
            description='Beam {beam} weights'.format(beam=beam),
            initial_status=Sensor.UNKNOWN, manager=sensor_manager)
        sensor.set_value(str(weights))
    beam_gains = sensor_manager.instrument.bops.get_beam_quant_gains()
    for beam, gain in beam_gains.items():
        sensor = Corr2Sensor.float(
            name='{beam}-quantiser-gains'.format(beam=beam),
            description='Beam {beam} quantiser gains'.format(beam=beam),
            initial_status=Sensor.UNKNOWN, manager=sensor_manager)
        sensor.set_value(gain)

    # ddc_mix_freq
    sensor = Corr2Sensor.float(
        name='ddc-mix-frequency',
        description='The f-engine DDC mixer frequency',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    # sensor.set_value(sensor_manager.instrument.xops.get_acc_time())

    # adc_bits
    sensor = Corr2Sensor.integer(
        name='adc-bits', description='ADC sample bitwidth',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.adc_bitwidth)

    # xeng_out_bits_per_sample
    sensor = Corr2Sensor.integer(
        name='xeng-out-bits-per-sample',
        description='X-engine output bits per sample',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.xeng_outbits)

    # beng_out_bits_per_sample
    if sensor_manager.instrument.found_beamformer:
        sensor = Corr2Sensor.integer(
            name='beng-out-bits-per-sample',
            description='B-engine output bits per sample',
            initial_status=Sensor.UNKNOWN, manager=sensor_manager)
        sensor.set_value(sensor_manager.instrument.beng_outbits)

    # bls_ordering - CAN CHANGE
    sensor = Corr2Sensor.string(
        name='baseline-ordering',
        description='X-engine output baseline ordering',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(str(sensor_manager.instrument.baselines))

    # max_adc_sample_rate
    sensor = Corr2Sensor.float(
        name='adc-sample-rate',
        description='The sample rate of the ADC', unit='Hz',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(sensor_manager.instrument.sample_rate_hz)

    # is the transient buffer ready?
    sensor = Corr2Sensor.boolean(
        name='transient-buffer-ready',
        description='The transient buffer is ready to trigger.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(True)

    # x-engine fchan range
    n_chans = sensor_manager.instrument.n_chans
    n_xeng = len(sensor_manager.instrument.xhosts)
    chans_per_x = n_chans / n_xeng
    for _x in sensor_manager.instrument.xhosts:
        bid = _x.registers.board_id.read()['data']['reg']
        sensor = Corr2Sensor.string(
            name='%s-rx-fchan-range' % _x.host,
            description='The frequency channels processed '
                        'by {host}.'.format(host=_x.host),
            initial_status=Sensor.UNKNOWN,
            manager=sensor_manager)
        sensor.set_value('({start},{end})'.format(start=bid*chans_per_x,
                                                  end=(bid+1)*chans_per_x))

    # feng_pkt_len (feng_heap_len?!)

    # per host tengbe sensors
    all_hosts = sensor_manager.instrument.fhosts + \
                sensor_manager.instrument.xhosts
    for _h in all_hosts:
        for tengbe in _h.tengbes:
            sensor = Corr2Sensor.string(
                name='%s-%s-ip' % (_h.host, tengbe.name),
                description='%s %s configured IP address' % (
                    _h.host, tengbe.name),
                initial_status=Sensor.UNKNOWN,
                manager=sensor_manager)
            sensor.set_value(str(tengbe.ip_address))
            sensor = Corr2Sensor.string(
                name='%s-%s-mac' % (_h.host, tengbe.name),
                description='%s %s configured MAC address' % (
                    _h.host, tengbe.name),
                initial_status=Sensor.UNKNOWN,
                manager=sensor_manager)
            sensor.set_value(str(tengbe.mac))
            sensor = Corr2Sensor.string(
                name='%s-%s-port' % (_h.host, tengbe.name),
                description='%s %s configured port' % (
                    _h.host, tengbe.name),
                initial_status=Sensor.UNKNOWN,
                manager=sensor_manager)
            sensor.set_value(str(tengbe.port))
            sensor = Corr2Sensor.string(
                name='%s-%s-multicast-subscriptions' % (_h.host, tengbe.name),
                description='%s %s is subscribed to these multicast '
                            'addresses' % (_h.host, tengbe.name),
                initial_status=Sensor.UNKNOWN,
                manager=sensor_manager)
            sensor.set_value(str(tengbe.multicast_subscriptions))

    # git information, if we have any
    hosts = [('fengine', sensor_manager.instrument.fhosts[0]),
             ('xengine', sensor_manager.instrument.xhosts[0])]
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
                        manager=sensor_manager)
                    sensor.set_value(str(value))
                filectr += 1

# end
