# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

# things all fxcorrelator Instruments do

import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error, log_io_error, log_not_implemented_error, program_fpgas
import instrument, katcp_client_fpga, digitiser, fengine,  xengine, types

from corr2.instrument import Instrument

import struct, socket, iniparse, time, numpy

class FxCorrelator(instrument.Instrument):
    '''
    A generic FxCorrelator containing hosts of various kinds.
    '''
    def __init__(self, descriptor='fxcorrelator', config_host=None, katcp_port=None, config_file=None):
        '''
        '''
        Instrument.__init__(self, descriptor, config_host, katcp_port, config_file)
    
        # get configuration information
        self._get_fxcorrelator_config()

        self.fengines = []
        self.xengines = []

    ##############################
    ## Configuration information #
    ##############################

    def _get_fxcorrelator_config(self, filename):
        '''
        '''
        self.config['pol_map'] = {'x':0, 'y':1}
        self.config['rev_pol_map'] = {0:'x', 1:'y'}
        self.config['pols'] = ['x', 'y']

        self.config['n_ants']               = self.config_portal.get_int(['%s'%self.descriptor, 'n_ants'])

        fptr.close()

    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        if name == 'n_ants':
            return self.config['n_ants']       
        if name == 'n_xengines':
            return self.config['n_ants']       
 
        return Instrument.__getattribute__(self, name)

    ###################################
    # Host creation and configuration #
    ###################################

    def fxcorrelator_initialise(set_eq=True, fft_shift=True, issue_spead=True):
        '''
        '''
        # set up the basics of the Instrument we are part of
        self.instrument_initialise()

        if fft_shift:
            self.set_fft_shift()

        if set_eq:
            self.set_equalisation()

        if issue_spead:
            self.fxcorrelator_issue_spead()        

    ###########################
    # f and x engine creation #
    ###########################

    def fxcorrelator_create_engines_of_type(self, engine_type):
        ''' Create the fengines that make up this FX correlator.
        '''
        fengines = []
        if engine_type == 'f':       
            for fengine_index in range(self.n_ants):
                engine = self.create_fengine(fengine_index)
            # from an fxcorrelator's view, it is important that these are in order
            fengines.append(engine)  
        elif engine_type == 'x':
            for xengine_index in range(len(self.n_xengines)):
                engine = self.create_fengine(fengine_index)
            # from an fxcorrelator's view, it is important that these are in order
            fengines.append(engine)  

    def create_fengine(self, ant_id):
        '''Create the fengines that make up this FX correlator.
           Overload in decendant class
        '''
        log_not_implemented_error(LOGGER, '%s.create_fengine not implemented'%self.descriptor)

    def create_xengine(self):
        ''' Create the xengines that make up this FX correlator.
        '''
        log_not_implemented_error(LOGGER, '%s.create_xengine not implemented'%self.descriptor)

    ########################
    # operational commands #
    #######################

    def ant_str_to_tuples(self, ant_str):
        ''' Get (ant_index, pol_index) tuples corresponding to ant_str
        '''
#        if ant_str == all:
#        else:
#            #TODO

    def ant_str_to_pol(self, ant_str):
        '''
        '''

    def check_katcp_connections(self):
        '''Ping hosts to see if katcp connections are functioning.
        '''
        return (False not in self.ping_hosts().values())
   
    def set_equalisation(self, ant_str=all, init_poly=[], init_coeffs=[], issue_spead=True):
        ''' Set equalisation values for specified antenna to polynomial or coefficients specified
        '''
        # get engines responsible
        ftuples = self.ant_str_to_fengines(ant_str)
            
        for fengine, pol_id in ftuples:
            fengine.set_equalisation(pol_id, init_coeffs, init_poly, send_spead)
   
#        if issue_spead:
#            #TODO

    def calculate_integration_time(self):
        '''Calculate the number of accumulations and integration time for this system.
        '''
        self.config['n_accs'] = self.config['acc_len'] * self.config['xeng_acc_len']
        self.config['int_time'] = float(self.config['n_chans']) * self.config['n_accs'] / self.config['bandwidth']

    def calculate_bandwidth(self):
        '''Determine the bandwidth the system is processing.
        The ADC on the running system must report how much bandwidth it is processing.
        '''
        raise NotImplementedError

    def probe_fhosts(self):
        '''Read information from the F-host hardware.
        '''
        raise NotImplementedError

    def probe_xhosts(self):
        '''Read information from the X-host hardware.
        '''
        raise NotImplementedError

    def connect(self):
        '''Connect to the correlator and test connections to all the nodes.
        '''
        return self.ping_hosts()

    def set_destination(self, txip_str=None, txport=None, spead=True):
        '''Set destination for output of fxcorrelator.
        '''
        raise NotImplementedError
    
    def start_tx(self):
        '''Turns on output pipes to start data flow from xengines
           All necessary links are enabled 
        '''
        raise NotImplementedError
    
    def stop_tx(self, stop_f=False, spead=True):
        '''Turns off output pipes to start data flow from xengines
        @param stop_f: stop output of fengines too
        '''
        # does not make sense to stop only certain xengines
        for xhost in self.xengines:
            xhost.stop_tx()

        # TODO (leave fengines running?) 
        if stop_f:
            for fengine in self.fengines:
                fengine.stop_tx()

    #TODO
    def issue_spead(self):
        '''All fxcorrelators issued SPEAD in the same way, with tweakings that
           are implemented by the child class
        '''
        #TODO


# end
