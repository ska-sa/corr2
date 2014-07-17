import logging
from fengine import Fengine
from engine_fpga import EngineCasperFpga

LOGGER = logging.getLogger(__name__)


class FengineCasperFpga(Fengine, EngineCasperFpga):
    """ An fengine that is also an engine using an FPGA as a host
        Data from two polarisations are received via SPEAD, channelised, equalised pre-requantisation, corner-turned
        and transmitted via SPEAD. Delay correction is applied via coarse delay before channelisation and phase
        rotation post channelisation.
    """
    def __init__(self, fpga_host, engine_id, ant_id, config_source):
        """
        @param fpga_host: fpga-bsed Host device
        @param engine_id: index of fengine on FPGA
        """
        Fengine.__init__(self, fpga_host, engine_id, ant_id, config_source)
        EngineCasperFpga.__init__(self, fpga_host, engine_id, config_source)
        LOGGER.info('%s %s initialised', self.__class__.__name__, str(self))

    def update_config(self, config_source):
        """
        Update necessary values from a config dictionary/server
        :return:
        """
        self.sample_bits = int(config_source['fengine']['sample_bits'])
        self.adc_demux_factor = int(config_source['fengine']['adc_demux_factor'])
        self.bandwidth = int(config_source['fengine']['bandwidth'])
        self.true_cf = int(config_source['fengine']['true_cf'])
        self.n_chans = int(config_source['fengine']['n_chans'])
        self.min_load_time = int(config_source['fengine']['min_load_time'])
        self.network_latency_adjust = int(config_source['fengine']['network_latency_adjust'])
        self.n_pols = int(config_source['fengine']['num_pols'])

        # TODO
        # self.control_reg = self.host.registers['control%d' % self.engine_id]
        # self.status_reg = self.host.registers['status%d' % self.engine_id]
        self.control_reg = None
        self.status_reg = None

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

    #######################
    # FFT shift schedule  #
    #######################

    def set_fft_shift(self, shift_schedule=None, issue_meta=True):
        """ Set the FFT shift schedule
        @param shift_schedule: int representing bit mask. '1' represents a shift for that stage. First stage is MSB. Use default if None provided
        """
        if shift_schedule is None:
            shift_schedule = self.config['fft_shift']
        self.fft_shift.write(fft_shift=shift_schedule)

        # TODO issue_meta

    def get_fft_shift(self):
        """ Get the current FFT shift schedule
        @return bit mask in the form of an unsigned integer
        """
        return self.fft_shift.read()['data']['fft_shift']
    
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
