import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error, log_io_error, log_not_implemented_error

from corr2.fxcorrelator_fpga import FxCorrelatorFpgs
from corr2.wb_rts_fengine import WbRtsFengine
from corr2.wb_rts_xengine import WbRtsXengine

class MockRts(FxCorrelator):
    '''
    '''

    def __init__(self, config_file, descriptor='mock_rts'):
        '''
        '''
        FxCorrelatorFpga.__init__(self, descriptor, None, None, config_file)

        self.mock_rts_config()

    def mock_rts_config(self):
        '''
        '''
    
    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        # the base address xengines are located at
        if name == 'x_ip_base':
            return self.config['engines']['rts_xengine']['ip_base']
        # the port to send things to the fabric on
        elif name == 'x_port':
            return self.config['engines']['rts_xengine']['port']
        elif name == 'f_per_host':
            return self.config['engines']['wb_rts_fengine']['engines_per_host']
        elif name == 'x_per_host':
            return self.config['engines']['rts_xengine']['engines_per_host']
        elif name == 'n_ants':
            return self.config['engines']['wb_rts_fengine']['n_engines']       
        elif name == 'n_xengines':
            return self.config['engines']['wb_rts_xengine']['n_engines']       

        return FxCorrelatorFpga.__getattribute__(self, name)

    def initialise(self, configure_hosts=True, setup_hosts=True, fft_shift=True, set_eq=True, start_tx_f=True, issue_meta=True):
        '''
        '''
        # do generic instrument setup first
        self.fxcorrelator_fpga_initialise(configure_hosts=configure_hosts, setup_hosts=setup_hosts, fft_shift=fft_shift, set_eq=set_eq, start_tx_f=start_tx_f, issue_meta=issue_meta)
  
    ##############
    # Host setup #
    ##############

    def setup_hosts_for_engines_of_type(self, engine_type):
        ''' 
        '''
        # we know that these engines can be set up in a standard fashion
        if engine_type == 'wb_rts_f' or engine_type == 'rts_x':
            # use default instrument setup
            self.instrument_setup_hosts_for_engines_of_type(engine_type)

        #TODO dengine

    ###################
    # Engine creation #
    ###################

    # needed by Instrument
    def create_engines_of_type(self, engine_type):
        ''' Create a new engine of specified type using link provided and info
            This should be created in instrument being implemented as it helps
            generic instruments create engines with the same capabilities
        ''' 

        # we know that these engines are what the fxcorrelator knows of as f engines so call it
        # It will call our create_fengine method in turn
        if engine_type == 'wb_rts_f':
            # these are the fengines for the fxcorrelator
            self.create_fengines()
            return self.fengines
        elif engine_type == 'wb_rts_x':
            # these are xengines for the fxcorrelator
            self.create_xengines()
            return self.xengines
        #TODO dengine

    def create_fengine(self, ant_id):
        ''' Create an fengine
        '''
        if len(self.f_host_links) > ant_id:
            log_runtime_error(LOGGER, 'Trying to create an fengine greater than the number of host_links we have')

        # we expect self.f_host_links to maintain the same order over time
        host_link = self.f_host_links[ant_id]
        # index in FPGA is related to 
        engine_index = 1

        feng = WbRtsFengine(ant_id, host_link, engine_index, self)
        return feng

    def create_xengine(self):
        ''' Create an xengine
        '''
        # we expect self.x_host_links to maintain the same order over time
        # so we assign the xengine to an index one higher than what we have 
        # in the system
        
        n_xengs = len(self.xengines)
        host_link = self.x_host_links[n_xengs]
        engine_index = n_xengs%self.x_per_host
        
        xeng = WbRtsXengine(host_link, engine_index, self)
        return xeng

    ####################
    # Normal operation #
    ####################

    def issue_meta(self):
        '''
        '''
        # use the generic fxcorrelator SPEAD meta data issue command
        self.fxcorrelator_fpga_issue_meta()
    
        #issue our specific stuff


