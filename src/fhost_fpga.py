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
        self.data_sources = []

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

    def check_rx(self, max_waittime=30):
        """
        Check the receive path on this f host
        :param max_waittime: the maximum time to wait for raw 10gbe data
        :return:
        """
        self.check_rx_raw(max_waittime)
        self.check_rx_spead()
        self.check_rx_reorder()

    def check_rx_reorder(self):
        """
        Is this F host reordering received data correctly?
        :return:
        """
        def get_gbe_data():
            data = {}
            for pol in [0, 1]:
                reord_errors = self.registers['updebug_reord_err%i' % pol].read()['data']
                data['re%i_cnt' % pol] = reord_errors['cnt']
                data['re%i_time' % pol] = reord_errors['time']
                data['re%i_tstep' % pol] = reord_errors['timestep']
                data['timerror%i' % pol] = reord_errors['timestep']
            valid_cnt = self.registers.updebug_validcnt.read()['data']
            data['valid_arb'] = valid_cnt['arb']
            data['valid_reord'] = valid_cnt['reord']
            data['mcnt_relock'] = self.registers.mcnt_relock.read()['data']['reg']
            temp = self.registers.pfb_of.read()['data']
            data['pfb_of0'] = temp['of0']
            data['pfb_of1'] = temp['of1']
            return data
        rxregs = get_gbe_data()
        time.sleep(1)
        rxregs_new = get_gbe_data()
        if rxregs_new['valid_arb'] == rxregs['valid_arb']:
            raise RuntimeError('F host %s arbiter is not counting packets.' % self.host)
        if rxregs_new['valid_reord'] == rxregs['valid_reord']:
            raise RuntimeError('F host %s reorder is not counting packets.' % self.host)
        if rxregs_new['pfb_of1'] > rxregs['pfb_of1']:
            raise RuntimeError('F host %s PFB 1 reports overflows.' % self.host)
        if rxregs_new['mcnt_relock'] > rxregs['mcnt_relock']:
            raise RuntimeError('F host %s mcnt_relock is triggering.' % self.host)
        for pol in [0, 1]:
            if rxregs_new['pfb_of%i' % pol] > rxregs['pfb_of%i' % pol]:
                raise RuntimeError('F host %s PFB %i reports overflows.' % (self.host, pol))
            if rxregs_new['re%i_cnt' % pol] > rxregs['re%i_cnt' % pol]:
                raise RuntimeError('F host %s reorder count error.' % (self.host, pol))
            if rxregs_new['re%i_time' % pol] > rxregs['re%i_time' % pol]:
                raise RuntimeError('F host %s reorder time error.' % (self.host, pol))
            if rxregs_new['re%i_tstep' % pol] > rxregs['re%i_tstep' % pol]:
                raise RuntimeError('F host %s timestep error.' % (self.host, pol))
            if rxregs_new['timerror%i' % pol] > rxregs['timerror%i' % pol]:
                raise RuntimeError('F host %s time error?.' % (self.host, pol))
        LOGGER.info('F host %s is reordering data okay.' % self.host)

    def read_spead_counters(self):
        """
        Read the SPEAD rx and error counters for this F host
        :return:
        """
        rv = []
        for core_ctr in range(0, 4):
            counter = self.registers['updebug_sp_val%i' % core_ctr].read()['data']['reg']
            error = self.registers['updebug_sp_err%i' % core_ctr].read()['data']['reg']
            rv.append((counter, error))
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
        :param eq_poly: The eq polynomial to apply to this source
        :return:
        """
        for source in self.data_sources:
            assert source.source_number != data_source.source_number
            assert source.name != data_source.name
        data_source.eq_bram = 'eq%i' % len(self.data_sources)
        self.data_sources.append(data_source)

    def get_source_eq_all(self):
        rv = {}
        for source in self.data_sources:
            rv[source.name] = source.get_eq(hostdevice=self)
        return rv

    def set_source_eq_all(self, complex_gain_list=None):
        """
        Set the gains for all sources on this fhost from a provided complex gain table
        :param complex_gain_list: a list of gains, ONE per source GLOBALLY,
        :return:
        """
        for source in self.data_sources:
            source.set_eq(complex_gain_list[source.source_number] if complex_gain_list is not None else None, self)
        # TODO issue_meta

    def read_eq(self, eq_bram):
        """
        Read a given EQ BRAM.
        :param eq_bram:
        :return:
        """
        # eq vals are packed as 32-bit complex (16 real, 16 imag)
        eqvals = self.read(eq_bram, self.n_chans*4)
        eqvals = struct.unpack('>%ih' % (self.n_chans*2), eqvals)
        eqcomplex = []
        for ctr in range(0, len(eqvals), 2):
            eqcomplex.append(eqvals[ctr] + (1j * eqvals[ctr+1]))
        return eqcomplex

    def write_eq(self, eq_poly, bram):
        """
        Write a given complex eq to the given SBRAM.
        :param eq_poly: an integer, complex number or list
        :param bram: the bram to which to write
        :return:
        """
        try:
            assert len(eq_poly) == self.n_chans
            creal = [num.real for num in eq_poly]
            cimag = [num.imag for num in eq_poly]
        except TypeError:
            # the eq_poly is an int or complex
            creal = self.n_chans * [int(eq_poly.real)]
            cimag = self.n_chans * [int(eq_poly.imag)]
        coeffs = (self.n_chans * 2) * [0]
        coeffs[0::2] = creal
        coeffs[1::2] = cimag
        ss = struct.pack('>%ih' % (self.n_chans * 2), *coeffs)
        self.write(bram, ss, 0)
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
        # TODO issue_meta

    def get_fft_shift(self):
        """
        Get the current FFT shift schedule from the FPGA.
        :return: integer representing the FFT shift schedule for all the FFTs on this engine.
        """
        return self.host.registers.fft_shift.read()['data']['fft_shift']

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
