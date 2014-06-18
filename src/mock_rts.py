import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error, log_io_error, log_not_implemented_error, program_fpgas
import instrument, katcp_client_fpga, digitiser, fengine,  xengine, types

from corr2.fxcorrelator import FxCorrelator
from corr2.wb_rts_fengine import WbRtsFengine
from corr2.wb_rts_xengine import WbRtsXengine

import struct, socket, iniparse, time, numpy

class MockRts(fxcorrelator.FxCorrelator):
    '''
    '''

    def __init__(self, descriptor='mock_rts', config_file=None):
        '''
        '''
        FxCorrelator.__init__(descriptor, config_host=0, katcp_port=None, config_file=config_file)
#    def __init__(self, descriptor='fxcorrelator', config_host=None, katcp_port=None, config_file=None):

        self.mock_rts_config()

    def mock_rts_config(self):
        '''
        '''
        self.config['n_xengines'] = self.config['engines']['rts_xengine']['n_engines']

    def initialise(self, fft_shift=True, set_eq=True, issue_spead=True):
        '''
        '''
        self.fxcorrelator_initialise(fft_shift, set_eq, issue_spead)
        


    def create_engines_of_type(self):
        ''' Create the engines that make up this FX correlator.
        '''
        self.create_fengines()
        self.create_xengines()

    def create_engines_of_type(self, engine_type):
        ''' Create a new engine of specified type using link provided and info
            This should be created in instrument being implemented as it helps
            generic instruments create engines with the same capabilities
        ''' 
        engines = []

        for engine_index in number:
            if descriptor == 'wb_rts_f':
                engine = self.fxcorrelator_create_engines_of_type('f')
            elif descriptor == 'wb_rts_x':
                engine = self.fxcorrelator_create_engines_of_type('x')
            #TODO
#            elif descriptor = 'mock_rts_lband_d':
#                engine = WbRtsFengine(0, host_link, engine_index, self)
            engines.extend(engine)
        return engines

    def create_fengine(self, ant_id):
        '''Create an fengine that makes up this FX correlator
        '''
        if len(self.f_host_links) > ant_id:
            log_runtime_error(LOGGER, 'Trying to create an fengine greater than the number of host_links we have')

        # we expect self.f_host_links to maintain the same order over time
        host_link = self.f_host_links[ant_id]
        # index in FPGA is related to 
        engine_index = 1

        feng = WbRtsFengine(ant_id, host_link, engine_index, self)

    def create_xengine(self):
        ''' Create the xengines that make up this FX correlator.
        '''
        # we expect self.x_host_links to maintain the same order over time
        # so we assign the xengine to an index one higher than what we have 
        # in the system
        
#        host_link = self.x_host_links[len(self.xengines)]
        
#        engine_index = 1
#        xeng = WbRtsXengine(host_link, engine_index, self)
#        log_not_implemented_error(LOGGER, '%s.create_xengine not implemented'%self.descriptor)

    def issue_spead(self):
        '''
        '''
    
    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        if name == 'hosts':
            tmp = {}
            tmp.update(self.fhosts)
            tmp.update(self.xhosts)
            return tmp
        elif name == 'fpga_hosts':
            tmp = {}
            for host in self.hosts.values():
                if isinstance(host, KatcpClientFpga):
                    tmp.update({host.host: host})
            return tmp  
        elif name == 'f_per_host':
            return self.config['engines']['wb_rts_fengine']['engines_per_host']
        elif name == 'x_per_host':
            return self.config['engines']['rts_xengine']['engines_per_host']
        elif name == 'f_host_links':     
            return self.host_links['wb_rts_fengine'].values()
        elif name == 'x_host_links':     
            return self.host_links['rts_xengine'].values()
        return FxCorrelator.__getattribute__(self, name)
        

