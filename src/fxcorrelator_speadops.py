import numpy
import socket
import spead2
import spead2.send as sptx
import struct

SPEAD_ADDRSIZE = 48


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
        self.meta_ig = sptx.ItemGroup(
            flavour=spead2.Flavour(4, 64, SPEAD_ADDRSIZE))

        streamconfig = sptx.StreamConfig(max_packet_size=4096,
                                         max_heaps=8)
        streamsocket = socket.socket(family=socket.AF_INET,
                                     type=socket.SOCK_DGRAM,
                                     proto=socket.IPPROTO_IP)
        ttl_bin = struct.pack('@i', 2)
        streamsocket.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_TTL,
            ttl_bin)
        speadstream = sptx.UdpStream(spead2.ThreadPool(),
                                     str(self.corr.meta_destination['ip']),
                                     self.corr.meta_destination['port'],
                                     streamconfig,
                                     51200000,
                                     streamsocket)
        self.tx = speadstream

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
            if not isinstance(stx, sptx.UdpStream):
                stx = self.tx
            stx.send_heap(sig.get_heap())

    def item_0x1007(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='adc_sample_rate', id=0x1007,
            description='The expected ADC sample rate (samples per '
                        'second) of incoming data.',
            shape=[], format=[('u', 64)],
            value=self.corr.sample_rate_hz)

    def item_0x1009(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='n_chans', id=0x1009,
            description='Number of frequency channels in an integration.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.n_chans)

    def item_0x100a(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='n_ants', id=0x100A,
            description='The number of antennas in the system.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.n_antennas)

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
            shape=metalist.shape,
            dtype=metalist.dtype,
            value=metalist)

    def item_0x1015(self, sig=None, stx=None):
        spec_acclen = (self.corr.accumulation_len *
                       self.corr.xeng_accumulation_len)
        self.add_item(
            sig=sig, stx=stx,
            name='n_accs', id=0x1015,
            description='The number of spectra that are accumulated '
                        'per X-engine dump.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=spec_acclen)

    def item_0x1016(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='int_time', id=0x1016,
            description='The time per integration, in seconds.',
            shape=[], format=[('f', 64)],
            value=self.corr.xops.get_acc_time())

    def item_0x101e(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='fft_shift', id=0x101E,
            description='The FFT bitshift pattern. F-engine '
                        'correlator internals.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=int(self.corr.configd['fengine']['fft_shift']))

    def item_0x1020(self, sig=None, stx=None):
        quant_str = self.corr.configd['fengine']['quant_format']
        quant_bits = int(quant_str.split('.')[0])
        self.add_item(
            sig=sig, stx=stx,
            name='requant_bits', id=0x1020,
            description='Number of bits after requantisation in the '
                        'F engines (post FFT and any phasing stages).',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=quant_bits)

    def item_0x1027(self, sig=None, stx=None):
        val = self.corr.synchronisation_epoch
        val = 0 if val < 0 else val
        self.add_item(
            sig=sig, stx=stx,
            name='sync_time', id=0x1027,
            description='The time at which the digitisers were synchronised. '
                        'Seconds since the Unix Epoch.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=val)

    def item_0x1045(self, sig=None, stx=None):
        sample_bits = int(self.corr.configd['fengine']['sample_bits'])
        self.add_item(
            sig=sig, stx=stx,
            name='adc_bits', id=0x1045,
            description='How many bits per ADC sample.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=sample_bits)

    def item_0x1046(self, sig=None, stx=None):
        self.add_item(
            sig=sig, stx=stx,
            name='scale_factor_timestamp', id=0x1046,
            description='Timestamp scaling factor. Divide the SPEAD '
                        'data packet timestamp by this number to get '
                        'back to seconds since last sync.',
            shape=[], format=[('f', 64)],
            value=self.corr.sample_rate_hz)

    def item_0x1400(self, sig=None, stx=None):
        all_eqs = self.corr.fops.eq_get()
        for source in self.corr.fengine_sources:
            _srcname = source['source'].name
            _srcnum = source['source_num']
            eq = [[numpy.real(eq_coeff), numpy.imag(eq_coeff)]
                  for eq_coeff in all_eqs[_srcname]['eq']]
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

    def item_0x1600(self, sig=None, stx=None):
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

    def meta_update_all(self):
        """
        Update metadata for this correlator.
        :return:
        """
        self.item_0x1007()

        self.meta_ig.add_item(
            name='n_bls', id=0x1008,
            description='Number of baselines in the data product.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=len(self.corr.xops.get_baseline_order()))

        self.item_0x1009()
        self.item_0x100a()

        n_xengs = len(self.corr.xhosts) * self.corr.x_per_fpga
        self.meta_ig.add_item(
            name='n_xengs', id=0x100B,
            description='The number of x-engines in the system.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=n_xengs)

        bls_ordering = numpy.array(
            [baseline for baseline in self.corr.xops.get_baseline_order()])
        # this is a list of the baseline product pairs, e.g. ['ant0x' 'ant0y']
        self.meta_ig.add_item(
            name='bls_ordering', id=0x100C,
            description='The baseline ordering in the output data product.',
            shape=bls_ordering.shape,
            dtype=bls_ordering.dtype,
            value=bls_ordering)

        self.item_0x100e()

        self.meta_ig.add_item(
            name='center_freq', id=0x1011,
            description='The on-sky centre-frequency.',
            shape=[], format=[('f', 64)],
            value=int(self.corr.configd['fengine']['true_cf']))

        self.meta_ig.add_item(
            name='bandwidth', id=0x1013,
            description='The input (analogue) bandwidth of the system.',
            shape=[], format=[('f', 64)],
            value=int(self.corr.configd['fengine']['bandwidth']))

        self.item_0x1015()
        self.item_0x1016()
        self.item_0x101e()

        self.meta_ig.add_item(
            name='xeng_acc_len', id=0x101F,
            description='Number of spectra accumulated inside X engine. '
                        'Determines minimum integration time and '
                        'user-configurable integration time stepsize. '
                        'X-engine correlator internals.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.xeng_accumulation_len)

        self.item_0x1020()

        pkt_len = int(self.corr.configd['fengine']['10gbe_pkt_len'])
        self.meta_ig.add_item(
            name='feng_pkt_len', id=0x1021,
            description='Payload size of 10GbE packet exchange between '
                        'F and X engines in 64 bit words. Usually equal '
                        'to the number of spectra accumulated inside X '
                        'engine. F-engine correlator internals.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=pkt_len)

        port = self.corr.xeng_tx_destination['port']
        self.meta_ig.add_item(
            name='rx_udp_port', id=0x1022,
            description='Destination UDP port for xengine data output.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=port)

        port = int(self.corr.configd['fengine']['10gbe_port'])
        self.meta_ig.add_item(
            name='feng_udp_port', id=0x1023,
            description='Port for F-engines 10Gbe links in the system.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=port)

        ipstr = numpy.array(self.corr.xeng_tx_destination['ip'])
        self.meta_ig.add_item(
            name='rx_udp_ip_str', id=0x1024,
            description='Destination IP address for xengine data ouput.',
            shape=ipstr.shape,
            dtype=ipstr.dtype,
            value=ipstr)

        ipstr = numpy.array(self.corr.configd['fengine']['10gbe_start_ip'])
        self.meta_ig.add_item(
            name='feng_start_ip', id=0x1025,
            description='Start IP address for F-engines in the system.',
            shape=ipstr.shape,
            dtype=ipstr.dtype,
            value=ipstr)

        self.meta_ig.add_item(
            name='xeng_rate', id=0x1026,
            description='Target clock rate of processing engines (xeng).',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.xeng_clk)

        self.item_0x1027()

        x_per_fpga = int(self.corr.configd['xengine']['x_per_fpga'])
        self.meta_ig.add_item(
            name='x_per_fpga', id=0x1041,
            description='Number of X engines per FPGA host.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=x_per_fpga)

        self.meta_ig.add_item(
            name='ddc_mix_freq', id=0x1043,
            description='Digital downconverter mixing frequency as a fraction '
                        'of the ADC sampling frequency. eg: 0.25. Set to zero '
                        'if no DDC is present.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=0)

        self.item_0x1045()
        self.item_0x1046()

        self.meta_ig.add_item(
            name='xeng_out_bits_per_sample', id=0x1048,
            description='The number of bits per value of the xeng '
                        'accumulator output. Note this is for a '
                        'single value, not the combined complex size.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.xeng_outbits)

        self.meta_ig.add_item(
            name='f_per_fpga', id=0x1049,
            description='Number of F engines per FPGA host.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.corr.f_per_fpga)

        self.item_0x1400()

        self.item_0x1600()

        self.meta_ig.add_item(
            name='flags_xeng_raw', id=0x1601,
            description='Flags associated with xeng_raw data output. '
                        'bit 34 - corruption or data missing during integration'
                        'bit 33 - overrange in data path '
                        'bit 32 - noise diode on during integration '
                        'bits 0 - 31 reserved for internal debugging',
            shape=[], format=[('u', SPEAD_ADDRSIZE)])

        self.meta_ig.add_item(
            name='xeng_raw', id=0x1800,
            description='Raw data for %i xengines in the system. This item '
                        'represents a full spectrum (all frequency channels) '
                        'assembled from lowest frequency to highest '
                        'frequency. Each frequency channel contains the data '
                        'for all baselines (baselines given by SPEAD ID '
                        '0x100C). Each value is a complex number -- two (real '
                        'and imaginary) unsigned integers.' % n_xengs,
            # dtype=numpy.int32,
            dtype=numpy.dtype('>i4'),
            shape=[self.corr.n_chans,
                   len(self.corr.xops.get_baseline_order()),
                   2])

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
