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
        name='input{0}-delay-set'.format(src.source_number),
        description='Source %s delay values last set' % src_name,
        initial_status=Corr2Sensor.UNKNOWN,
        default='', manager=src.sensor_manager)
    sensor.set_value('%.5f,%.5f' % (src.delay.delay, src.delay.delay_delta))

    sensor = Corr2Sensor.string(
        name='input{0}-phase-set'.format(src.source_number),
        description='Source %s phase values last set' % src_name,
        initial_status=Corr2Sensor.UNKNOWN,
        default='', manager=src.sensor_manager)
    sensor.set_value('%.5f,%.5f' % (src.delay.phase_offset,
                                    src.delay.phase_offset_delta))

    sensor = Corr2Sensor.float(
        name='input{0}-loadtime'.format(src.source_number),
        description='Source %s delay tracking load time' % src_name,
        initial_status=Corr2Sensor.UNKNOWN,
        default=-1, manager=src.sensor_manager)
    if src.delay.load_time is not None:
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

    instr = sensor_manager.instrument

    # sensors from list @ https://docs.google.com/document/d/1TtXdHVTL6ns8vOCUNKZU2pn4y6Fnocj83YiJpbVHOKU/edit?ts=57751f06

    # board-to-engine mapping - TODO changing on swapped board?
    # fengine
    mapping = instr.fops.fengine_to_host_mapping()
    sensor = Corr2Sensor.string(
            name='host-fengine-mapping',
            description='F-engine to host mapping',
            initial_status=Sensor.NOMINAL,
            default=str(mapping), manager=sensor_manager)
    # xengine
    mapping = instr.xops.xengine_to_host_mapping()
    sensor = Corr2Sensor.string(
            name='host-xengine-mapping',
            description='X-engine to host mapping',
            initial_status=Sensor.NOMINAL,
            default=str(mapping), manager=sensor_manager)
    # bengine
    # TODO

    # input labels
    mapping = instr.get_labels()
    sensor = Corr2Sensor.string(
            name='input-mapping',
            description='Input labels',
            initial_status=Sensor.NOMINAL,
            default=str(mapping), manager=sensor_manager)

    # F-engine host-specific things
    num_inputs = 0
    for _f in instr.fhosts:
        # input labels - CAN CHANGE
        rv = [dsrc.name for dsrc in _f.data_sources]
        num_inputs += len(rv)
        sensor = Corr2Sensor.string(
            name='%s-input-mapping' % _f.host,
            description='F-engine host %s to input mapping' % _f.host,
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

    # n_xengs
    sensor = Corr2Sensor.integer(
        name='n-xeng-hosts', description='Number of X-engine boards',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(len(instr.xhosts))

    # n_fengs
    sensor = Corr2Sensor.integer(
        name='n-feng-hosts', description='Number of F-engine boards',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(len(instr.fhosts))

    # stream destination sensors - CAN CHANGE
    for stream in instr.data_streams.values():
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
    if instr.found_beamformer:
        beam_weights = instr.bops.get_beam_weights()
        for beam_name, weights in beam_weights.items():
            beam = instr.bops.get_beam_by_name(beam_name)
            sensor = Corr2Sensor.string(
                name='beam{idx}-weights'.format(idx=beam.index),
                description='Beam{idx} {beam} weights.'.format(
                    idx=beam.index, beam=beam_name),
                initial_status=Sensor.UNKNOWN, manager=sensor_manager)
            sensor.set_value(str(weights))
        beam_gains = instr.bops.get_beam_quant_gains()
        for beam_name, gain in beam_gains.items():
            beam = instr.bops.get_beam_by_name(beam_name)
            sensor = Corr2Sensor.float(
                name='beam{idx}-quantiser-gain'.format(idx=beam.index),
                description='Beam{idx} {beam} quantiser gain.'.format(
                    idx=beam.index, beam=beam_name),
                initial_status=Sensor.UNKNOWN, manager=sensor_manager)
            sensor.set_value(gain)

    # is the transient buffer ready?
    sensor = Corr2Sensor.boolean(
        name='transient-buffer-ready',
        description='The transient buffer is ready to trigger.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(True)

    # X-engine fchan range
    n_chans = instr.n_chans
    n_xeng = len(instr.xhosts)
    chans_per_x = n_chans / n_xeng
    for _x in instr.xhosts:
        bid = _x.registers.board_id.read()['data']['reg']
        sensor = Corr2Sensor.string(
            name='xeng_host{}-rx-fchan-range'.format(bid),
            description='The frequency channels processed '
                        'by {host}:{brd}.'.format(host=_x.host, brd=bid),
            initial_status=Sensor.UNKNOWN,
            manager=sensor_manager)
        sensor.set_value('({start},{end})'.format(start=bid*chans_per_x,
                                                  end=(bid+1)*chans_per_x))
    # SPEAD 0x1007
    sensor = Corr2Sensor.float(
        name='adc-sample-rate',
        description='The sample rate of the ADC', unit='Hz',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.sample_rate_hz)

    # SPEAD 0x1008
    sensor = Corr2Sensor.integer(
        name='n-bls',
        description='Number of baselines in the data stream.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(len(instr.baselines))

    # SPEAD 0x1009
    sensor = Corr2Sensor.integer(
        name='n-chans',
        description='Number of frequency channels in an integration.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.n_chans)

    # SPEAD 0x100a
    sensor = Corr2Sensor.integer(
        name='n-ants',
        description='The number of antennas in the system.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.n_antennas)

    # SPEAD 0x100b
    sensor = Corr2Sensor.integer(
        name='n-xengs',
        description='The number of X-engines in the system.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(len(instr.xhosts) * instr.x_per_fpga)

    # SPEAD 0x100c - bls_ordering
    sensor = Corr2Sensor.string(
        name='baseline-ordering',
        description='X-engine output baseline ordering',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.baselines)

    # SPEAD 0x100d - DEPRECATED

    # SPEAD 0x100e - see above input labels

    # SPEAD 0x100f
    sensor = Corr2Sensor.integer(
        name='n-bengs',
        description='The total number of B engines in the system.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    if instr.found_beamformer:
        n_bengs = instr.bops.beng_per_host * len(instr.bops.hosts)
    else:
        n_bengs = 0
    sensor.set_value(n_bengs)

    # SPEAD 0x1010?

    # SPEAD 0x1011
    sensor = Corr2Sensor.float(
        name='center-frequency',
        description='The on-sky center frequency.', unit='Hz',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.true_cf)

    # 0x1012 - UNUSED

    # SPEAD 0x1013
    sensor = Corr2Sensor.float(
        name='bandwidth',
        description='The analogue bandwidth of the digitally processed '
                    'signal.', unit='Hz',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.analogue_bandwidth)

    # 0x1014 - UNUSED

    # SPEAD 0x1015 - n_accs - CAN CHANGE
    spec_acclen = (instr.accumulation_len * instr.xeng_accumulation_len)
    sensor = Corr2Sensor.integer(
        name='n-accs',
        description='The number of spectra that are accumulated per '
                    'X-engine dump',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(spec_acclen)

    # SPEAD 0x1016 - integration time - CAN CHANGE
    sensor = Corr2Sensor.float(
        name='integration-time',
        description='The total time for which the X-engines integrate.',
        unit='s',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.xops.get_acc_time())

    # SPEAD 0x1017
    sensor = Corr2Sensor.integer(
        name='coarse-chans',
        description='Number of channels in the first PFB in a '
                    'cascaded-PFB design.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(-1)

    # SPEAD 0x1018
    sensor = Corr2Sensor.integer(
        name='current-coarse-chan',
        description='The currently selected coarse channel in a '
                    'cascaded-PFB design.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(-1)

    # 0x1019 - UNUSED

    # 0x101a - UNUSED

    # 0x101b - UNUSED

    # SPEAD 0x101c
    sensor = Corr2Sensor.integer(
        name='fft-shift-fine',
        description='The FFT bitshift pattern for the second (fine) '
                    'PFB in a cascaded-PFB design.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(-1)

    # SPEAD 0x101d
    sensor = Corr2Sensor.integer(
        name='fft-shift-coarse',
        description='The FFT bitshift pattern for the first (coarse) '
                    'PFB in a cascaded-PFB design.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(-1)

    # SPEAD 0x101e - CAN CHANGE
    sensor = Corr2Sensor.integer(
        name='fft-shift',
        description='The FFT bitshift pattern in a single-PFB design.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.fft_shift)

    # SPEAD 0x101f
    sensor = Corr2Sensor.integer(
        name='xeng-acc-len',
        description='Number of accumulations performed '
                    'internal to the X-engine',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.xeng_accumulation_len)

    # SPEAD 0x1020
    sensor = Corr2Sensor.string(
        name='requant-bits',
        description='The F-engine quantiser output format.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.quant_format)

    # SPEAD 0x1021
    pkt_len = int(instr.configd['fengine']['10gbe_pkt_len'])
    sensor = Corr2Sensor.integer(
        name='feng-pkt-len',
        description='Payload size of 10GbE packet exchange between F and X '
                    'engines in 64 bit words. Usually equal to the number of '
                    'spectra accumulated inside X engine. F-engine '
                    'correlator internals.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(pkt_len)

    # SPEAD 0x1022
    # see above for stream destinations

    # SPEAD 0x1023
    port = int(instr.configd['fengine']['10gbe_port'])
    sensor = Corr2Sensor.integer(
        name='feng-udp-port',
        description='Port for F-engines 10Gbe links in the system.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(port)

    # SPEAD 0x1024
    # see above for stream destinations

    # SPEAD 0x1025
    sensor = Corr2Sensor.string(
        name='feng-start-ip',
        description='Start IP address for F-engines in the system.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.configd['fengine']['10gbe_start_ip'])

    # SPEAD 0x1026
    sensor = Corr2Sensor.integer(
        name='xeng-rate',
        description='Target clock rate of X-engines.',
        unit='Hz',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.xeng_clk)

    # SPEAD 0x1027
    val = instr.get_synch_time()
    val = 0 if val < 0 else val
    sensor = Corr2Sensor.integer(
        name='sync-time',
        description='The time at which the digitisers were synchronised. '
                    'Seconds since the Unix Epoch.',
        unit='s',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(val)

    # SPEAD 0x1040 - ????
    # TODO

    # SPEAD 0x1041
    sensor = Corr2Sensor.integer(
        name='x-per-fpga', description='Number of X-engines per FPGA host',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.x_per_fpga)

    # 0x1042 - DEPRECATED

    # SPEAD 0x1043
    sensor = Corr2Sensor.float(
        name='ddc-mix-frequency',
        description='The F-engine DDC mixer frequency.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(-1)

    # 0x1044 - DEPRECATED

    # SPEAD 0x1045
    sensor = Corr2Sensor.integer(
        name='adc-bits', description='ADC sample bitwidth.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.adc_bitwidth)

    # SPEAD 0x1046
    sensor = Corr2Sensor.float(
        name='scale-factor-timestamp',
        description='Factor by which to divide system timestamps to '
                    'convert to unix seconds.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.get_scale_factor())

    # SPEAD 0x1047
    sensor = Corr2Sensor.integer(
        name='b-per-fpga',
        description='The number of B-engines per fpga.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    if instr.found_beamformer:
        sensor.set_value(instr.bops.beng_per_host)
    else:
        sensor.set_value(-1)

    # SPEAD 0x1048
    sensor = Corr2Sensor.integer(
        name='xeng-out-bits-per-sample',
        description='X-engine output bits per sample.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.xeng_outbits)

    # SPEAD 0x1049
    sensor = Corr2Sensor.integer(
        name='f-per-fpga', description='Number of F-engines per FPGA host.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.f_per_fpga)

    # SPEAD 0x104a
    sensor = Corr2Sensor.integer(
        name='ticks-between-spectra',
        description='Number of sample ticks between spectra.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.n_chans * 2)

    # SPEAD 0x104b
    sensor = Corr2Sensor.integer(
        name='fengine-chans',
        description='Number of channels in the F-engine spectra.',
        initial_status=Sensor.UNKNOWN, manager=sensor_manager)
    sensor.set_value(instr.n_chans)

    # SPEAD 0x1050
    if instr.found_beamformer:
        sensor = Corr2Sensor.integer(
            name='beng-out-bits-per-sample',
            description='B-engine output bits per sample.',
            initial_status=Sensor.UNKNOWN, manager=sensor_manager)
        sensor.set_value(instr.beng_outbits)

    # 0x1200 - DEPRECATED

    # SPEAD 0x1400 - per source eqs - can CHANGE!!
    all_eqs = instr.fops.eq_get()
    for source in instr.fengine_sources.values():
        _srcname = source.name
        _srcnum = source.source_number
        sensor = Corr2Sensor.string(
            name='feng{num}-eq'.format(num=_srcnum),
            description='The unitless per-channel digital scaling factors '
                        'implemented prior to requantisation, post-FFT, '
                        'for input %s. Complex number real,imag 32-bit '
                        'integers.' % _srcnum,
            initial_status=Sensor.UNKNOWN, manager=sensor_manager)
        sensor.set_value(all_eqs[_srcname])

    # per host tengbe sensors
    all_hosts = instr.fhosts + \
                instr.xhosts
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
    hosts = [('fengine', instr.fhosts[0]),
             ('xengine', instr.xhosts[0])]
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
