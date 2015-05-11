__author__ = 'paulp'

import time
import logging
import struct

from host_fpga import FpgaHost

LOGGER = logging.getLogger(__name__)


class FpgaFHost(FpgaHost):
    """
    A Host, that hosts Fengines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, boffile=None, connect=True, config=None):
        FpgaHost.__init__(self, host, katcp_port=katcp_port, boffile=boffile, connect=connect)
        self._config = config
        self.data_sources = []  # a list of DataSources received by this f-engine host
        self.eqs = {}  # a dictionary, indexed on source name, containing tuples of poly and bram name
        if config is not None:
            self.num_fengines = int(config['f_per_fpga'])
            self.ports_per_fengine = int(config['ports_per_fengine'])
            self.fft_shift = int(config['fft_shift'])
            self.n_chans = int(config['n_chans'])
        else:
            self.num_fengines = None
            self.ports_per_fengine = None
            self.fft_shift = None
            self.n_chans = None

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile, connect=True, config=config_source)

    def clear_status(self):
        """
        Clear the status registers and counters on this f-engine host
        :return:
        """
        self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse', cnt_rst='pulse')

    def host_okay(self):
        """
        Is this host/LRU okay?
        :return:
        """
        try:
            assert self.check_rx()
            err_one = self.registers.ct_errcnt.read()['data']
            err_two = self.registers.wintime_error.read()['data']
            ct_cnt_one = self.registers.ct_cnt.read()['data']
            time.sleep(0.2)
            ct_cnt_two = self.registers.ct_cnt.read()['data']
            assert err_one['errcnt0'] == 0
            assert err_one['parerrcnt0'] == 0
            assert err_one['errcnt1'] == 0
            assert err_one['parerrcnt1'] == 0
            assert err_two['step'] == 0
            assert err_two['vs_spead'] == 0
            assert ct_cnt_two['validcnt'] - ct_cnt_one['validcnt'] > 0
            assert ct_cnt_two['synccnt'] - ct_cnt_one['synccnt'] > 0
        except:
            LOGGER.info('F host %s host_okay() - FALSE.' % self.host)
            return False
        LOGGER.info('F host %s host_okay() - TRUE.' % self.host)
        return True

    def check_rx(self, max_waittime=30):
        """
        Check the receive path on this f host
        :param max_waittime: the maximum time to wait for raw 10gbe data
        :return:
        """
        self.check_rx_raw(max_waittime)
        self.check_rx_spead()
        self.check_rx_reorder()
        return True

    def check_rx_reorder(self):
        """
        Is this F host reordering received data correctly?
        :return:
        """
        def get_gbe_data():
            data = {}
            pktof_ctrs = self.registers.pktof_ctrs.read()['data']
            for gbe in [0, 1, 2, 3]:
                data['pktof_ctr%i' % gbe] = pktof_ctrs['gbe%i' % gbe]             
            recverr_ctrs = self.registers.recverr_ctr.read()['data']
            for pol in [0, 1]:
                data['recverr_ctr%i' % pol] = recverr_ctrs['p%i' % pol]             
            temp = self.registers.reorder_ctrs.read()['data']
            data['mcnt_relock'] = temp['mcnt_relock']
            data['timerror'] = temp['timestep_error']
            data['discard'] = temp['discard']
            temp = self.registers.pfb_of.read()['data']
            data['pfb_of0'] = temp['of0']
            data['pfb_of1'] = temp['of1']
            return data
        rxregs = get_gbe_data()
        time.sleep(1)
        rxregs_new = get_gbe_data()
        for gbe in [0, 1, 2, 3]:
            if rxregs_new['pktof_ctr%i' % gbe] != rxregs['pktof_ctr%i' % gbe]:
                raise RuntimeError('F host %s packet overflow on interface gbe%i. %i -> %i' % (
                    self.host, gbe, rxregs_new['pktof_ctr%i' % gbe], rxregs['pktof_ctr%i' % gbe]))
        for pol in [0, 1]:
            if rxregs_new['recverr_ctr%i' % pol] != rxregs['recverr_ctr%i' % pol]:
                raise RuntimeError('F host %s pol %i reorder count error. %i -> %i' % (
                    self.host, pol, rxregs_new['recverr_ctr%i' % pol], rxregs['recverr_ctr%i' % pol]))
        if rxregs_new['mcnt_relock'] != rxregs['mcnt_relock']:
            raise RuntimeError('F host %s mcnt_relock is changing. %i -> %i' % (
                self.host, rxregs_new['mcnt_relock'], rxregs['mcnt_relock']))
        if rxregs_new['timerror'] != rxregs['timerror']:
            raise RuntimeError('F host %s timestep error is changing. %i -> %i' % (
                self.host, rxregs_new['timerror'], rxregs['timerror']))
        if rxregs_new['discard'] != rxregs['discard']:
            raise RuntimeError('F host %s discarding packets. %i -> %i' % (
                self.host, rxregs_new['discard'], rxregs['discard']))
        LOGGER.info('F host %s is reordering data okay.' % self.host)

    def read_spead_counters(self):
        """
        Read the SPEAD rx and error counters for this F host
        :return:
        """
        rv = []
	errors = self.registers.speaderr_ctrs.read()
        for core_ctr in range(0, 4):
            counter = self.registers['gbe%i_rxctr' % core_ctr].read()['data']['reg']
            error = errors['data']['gbe%i' % core_ctr]
	    rv.append((counter, error))
        #for core_ctr in range(0, 4):
            #counter = self.registers['updebug_sp_val%i' % core_ctr].read()['data']['reg']
            #error = self.registers['updebug_sp_err%i' % core_ctr].read()['data']['reg']
	    #rv.append((counter, error))
        return rv

    def get_local_time(self):
        """
        Get the local timestamp of this board, received from the digitiser
        :return: time in samples since the digitiser epoch
        """
        first_msw = self.registers.local_time_msw.read()['data']['timestamp_msw']
        while self.registers.local_time_msw.read()['data']['timestamp_msw'] == first_msw:
            time.sleep(0.01)
        lsw = self.registers.local_time_lsw.read()['data']['timestamp_lsw']
        msw = self.registers.local_time_msw.read()['data']['timestamp_msw']
        assert msw == first_msw + 1  # if this fails the network is waaaaaaaay slow
        return (msw << 32) | lsw

    def add_source(self, data_source):
        """
        Add a new data source to this fengine host
        :param data_source: A DataSource object
        :return:
        """
        # check that it doesn't already exist before adding it
        for source in self.data_sources:
            assert source.source_number != data_source.source_number
            assert source.name != data_source.name
        self.data_sources.append(data_source)

    def get_source_eq(self, source_name=None):
        """
        Return a dictionary of all the EQ settings for the sources allocated to this fhost
        :return:
        """
        if source_name is not None:
            return self.eqs[source_name]
        return self.eqs

    def read_eq(self, eq_bram=None, eq_name=None):
        """
        Read a given EQ BRAM.
        :param eq_bram:
        :return: a list of the complex EQ values from RAM
        """
        if eq_bram is None and eq_name is None:
            raise RuntimeError('Cannot have both tuple and name None')
        if eq_name is not None:
            eq_bram = 'eq%i' % self.eqs[eq_name][1]
        # eq vals are packed as 32-bit complex (16 real, 16 imag)
        eqvals = self.read(eq_bram, self.n_chans*4)
        eqvals = struct.unpack('>%ih' % (self.n_chans*2), eqvals)
        eqcomplex = []
        for ctr in range(0, len(eqvals), 2):
            eqcomplex.append(eqvals[ctr] + (1j * eqvals[ctr+1]))
        return eqcomplex

    def write_eq_all(self):
        """
        Write the self.eq variables to the device SBRAMs
        :return:
        """
        for eqname in self.eqs.keys():
            LOGGER.debug('Writing EQ %s' % eqname)
            self.write_eq(eq_name=eqname)

    def write_eq(self, eq_tuple=None, eq_name=None):
        """
        Write a given complex eq to the given SBRAM.
        :param eq_tuple: a tuple of an integer, complex number or list or integers or complex numbers and a sbram name
        :param eq_name: the name of an eq to use, found in the self.eqs dictionary
        :return:
        """
        if eq_tuple is None and eq_name is None:
            raise RuntimeError('Cannot have both tuple and name None')
        if eq_name is not None:
            if eq_name not in self.eqs.keys():
                raise ValueError('Unknown source name %s' % eq_name)
            eq_poly = self.eqs[eq_name]['eq']
            eq_bram = 'eq%i' % self.eqs[eq_name]['bram_num']
        else:
            eq_poly = eq_tuple[0]
            eq_bram = eq_tuple[1]
        if len(eq_poly) == 1:
            # single complex
            creal = self.n_chans * [int(eq_poly[0].real)]
            cimag = self.n_chans * [int(eq_poly[0].imag)]
        elif len(eq_poly) == self.n_chans:
            # list - one for each channel
            creal = [num.real for num in eq_poly]
            cimag = [num.imag for num in eq_poly]
        else:
            # polynomial
            raise NotImplementedError('Polynomials are not yet complete.')
        coeffs = (self.n_chans * 2) * [0]
        coeffs[0::2] = creal
        coeffs[1::2] = cimag
        ss = struct.pack('>%ih' % (self.n_chans * 2), *coeffs)
        self.write(eq_bram, ss, 0)
        LOGGER.debug('%s: wrote EQ to sbram %s' % (self.host, eq_bram))
        return len(ss)

    def set_fft_shift(self, shift_schedule=None, issue_meta=True):
        """
        Set the FFT shift schedule.
        :param shift_schedule: int representing bit mask. '1' represents a shift for that stage. First stage is MSB.
        Use default if None provided
        :param issue_meta: Should SPEAD meta data be sent after the value is changed?
        :return: <nothing>
        """
        if shift_schedule is None:
            shift_schedule = self.fft_shift
        self.registers.fft_shift.write(fft_shift=shift_schedule)

    def get_fft_shift(self):
        """
        Get the current FFT shift schedule from the FPGA.
        :return: integer representing the FFT shift schedule for all the FFTs on this engine.
        """
        return self.registers.fft_shift.read()['data']['fft_shift']

    def get_quant_snapshot(self, source_name=None):
        """
        Read the post-quantisation snapshot for a given source
        :return:
        """
        raise NotImplementedError
        """
        source_names = []
        if source_name is None:
            for src in self.data_sources:
                source_names.append(src.name)
        else:
            for src in self.data_sources:
                if src.name == source_name:
                    source_names.append(source_name)
                    break
        if len(source_names) == 0:
            raise RuntimeError('Could not find source %s on this f-engine host or no sources given' % source_name)
        targetsrc.host.snapshots.snapquant_ss.arm()
        targetsrc.host.registers.control.write(snapquant_arm='pulse')
        sdata = targetsrc.host.snapshots.snapquant_ss.read(arm=False)['data']
        self.snapshots.snapquant_ss.arm()
        self.registers.control.write(snapquant_arm='pulse')
        snapdata = self.snapshots.snapquant_ss.read(arm=False)['data']
        raise RuntimeError
        """

    def get_pfb_snapshot(self, pol=0):
        # select the pol
        self.registers.control.write(snappfb_dsel=pol)

        # arm the snaps
        self.snapshots.snappfb_0_ss.arm()
        self.snapshots.snappfb_1_ss.arm()

        # allow them to trigger
        self.registers.control.write(snappfb_arm='pulse')

        # read the data
        r0_to_r3 = self.snapshots.snappfb_0_ss.read(arm=False)['data']
        i3 = self.snapshots.snappfb_1_ss.read(arm=False)['data']

        # reorder the data
        p_data = []
        for ctr in range(0, len(i3['i3'])):
            p_data.append(complex(r0_to_r3['r0'][ctr], r0_to_r3['i0'][ctr]))
            p_data.append(complex(r0_to_r3['r1'][ctr], r0_to_r3['i1'][ctr]))
            p_data.append(complex(r0_to_r3['r2'][ctr], r0_to_r3['i2'][ctr]))
            p_data.append(complex(r0_to_r3['r3'][ctr], i3['i3'][ctr]))
        return p_data

'''
    def _get_fengine_fpga_config(self):

        # constants for accessing polarisation specific registers 'x' even, 'y' odd
        self.pol0_offset =  '%s' % (str(self.id*2))
        self.pol1_offset =  '%s' % (str(self.id*2+1))

        # default fft shift schedule
        self.config['fft_shift']                        = self.config_portal.get_int([ '%s '%self.descriptor, 'fft_shift'])

        # output data resolution after requantisation
        self.config['n_bits_output']                    = self.config_portal.get_int([ '%s '%self.descriptor, 'n_bits_output'])
        self.config['bin_pt_output']                    = self.config_portal.get_int([ '%s '%self.descriptor, 'bin_pt_output'])

        # equalisation (only necessary in FPGA based fengines)
        self.config['equalisation'] = {}
        # TODO this may not be constant across fengines (?)
        self.config['equalisation']['decimation']       = self.config_portal.get_int(['equalisation', 'decimation'])
        # TODO what is this?
        self.config['equalisation']['tolerance']        = self.config_portal.get_float(['equalisation', 'tolerance'])
        # coeffs
        self.config['equalisation']['n_bytes_coeffs']   = self.config_portal.get_int(['equalisation', 'n_bytes_coeffs'])
        self.config['equalisation']['bin_pt_coeffs']    = self.config_portal.get_int(['equalisation', 'bin_pt_coeffs'])
        # default equalisation polynomials for polarisations
        self.config['equalisation']['poly0']            = self.config_portal.get_int_list([ '%s '%self.descriptor, 'poly0'])
        self.config['equalisation']['poly1']            = self.config_portal.get_int_list([ '%s '%self.descriptor, 'poly1'])

    def __getattribute__(self, name):
        """Overload __getattribute__ to make shortcuts for getting object data.
        """

        # fft_shift is same for all fengine_fpgas of this type on device
        # (overload in child class if this changes)
        if name == 'fft_shift':
            return self.host.device_by_name( '%sfft_shift'   %self.tag)
        # we can't access Shared BRAMs in the same way as we access registers
        # at the moment, so we access the name and use read/write
        elif name == 'eq0_name':
            return  '%seq  %s'  % (self.tag, self.pol0_offset)
        elif name == 'eq1_name':
            return  '%seq  %s'  % (self.tag, self.pol1_offset)
        # fengines transmit to multiple xengines. Each xengine processes a continuous band of
        # frequencies with the lowest numbered band from all antennas being processed by the first xengine
        # and so on. The xengines have IP addresses starting a txip_base and increasing linearly. Some xengines
        # may share IP addresses
        elif name == 'txip_base':
            return self.host.device_by_name( '%stxip_base  %s'  % (self.tag, self.offset))
        elif name == 'txport':
            return self.host.device_by_name( '%stxport  %s'  % (self.tag, self.offset))
        # two polarisations
        elif name == 'snap_adc0':
            return self.host.device_by_name( '%ssnap_adc  %s_ss' % (self.tag, self.pol0_offset))
        elif name == 'snap_adc1':
            return self.host.device_by_name( '%ssnap_adc  %s_ss' % (self.tag, self.pol1_offset))
        elif name == 'snap_quant0':
            return self.host.device_by_name( '%sadc_quant  %s_ss' % (self.tag, self.pol0_offset))
        elif name == 'snap_quant1':
            return self.host.device_by_name( '%sadc_quant  %s_ss' % (self.tag, self.pol1_offset))

        # if attribute name not here try parent class
        return EngineFpga.__getattribute__(self, name)

    ##############################################
    # Equalisation before re-quantisation stuff  #
    ##############################################

    def get_equalisation(self, pol_index):
        """ Get current equalisation values applied pre-quantisation
        """

        reg_name = getattr(self, 'eq  %s_name' % pol_index)
        n_chans = self.config['n_chans']
        decimation = self.config['equalisation']['decimation']
        n_coeffs = n_chans/decimation * 2

        n_bytes = self.config['equalisation']['n_bytes_coeffs']
        bin_pt = self.config['equalisation']['bin_pt_coeffs']

        #read raw bytes
        # we cant access brams like registers, so use old style read
        coeffs_raw = self.host.read(reg_name, n_coeffs*n_bytes)

        coeffs = self.str2float(coeffs_raw, n_bytes*8, bin_pt)

        #pad coeffs out by decimation factor
        coeffs_padded = numpy.reshape(numpy.tile(coeffs, [decimation, 1]), [1, n_chans], 'F')

        return coeffs_padded[0]

    def get_default_equalisation(self, pol_index):
        """ Get default equalisation settings
        """

        decimation = self.config['equalisation']['decimation']
        n_chans = self.config['n_chans']
        n_coeffs = n_chans/decimation

        poly = self.config['equalisation']['poly  %s'  % pol_index]
        eq_coeffs = numpy.polyval(poly, range(n_chans))[decimation/2::decimation]
        eq_coeffs = numpy.array(eq_coeffs, dtype=complex)

        if len(eq_coeffs) != n_coeffs:
            log_runtime_error(LOGGER, "Something's wrong. I have %i eq coefficients when I should have %i."  % (len(eq_coeffs), n_coeffs))
        return eq_coeffs

    def set_equalisation(self, pol_index, init_coeffs=None, init_poly=None, issue_spead=True):
        """ Set equalisation values to be applied pre-requantisation
        """

        reg_name = getattr(self, 'eq  %s_name' % pol_index)
        n_chans = self.config['n_chans']
        decimation = self.config['equalisation']['decimation']
        n_coeffs = n_chans / decimation

        if init_coeffs is None and init_poly is None:
            coeffs = self.get_default_equalisation(pol_index)
        elif len(init_coeffs) == n_coeffs:
            coeffs = init_coeffs
        elif len(init_coeffs) == n_chans:
            coeffs = init_coeffs[0::decimation]
            LOGGER.warn("You specified %i EQ coefficients but your system only supports %i actual values. Only writing every %ith value." % (n_chans ,n_coeffs, decimation))
        elif len(init_coeffs) > 0:
            log_runtime_error(LOGGER, 'You specified %i coefficients, but there are %i EQ coefficients required for this engine' % (len(init_coeffs), n_coeffs))
        else:
            coeffs = numpy.polyval(init_poly, range(n_chans))[decimation/2::decimation]
            coeffs = numpy.array(coeffs, dtype=complex)

        n_bytes = self.config['equalisation']['n_bytes_coeffs']
        bin_pt = self.config['equalisation']['bin_pt_coeffs']

        coeffs_str = self.float2str(coeffs, n_bytes*8, bin_pt)

        # finally write to the bram
        self.host.write(reg_name, coeffs_str)

    #TODO
    def set_delay(self, pol_index, delay=0, delay_delta=0, phase=0, phase_delta=0, load_time=None):
        """ Apply delay correction coefficients to polarisation specified from time specified
        @param pol_index: polarisation delay coefficients are to be applied to
        @param delay: delay in samples
        @param delay_delta: change in delay in samples per ADC sample
        @param phase: initial phase offset TODO units
        @param phase_delta: change in phase TODO units
        @param load_time: time to load values in ADC samples since epoch. If None load immediately
        """
        log_not_implemented_error(LOGGER,  '%s.set_delay not implemented '%self.descriptor)

'''
