import numpy

SPEAD_ADDRSIZE = 48


def add_item(sig, stx=None, **kwargs):
    """
    Add an item to a SPEAD ItemGroup, send if SPEAD TX provided
    :param sig: SPEAD ItemGroup
    :param stx: SPEAD transmitter
    :param kwargs:
    :return:
    """
    sig.add_item(**kwargs)
    if stx:
        stx.send_heap(sig.get_heap())


class SpeadOperations(object):
    def __init__(self, corr_obj):
        """
        :param corr_obj: the FxCorrelator object with which we interact
        :return:
        """
        self.corr = corr_obj
        self.logger = self.corr.logger

    def update_metadata(self, ids):
        """
        Update an ID and trigger those data sources that contain those IDs
        to send their metadata
        :param ids: a list of ids to update
        :return:
        """
        for name, product in self.corr.data_products.items():
            changes = False
            for speadid in ids:
                idfunc = getattr(self, 'item_0x%x' % speadid)
                if speadid in product.meta_ig.ids():
                    idfunc(product.meta_ig)
                    changes = True
            if changes:
                product.meta_transmit()

    def item_0x1007(self, sig, stx=None):
        add_item(
            sig=sig, stx=stx,
            name='adc_sample_rate', id=0x1007,
            description='The expected ADC sample rate (samples per '
                        'second) of incoming data.',
            shape=[], format=[('u', 64)],
            value=self.corr.sample_rate_hz)

    def item_0x1009(self, sig, stx=None):
        add_item(
            sig=sig, stx=stx,
            name='n_chans', id=0x1009,
            description='Number of frequency channels in an integration.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.n_chans)

    def item_0x100a(self, sig, stx=None):
        add_item(
            sig=sig, stx=stx,
            name='n_ants', id=0x100A,
            description='The number of antennas in the system.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.n_antennas)

    def item_0x100e(self, sig, stx=None):
        metalist = [(fsrc['source'].name,
                     fsrc['source_num'],
                     fsrc['host'].host,
                     fsrc['numonhost'])
                    for fsrc in self.corr.fengine_sources]
        metalist = numpy.array(metalist)
        add_item(
            sig=sig, stx=stx,
            name='input_labelling', id=0x100E,
            description='input labels and numbers',
            shape=metalist.shape,
            dtype=metalist.dtype,
            value=metalist)

    def item_0x1013(self, sig, stx=None):
        add_item(
            sig=sig, stx=stx,
            name='bandwidth', id=0x1013,
            description='The analogue bandwidth of the digitally processed '
                        'signal in Hz.',
            shape=[], format=[('f', 64)],
            value=self.corr.analogue_bandwidth)

    def item_0x1015(self, sig, stx=None):
        spec_acclen = (self.corr.accumulation_len *
                       self.corr.xeng_accumulation_len)
        add_item(
            sig=sig, stx=stx,
            name='n_accs', id=0x1015,
            description='The number of spectra that are accumulated '
                        'per X-engine dump.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=spec_acclen)

    def item_0x1016(self, sig, stx=None):
        add_item(
            sig=sig, stx=stx,
            name='int_time', id=0x1016,
            description='The time per integration, in seconds.',
            shape=[], format=[('f', 64)],
            value=self.corr.xops.get_acc_time())

    def item_0x101e(self, sig, stx=None):
        add_item(
            sig=sig, stx=stx,
            name='fft_shift', id=0x101E,
            description='The FFT bitshift pattern. F-engine '
                        'correlator internals.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=int(self.corr.configd['fengine']['fft_shift']))

    def item_0x1020(self, sig, stx=None):
        quant_str = self.corr.configd['fengine']['quant_format']
        quant_bits = int(quant_str.split('.')[0])
        add_item(
            sig=sig, stx=stx,
            name='requant_bits', id=0x1020,
            description='Number of bits after requantisation in the '
                        'F engines (post FFT and any phasing stages).',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=quant_bits)

    def item_0x1027(self, sig, stx=None):
        val = self.corr.synchronisation_epoch
        val = 0 if val < 0 else val
        add_item(
            sig=sig, stx=stx,
            name='sync_time', id=0x1027,
            description='The time at which the digitisers were synchronised. '
                        'Seconds since the Unix Epoch.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=val)

    def item_0x1045(self, sig, stx=None):
        sample_bits = int(self.corr.configd['fengine']['sample_bits'])
        add_item(
            sig=sig, stx=stx,
            name='adc_bits', id=0x1045,
            description='How many bits per ADC sample.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=sample_bits)

    def item_0x1046(self, sig, stx=None):
        add_item(
            sig=sig, stx=stx,
            name='scale_factor_timestamp', id=0x1046,
            description='Timestamp scaling factor. Divide the SPEAD '
                        'data packet timestamp by this number to get '
                        'back to seconds since last sync.',
            shape=[], format=[('f', 64)],
            value=self.corr.sample_rate_hz)

    def item_0x1400(self, sig, stx=None):
        all_eqs = self.corr.fops.eq_get()
        for source in self.corr.fengine_sources:
            _srcname = source['source'].name
            _srcnum = source['source_num']
            eq = [[numpy.real(eq_coeff), numpy.imag(eq_coeff)]
                  for eq_coeff in all_eqs[_srcname]['eq']]
            eq = numpy.array(eq, dtype=numpy.int32)
            add_item(
                sig=sig, stx=stx,
                name='eq_coef_%s' % _srcname, id=0x1400 + _srcnum,
                description='The unitless per-channel digital scaling '
                            'factors implemented prior to requantisation, '
                            'post-FFT, for input %s. Complex number '
                            'real,imag 32 bit integers.' % _srcname,
                shape=eq.shape,
                dtype=eq.dtype,
                value=eq)

    @staticmethod
    def item_0x1600(sig, stx=None):
        add_item(
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

    # self.spead_meta_ig.add_item(
    #     name='crosspol_ordering', id=0x100D,
    #     description='',
    #     shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #     value=)
    #
    # self.meta_ig.add_item(
    #     name='coarse_chans', id=0x1017,
    #     description='',
    #     shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #     value=)
    #
    # self.meta_ig.add_item(
    #     name='current_coarse_chan', id=0x1018,
    #     description='',
    #     shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #     value=)
    #
    # self.meta_ig.add_item(
    #     name='fft_shift_fine', id=0x101C,
    #     description='',
    #     shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #     value=)
    #
    # self.meta_ig.add_item(
    #     name='fft_shift_coarse', id=0x101D,
    #     description='',
    #     shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #     value=)
    #
    # port = int(self.corr.configd['xengine']['output_destination_port'])
    # self.meta_ig.add_item(
    #     name='rx_udp_port', id=0x1022,
    #     description='Destination UDP port for X engine output.',
    #     shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #     value=port)

    # ip = self.corr.configd['xengine']['output_destination_ip']
    # self.meta_ig.add_item(
    #     name='rx_udp_ip_str', id=0x1024,
    #     description='Destination UDP IP for X engine output.',
    #     shape=[-1], fmt=spead.STR_FMT,
    #     value=ip)
    # self.meta_ig.add_item(
    #     name='n_stokes', id=0x1040,
    #     description='',
    #     shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #     value=)
    # n_ants_per_xaui = 1
    # self.meta_ig.add_item(
    #     name='n_ants_per_xaui', id=0x1042,
    #     description='',
    #     shape=[], format=[('u', SPEAD_ADDRSIZE)],
    #     value=n_ants_per_xaui)
    #
    # self.meta_ig.add_item(
    #     name='ddc_mix_freq', id=0x1043,
    #     description='',
    #     shape=[],format=[('f', 64)],
    #     value=)
    #
    # self.meta_ig.add_item(
    #     name='ddc_bandwidth', id=0x1044,
    #     description='',
    #     shape=[],format=[('f', 64)],
    #     value=)
    # spead_ig.add_item(name='rf_gain_MyAntStr ', id=0x1200+inputN,
    #                        description='',
    #                        shape=[], format=[('f', 64)],
    #                        value=)
    # spead_ig.add_item(name='eq_coef_MyAntStr', id=0x1400+inputN,
    #                        description='',
    #                        shape=[], format=[('u', 32)],
    #                        value=)

    # spead_ig.add_item(name='beamweight_MyAntStr', id=0x2000+inputN,
    #                        description='',
    #                        shape=[], format=[('u', 32)],
    #                        value=)

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
