import numpy
import socket
import spead64_48 as spead
import struct


class SpeadOperations(object):
    def __init__(self, corr_obj):
        """
        :param corr_obj: the FxCorrelator object with which we interact
        :return:
        """
        self.corr = corr_obj
        self.logger = self.corr.logger
        self.tx = None
        self.meta_ig = None
        self.initialise()

    def initialise(self):
        """
        Set up the base transmitter and itemgroup
        :return:
        """
        self.meta_ig = spead.ItemGroup()

        _stxudp = spead.TransportUDPtx(str(self.corr.meta_destination['ip']),
                                       self.corr.meta_destination['port'])
        self.tx = spead.Transmitter(_stxudp)

        # update the multicast socket option to use a TTL of 2,
        # in order to traverse the L3 network on site.
        ttl_bin = struct.pack('@i', 2)
        self.tx.t._udp_out.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_TTL,
            ttl_bin)

        # multicast
        # mcast_interface = \
        #     self.corr.configd['xengine']['multicast_interface_address']
        # self.tx.t._udp_out.setsockopt(
        #     socket.SOL_IP, socket.IP_MULTICAST_IF,
        #     socket.inet_aton(mcast_interface))
        # self.tx.t._udp_out.setsockopt(
        #     socket.SOL_IP, socket.IP_ADD_MEMBERSHIP,
        #     socket.inet_aton(txip_str) + socket.inet_aton(mcast_interface))

    def add_item(self, sig=None, stx=None, **kwargs):
        sig = sig or self.meta_ig
        sig.add_item(**kwargs)
        if stx:
            if not isinstance(stx, spead.Transmitter):
                stx = self.tx
            stx.send_heap(sig.get_heap())

    def item_0x1007(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='adc_sample_rate', id=0x1007,
            description='The expected ADC sample rate (samples per '
                        'second) of incoming data.',
            shape=[], fmt=spead.mkfmt(('u', 64)),
            init_val=self.corr.sample_rate_hz)

    def item_0x1009(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='n_chans', id=0x1009,
            description='Number of frequency channels in an integration.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=self.corr.n_chans)

    def item_0x100a(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='n_ants', id=0x100A,
            description='The number of antennas in the system.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=self.corr.n_antennas)

    def item_0x100e(self, sig=None, stx=None):
        metalist = [(fsrc['source'].name,
                     fsrc['source_num'],
                     fsrc['host'].host,
                     fsrc['numonhost'])
                    for fsrc in self.corr.fengine_sources]
        metalist = numpy.array(metalist)
        self.add_item(
            sig=sig, stx=stx,
            name='input_labelling', id=0x100E,
            description='input labels and numbers',
            init_val=metalist)

    def item_0x1015(self, sig=None, stx=None):
        spec_acclen = (self.corr.accumulation_len *
                       self.corr.xeng_accumulation_len)
        self.add_item(
            sig=sig, stx=stx,
            name='n_accs', id=0x1015,
            description='The number of spectra that are accumulated '
                        'per X-engine dump.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=spec_acclen)

    def item_0x1016(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='int_time', id=0x1016,
            description='The time per integration, in seconds.',
            shape=[], fmt=spead.mkfmt(('f', 64)),
            init_val=self.corr.xops.get_acc_time())

    def item_0x101e(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='fft_shift', id=0x101E,
            description='The FFT bitshift pattern. F-engine '
                        'correlator internals.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=int(self.corr.configd['fengine']['fft_shift']))

    def item_0x1020(self, sig=None, stx=None):
        quant_str = self.corr.configd['fengine']['quant_format']
        quant_bits = int(quant_str.split('.')[0])
        self.add_item(
            sig=sig, stx=stx,
            name='requant_bits', id=0x1020,
            description='Number of bits after requantisation in the '
                        'F engines (post FFT and any phasing stages).',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=quant_bits)

    def item_0x1045(self, sig=None, stx=None):
        sample_bits = int(self.corr.configd['fengine']['sample_bits'])
        self.add_item(
            sig=sig, stx=stx,
            name='adc_bits', id=0x1045,
            description='How many bits per ADC sample.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=sample_bits)

    def item_0x1400(self, sig=None, stx=None):
        all_eqs = self.corr.fops.eq_get()
        for source in self.corr.fengine_sources:
            _srcname = source['source'].name
            _srcnum = source['source_num']
            eqlen = len(all_eqs[_srcname]['eq'])
            self.add_item(
                sig=sig, stx=stx,
                name='eq_coef_%s' % _srcname, id=0x1400 + _srcnum,
                description='The unitless per-channel digital scaling '
                            'factors implemented prior to requantisation, '
                            'post-FFT, for input %s. Complex number '
                            'real,imag 32 bit integers.' % _srcname,
                shape=[eqlen, 2],
                fmt=spead.mkfmt(('u', 32)),
                init_val=[[numpy.real(eq_coeff), numpy.imag(eq_coeff)] for
                          eq_coeff in all_eqs[_srcname]['eq']])

    def meta_update_all(self):
        """
        Update metadata for this correlator.
        :return:
        """
        self.item_0x1007()

        self.meta_ig.add_item(
            name='n_bls', id=0x1008,
            description='Number of baselines in the data product.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=len(self.corr.xops.get_baseline_order()))

        self.item_0x1009()
        self.item_0x100a()

        n_xengs = len(self.corr.xhosts) * self.corr.x_per_fpga
        self.meta_ig.add_item(
            name='n_xengs', id=0x100B,
            description='The number of x-engines in the system.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=n_xengs)

        bls_ordering = numpy.array(
            [baseline for baseline in self.corr.xops.get_baseline_order()])
        self.meta_ig.add_item(
            name='bls_ordering', id=0x100C,
            description='The baseline ordering in the output data product.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=bls_ordering)

        self.item_0x100e()

        self.meta_ig.add_item(
            name='center_freq', id=0x1011,
            description='The on-sky centre-frequency.',
            shape=[], fmt=spead.mkfmt(('f', 64)),
            init_val=int(self.corr.configd['fengine']['true_cf']))

        self.meta_ig.add_item(
            name='bandwidth', id=0x1013,
            description='The input (analogue) bandwidth of the system.',
            shape=[], fmt=spead.mkfmt(('f', 64)),
            init_val=int(self.corr.configd['fengine']['bandwidth']))

        self.item_0x1015()
        self.item_0x1016()
        self.item_0x101e()

        self.meta_ig.add_item(
            name='xeng_acc_len', id=0x101F,
            description='Number of spectra accumulated inside X engine. '
                        'Determines minimum integration time and '
                        'user-configurable integration time stepsize. '
                        'X-engine correlator internals.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=self.corr.xeng_accumulation_len)

        self.item_0x1020()

        pkt_len = int(self.corr.configd['fengine']['10gbe_pkt_len'])
        self.meta_ig.add_item(
            name='feng_pkt_len', id=0x1021,
            description='Payload size of 10GbE packet exchange between '
                        'F and X engines in 64 bit words. Usually equal '
                        'to the number of spectra accumulated inside X '
                        'engine. F-engine correlator internals.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=pkt_len)

        port = int(self.corr.configd['fengine']['10gbe_port'])
        self.meta_ig.add_item(
            name='feng_udp_port', id=0x1023,
            description='Port for F-engines 10Gbe links in the system.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=port)

        ipstr = self.corr.configd['fengine']['10gbe_start_ip']
        ip = struct.unpack('>I', socket.inet_aton(ipstr))[0]
        self.meta_ig.add_item(
            name='feng_start_ip', id=0x1025,
            description='Start IP address for F-engines in the system.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=ip)

        self.meta_ig.add_item(
            name='xeng_rate', id=0x1026,
            description='Target clock rate of processing engines (xeng).',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=self.corr.xeng_clk)

        self.meta_ig.add_item(
            name='sync_time', id=0x1027,
            description='The time at which the digitisers were synchronised. '
                        'Seconds since the Unix Epoch.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=self.corr.synchronisation_epoch)

        x_per_fpga = int(self.corr.configd['xengine']['x_per_fpga'])
        self.meta_ig.add_item(
            name='x_per_fpga', id=0x1041,
            description='Number of X engines per FPGA host.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=x_per_fpga)

        self.item_0x1045()

        self.meta_ig.add_item(
            name='scale_factor_timestamp', id=0x1046,
            description='Timestamp scaling factor. Divide the SPEAD '
                        'data packet timestamp by this number to get '
                        'back to seconds since last sync.',
            shape=[], fmt=spead.mkfmt(('f', 64)),
            init_val=self.corr.sample_rate_hz)

        self.meta_ig.add_item(
            name='xeng_out_bits_per_sample', id=0x1048,
            description='The number of bits per value of the xeng '
                        'accumulator output. Note this is for a '
                        'single value, not the combined complex size.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=self.corr.xeng_outbits)

        self.meta_ig.add_item(
            name='f_per_fpga', id=0x1049,
            description='Number of F engines per FPGA host.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
            init_val=self.corr.f_per_fpga)

        self.item_0x1400()

        self.meta_ig.add_item(
            name='timestamp', id=0x1600,
            description='Timestamp of start of this integration. uint '
                        'counting multiples of ADC samples since last sync '
                        '(sync_time, id=0x1027). Divide this number by '
                        'timestamp_scale (id=0x1046) to get back to seconds '
                        'since last sync when this integration was actually '
                        'started.',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)))

        self.meta_ig.add_item(
            name='flags_xeng_raw', id=0x1601,
            description='Flags associated with xeng_raw data output. '
                        'bit 34 - corruption or data missing during integration'
                        'bit 33 - overrange in data path '
                        'bit 32 - noise diode on during integration '
                        'bits 0 - 31 reserved for internal debugging',
            shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)))

        xraw_array = numpy.dtype(numpy.int32), (
            self.corr.n_chans, len(self.corr.xops.get_baseline_order()), 2)
        self.meta_ig.add_item(
            name='xeng_raw', id=0x1800,
            description='Raw data for %i xengines in the system. This item '
                        'represents a full spectrum (all frequency channels) '
                        'assembled from lowest frequency to highest '
                        'frequency. Each frequency channel contains the data '
                        'for all baselines (n_bls given by SPEAD ID 0x100b). '
                        'Each value is a complex number -- two (real and '
                        'imaginary) unsigned integers.' % n_xengs,
            ndarray=xraw_array)

    def meta_transmit_all(self):
        """
        Actually send the metadata heap
        :return:
        """
        if self.corr.meta_destination is None:
            self.logger.info('SPEAD meta destination is still unset, '
                             'NOT sending metadata at this time.')
            return

        self.tx.send_heap(self.meta_ig.get_heap())

    def meta_issue_all(self):
        """
        Issue = update the metadata then send it.
        :return:
        """
        self.meta_update_all()
        self.meta_transmit_all()
        self.logger.info('Issued SPEAD data descriptor to %s:%i.' % (
            self.corr.meta_destination['ip'],
            self.corr.meta_destination['port']))

    # self.spead_meta_ig.add_item(
    #     name='crosspol_ordering', id=0x100D,
    #     description='',
    #     shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #     init_val=)
    #
    # self.meta_ig.add_item(
    #     name='coarse_chans', id=0x1017,
    #     description='',
    #     shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #     init_val=)
    #
    # self.meta_ig.add_item(
    #     name='current_coarse_chan', id=0x1018,
    #     description='',
    #     shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #     init_val=)
    #
    # self.meta_ig.add_item(
    #     name='fft_shift_fine', id=0x101C,
    #     description='',
    #     shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #     init_val=)
    #
    # self.meta_ig.add_item(
    #     name='fft_shift_coarse', id=0x101D,
    #     description='',
    #     shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #     init_val=)
    #
    # port = int(self.corr.configd['xengine']['output_destination_port'])
    # self.meta_ig.add_item(
    #     name='rx_udp_port', id=0x1022,
    #     description='Destination UDP port for X engine output.',
    #     shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #     init_val=port)

    # ip = self.corr.configd['xengine']['output_destination_ip']
    # self.meta_ig.add_item(
    #     name='rx_udp_ip_str', id=0x1024,
    #     description='Destination UDP IP for X engine output.',
    #     shape=[-1], fmt=spead.STR_FMT,
    #     init_val=ip)
    # self.meta_ig.add_item(
    #     name='n_stokes', id=0x1040,
    #     description='',
    #     shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #     init_val=)
    # n_ants_per_xaui = 1
    # self.meta_ig.add_item(
    #     name='n_ants_per_xaui', id=0x1042,
    #     description='',
    #     shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #     init_val=n_ants_per_xaui)
    #
    # self.meta_ig.add_item(
    #     name='ddc_mix_freq', id=0x1043,
    #     description='',
    #     shape=[],fmt=spead.mkfmt(('f', 64)),
    #     init_val=)
    #
    # self.meta_ig.add_item(
    #     name='ddc_bandwidth', id=0x1044,
    #     description='',
    #     shape=[],fmt=spead.mkfmt(('f', 64)),
    #     init_val=)
    # spead_ig.add_item(name='rf_gain_MyAntStr ', id=0x1200+inputN,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('f', 64)),
    #                        init_val=)
    # spead_ig.add_item(name='eq_coef_MyAntStr', id=0x1400+inputN,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', 32)),
    #                        init_val=)

    # spead_ig.add_item(name='beamweight_MyAntStr', id=0x2000+inputN,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', 32)),
    #                        init_val=)

    # spead_ig.add_item(name='incoherent_sum', id=0x3000,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', 32)),
    #                        init_val=)

    # spead_ig.add_item(name='n_inputs', id=0x3100,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='digitiser_id', id=0x3101,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='digitiser_status', id=0x3102,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='pld_len', id=0x3103,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='raw_data_MyAntStr', id=0x3300+inputN,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='Reserved for SP-CAM meta-data', id=0x7000-0x7fff,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='feng_id', id=0xf101,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='feng_status', id=0xf102,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='frequency', id=0xf103,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='raw_freq_MyAntStr', id=0xf300+inputN,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)

    # spead_ig.add_item(name='bf_MyBeamName', id=0xb000+beamN,
    #                        description='',
    #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
    #                        init_val=)
