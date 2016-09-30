import numpy

from sensors import Corr2Sensor

SPEAD_ADDRSIZE = 48


# def create_sensor_from_meta(sensor_manager, **kwargs):
#     sid = kwargs['id']
#     sname = kwargs['name'].replace('_', '-')
#     sname = 'speadmeta-0x{id:04x}-{name}'.format(id=sid, name=sname)
#     sensor = Corr2Sensor.string(
#         name=sname,
#         description=kwargs['description'],
#         initial_status=Corr2Sensor.UNKNOWN, manager=sensor_manager)
#     return sensor


class SpeadOperations(object):
    def __init__(self, corr_obj):
        """
        :param corr_obj: the FxCorrelator object with which we interact
        :return:
        """
        self.corr = corr_obj
        self.logger = self.corr.logger

    def add_item(self, sig, stx=None, **kwargs):
        """
        Add an item to a SPEAD ItemGroup, send if SPEAD TX provided
        :param sig: SPEAD ItemGroup
        :param stx: SPEAD transmitter
        :param kwargs:
        :return:
        """
        sid = kwargs['id']
        # spead2 metadata create (and send)
        if sig is not None:
            sig.add_item(**kwargs)
        if stx is not None:
            stx.send_heap(sig.get_heap())
        # # add or update a sensor
        # if self.corr.sensor_manager:
        #     # does the sensor exist?
        #     try:
        #         sensor = self.corr.sensor_manager.metasensors[sid]
        #     except KeyError:
        #         sensor = create_sensor_from_meta(self.corr.sensor_manager,
        #                                          **kwargs)
        #         self.corr.sensor_manager.metasensors[kwargs['id']] = sensor
        #     if 'value' in kwargs:
        #         svalue = str(kwargs['value'])
        #         sensor.set_value(svalue)

    def update_metadata(self, ids):
        """
        Update an ID and trigger those data sources that contain those IDs
        to send their metadata
        :param ids: a list of ids to update
        :return:
        """
        try:
            iter(ids)
        except TypeError:
            ids = [ids]
        # loop through known streams and match spead IDs to those streams
        for stream in self.corr.data_streams:
            try:
                if stream.meta_ig:
                    changes = False
                    for speadid in ids:
                        idfunc = getattr(self, 'item_0x%04x' % speadid)
                        if speadid in stream.meta_ig.ids():
                            idfunc(stream.meta_ig)
                            changes = True
                    if changes:
                        stream.meta_transmit()
            except AttributeError as e:
                # DataStreams don't necessarily have an associated SPEAD stream
                pass

    def item_0x1007(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='adc_sample_rate', id=0x1007,
            description='The expected ADC sample rate (samples per '
                        'second) of incoming data.',
            shape=[], format=[('u', 64)],
            value=self.corr.sample_rate_hz)

    # 0x1008 - fxcorrelator_xengops.py

    # 0x1009 - fxcorrelator_xengops.py

    def item_0x100a(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='n_ants', id=0x100A,
            description='The number of antennas in the system.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.n_antennas)

    # 0x100b - fxcorrelator_xengops.py

    # 0x100c - fxcorrelator_xengops.py

    # 0x100d - DEPRECATED

    def item_0x100e(self, sig, stx=None):
        metalist = self.corr.get_input_mapping()
        metalist = numpy.array(metalist)
        self.add_item(
            sig=sig, stx=stx,
            name='input_labelling', id=0x100E,
            description='input labels and numbers',
            shape=metalist.shape,
            dtype=metalist.dtype,
            value=metalist)

    # 0x100f - beam.py

    # 0x1011 - fxcorrelator_xengops.py

    # 0x1012 - UNUSED

    def item_0x1013(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='bandwidth', id=0x1013,
            description='The analogue bandwidth of the digitally processed '
                        'signal, in Hz.',
            shape=[], format=[('f', 64)],
            value=self.corr.analogue_bandwidth)

    # 0x1014 - UNUSED

    def item_0x1015(self, sig, stx=None):
        spec_acclen = (self.corr.accumulation_len *
                       self.corr.xeng_accumulation_len)
        self.add_item(
            sig=sig, stx=stx,
            name='n_accs', id=0x1015,
            description='The number of spectra that are accumulated '
                        'per X-engine dump.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=spec_acclen)

    def item_0x1016(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='int_time', id=0x1016,
            description='The time per integration, in seconds.',
            shape=[], format=[('f', 64)],
            value=self.corr.xops.get_acc_time())

    def item_0x1017(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='coarse_chans', id=0x1017,
            description='Number of channels in the first PFB in a cascaded-PFB'
                        ' design.',
            shape=[], format=[('f', 64)],
            value=-1)

    def item_0x1018(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='current_coarse_chan', id=0x1018,
            description='The currently selected coarse channel in a cascaded-'
                        'PFB design.',
            shape=[], format=[('f', 64)],
            value=-1)

    # 0x1019 - UNUSED

    # 0x101a - UNUSED

    # 0x101b - UNUSED

    def item_0x101c(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='fft_shift_fine', id=0x101C,
            description='The FFT bitshift pattern for the second (fine) '
                        'PFB in a cascaded-PFB design.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=0)

    def item_0x101d(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='fft_shift_coarse', id=0x101D,
            description='The FFT bitshift pattern for the first (coarse) '
                        'PFB in a cascaded-PFB design.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=0)

    def item_0x101e(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='fft_shift', id=0x101E,
            description='The FFT bitshift pattern. F-engine '
                        'correlator internals.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.fft_shift)

    # 0x101F - fxcorrelator_xengops.py

    def item_0x1020(self, sig, stx=None):
        quant_str = self.corr.configd['fengine']['quant_format']
        quant_bits = int(quant_str.split('.')[0])
        self.add_item(
            sig=sig, stx=stx,
            name='requant_bits', id=0x1020,
            description='Number of bits after requantisation in the '
                        'F engines (post FFT and any phasing stages).',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=quant_bits)

    # 0x1021 - fxcorrelator_xengops.py

    # 0x1022 - fxcorrelator_xengops.py

    # 0x1023 - fxcorrelator_xengops.py

    # 0x1024 - fxcorrelator_xengops.py

    # 0x1025 - fxcorrelator_xengops.py

    # 0x1026 - fxcorrelator_xengops.py

    def item_0x1027(self, sig, stx=None):
        val = self.corr.synchronisation_epoch
        val = 0 if val < 0 else val
        self.add_item(
            sig=sig, stx=stx,
            name='sync_time', id=0x1027,
            description='The time at which the digitisers were synchronised. '
                        'Seconds since the Unix Epoch.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=val)

    # 0x1040 - fxcorrelator_xengops.py

    # 0x1041 - fxcorrelator_xengops.py

    # 0x1042 - DEPRECATED

    # 0x1043 - fxcorrelator_xengops.py

    # 0x1044 - DEPRECATED

    def item_0x1045(self, sig, stx=None):
        sample_bits = int(self.corr.configd['fengine']['sample_bits'])
        self.add_item(
            sig=sig, stx=stx,
            name='adc_bits', id=0x1045,
            description='How many bits per ADC sample.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=sample_bits)

    def item_0x1046(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='scale_factor_timestamp', id=0x1046,
            description='Timestamp scaling factor. Divide the SPEAD '
                        'data packet timestamp by this number to get '
                        'back to seconds since last sync.',
            shape=[], format=[('f', 64)],
            value=self.corr.get_scale_factor())

    # 0x1047 - beam.py

    # 0x1048 - fxcorrelator_xengops.py

    # 0x1049 - fxcorrelator_xengops.py

    def item_0x104a(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='ticks_between_spectra', id=0x104A,
            description='Number of sample ticks between spectra.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.n_chans * 2)

    def item_0x104b(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='fengine_chans', id=0x104B,
            description='Number of channels in the F-engine spectra.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.n_chans)

    # 0x1050 - beam.py

    # 0x1200 - DEPRECATED

    def item_0x1400(self, sig, stx=None):
        all_eqs = self.corr.fops.eq_get()
        for feng in self.corr.fops.fengines:
            _srcname = feng.name
            _srcnum = feng.input_number
            eq = [[numpy.real(eq_coeff), numpy.imag(eq_coeff)]
                  for eq_coeff in all_eqs[_srcname]]
            eq = numpy.array(eq, dtype=numpy.int32)
            self.add_item(
                sig=sig, stx=stx,
                name='eq_coef_%s' % _srcname, id=0x1400 + _srcnum,
                description='The unitless per-channel digital scaling '
                            'factors implemented prior to requantisation, '
                            'post-FFT, for input %s. Complex number '
                            'real,imag 32 bit integers.' % _srcname,
                shape=eq.shape,
                dtype=eq.dtype,
                value=eq)

    def item_0x1600(self, sig, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='timestamp', id=0x1600,
            description='Timestamp of start of this integration. uint '
                        'counting multiples of ADC samples since last sync '
                        '(sync_time, id=0x1027). Divide this number by '
                        'timestamp_scale (id=0x1046) to get back to seconds '
                        'since last sync when this integration was actually '
                        'started.',
            shape=[],
            format=[('u', SPEAD_ADDRSIZE)])

    # 0x1800 - fxcorrelator_xengops.py

    # 0x2000 - beam.py

    # spead_ig.add_item(name='incoherent_sum', id=0x3000,
    #                        description='',
    #                        shape=[], format=[('u', 32)],
    #                        value=)

    # spead_ig.add_item(name='n_inputs', id=0x3100,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='digitiser_id', id=0x3101,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='digitiser_status', id=0x3102,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='pld_len', id=0x3103,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='raw_data_MyAntStr', id=0x3300+inputN,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='Reserved for SP-CAM meta-data', id=0x7000-0x7fff,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='feng_id', id=0xf101,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='feng_status', id=0xf102,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='frequency', id=0xf103,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='raw_freq_MyAntStr', id=0xf300+inputN,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)

    # spead_ig.add_item(name='bf_MyBeamName', id=0xb000+beamN,
    #                        description='',
    #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #                        value=)
