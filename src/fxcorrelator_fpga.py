import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error, log_io_error, log_not_implemented_error, log_value_error
import instrument, fengine,  xengine

from corr2.instrument import Instrument
from corr2.fxcorrelator import FxCorrelator

import struct, socket, iniparse, time, numpy

class FxCorrelatorFpga(FxCorrelator, Instrument):
    ''' FX Correlator implemented using FPGAs
    '''

    def __init__(self, descriptor='fxcorrelator_fpga', config_host=None, katcp_port=None, config_file=None):
        '''
        '''
        Instrument.__init__(self, descriptor, config_host, katcp_port, config_file)
        FxCorrelator.__init__(self)

        self.fxcorrelator_fpga_config()

    def fxcorrelator_fpga_config(self):
        '''
        '''
        self.config['pol_map'] = {'x':0, 'y':1}
        self.config['rev_pol_map'] = {0:'x', 1:'y'}
        self.config['pols'] = ['x', 'y']
    
    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        return Instrument.__getattribute__(self, name)

    def fxcorrelator_fpga_initialise(self, configure_hosts=True, setup_hosts=True, fft_shift=True, set_eq=True, start_tx_f=True, issue_meta=True):
        '''
        '''
        # do generic instrument setup first
        # creating links to hosts, configuring hosts, creating processing engines
        self.instrument_initialise(configure_hosts=configure_hosts, setup_hosts=setup_hosts)

        # do some basic engine configuration
        if fft_shift:
            self.set_fft_shift()

        if set_eq:
            self.set_equalisation()

        # do generic fxcorrelator stuff like
        # turning on output of fengines, setting up vector accumulators etc
        self.fxcorrelator_initialise(start_tx_f=start_tx_f, issue_meta=issue_meta)

        if issue_meta:
            self.fxcorrelator_fpga_issue_meta()

    ##############
    # Host setup #
    ##############

    def setup_hosts_for_engines_of_type(self, engine_type):
        ''' Instruments must do this themselves based on instrument and engine type
        '''
        log_not_implemented_error(LOGGER, '%s.setup_hosts_for_engines_of_type not implemented'%self.descriptor)
    
    ###################
    # Engine creation #
    ###################

    def create_engines_of_type(self, engine_type):
        ''' Create a new engine of specified type using link provided and info
            This should be created in instrument being implemented as it helps
            generic instruments create engines with the same capabilities
        ''' 
        log_not_implemented_error(LOGGER, '%s.create_engines_of_type not implemented'%self.descriptor)

    ####################
    # Normal operation #
    ####################

    def ant_str_to_tuples(self, ant_str=all):
        ''' Get (ant_index, pol_index) tuples corresponding to ant_str
        '''
        if not (len(self.fengines) == self.n_ants):
            log_runtime_error(LOGGER, 'The number of fengines in our system (%d) does not match the number required (%d)'%(len(self.fengines), self.n_ants))
        
        tuples = []
        if ant_str==all:
            for ant_index in range(self.n_ants):
                for pol_index in range(len(self.config['pols'])):
                    tuples.append((self.fengines[ant_index], pol_index))
        else:
            #polarisation must be single character and in pol_map
            pol = ant_str[len(ant_str)-1]
            pol_index = self.config['pol_map'].get(pol)
            if pol_index == None:
                log_value_error(LOGGER, '%s not a valid polarisation label for %s'%(pol, self.descriptor))
            
            #antenna index must be natural number smaller than the ants we have
            ant = ant_str[0:len(ant_str)-1] 
            try:
                ant_index = int(ant)
            except ValueError:
                log_value_error(LOGGER, '%s cannot be converted to an integer'%(ant))

            if ant_index < 0 or ant_index >= self.n_ants:
                log_runtime_error(LOGGER, '%d is not a valid antenna index in %s'%(ant_index, self.descriptor))

            tuples.append((self.fengines[ant_index], pol_index))

        return tuples

    def set_fft_shift(self, ant_str=all, shift_schedule=None, issue_meta=True):
        ''' Set the FFT shift schedule
        @param shift_schedule: int representing shift bit mask. First stage is MSB. Use default if None provided
        @param ant_str: the antenna input to set the schedule for
        '''

    def set_equalisation(self, ant_str=all, init_poly=None, init_coeffs=None, issue_meta=True):
        ''' Set equalisation pre requantisation values for specified antenna to polynomial or coefficients specified
        '''
        # get engines responsible
        ftuples = self.ant_str_to_tuples(ant_str)
            
        for fengine, pol_id in ftuples:
            fengine.set_equalisation(pol_id, init_coeffs, init_poly, issue_meta)

    def fxcorrelator_fpga_issue_meta(self):
        '''
        '''
        # use the generic fxcorrelator SPEAD meta data issue command
        self.fxcorrelator_issue_meta()
    
        #issue our specific SPEAD metadata stuff


