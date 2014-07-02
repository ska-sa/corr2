import logging
LOGGER = logging.getLogger(__name__)

from casperfpga.misc import log_runtime_error, log_io_error, log_not_implemented_error

from corr2.fxcorrelator_fpga import FxCorrelatorFpga
from corr2.wb_rts_fengine import WbRtsFengine
from corr2.wb_rts_xengine import WbRtsXengine

class MockRts(FxCorrelatorFpga):
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

        # settings required by FxCorrealatorFpga
        n_ants = self.config_portal.get_int(['%s'%self.descriptor, 'n_ants'])
        self.config['n_ants'] = n_ants
        self.n_ants = n_ants

        self.n_xengines = self.config['engines']['rts_xengine']['n_engines']

        self.f_per_host = self.config['engines']['wb_rts_fengine']['engines_per_host']
        self.x_per_host = self.config['engines']['rts_xengine']['engines_per_host']

        # the base address xengines are located at
        self.x_ip_base = self.config['engines']['rts_xengine']['ip_base']
        # the port to send things to the fabric on
        self.x_port = self.config['engines']['rts_xengine']['port']

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
        if engine_type == 'wb_rts_fengine' or engine_type == 'rts_xengine':
            # use default instrument setup
            self.instrument_setup_hosts_for_engines_of_type(engine_type)

        #TODO dengine
   
    ######################
    # host link creation #   
    ######################
    def create_host_links_for_engines_of_type(self, engine_type):

        #call generic
        host_links = self.instrument_create_host_links_for_engines_of_type(engine_type)
        if engine_type == 'wb_rts_fengine':
            self.fhosts = host_links.values()
        elif engine_type == 'rts_xengine':
            self.xhosts = host_links.values()

        return host_links

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
        if engine_type == 'wb_rts_fengine':
            # these are the fengines for the fxcorrelator
            fengines = self.create_fengines()
            return fengines
        elif engine_type == 'rts_xengine':
            # these are xengines for the fxcorrelator
            xengines = self.create_xengines()
            return xengines
        #TODO dengine

        return []

    def create_fengine_fpga(self, ant_id, host_link, engine_index):
        ''' Create an fengine
        '''

        feng = WbRtsFengine(ant_id, host_link, engine_index, self)
        return feng

    def create_xengine_fpga(self, host_link, engine_index):
        ''' Create an xengine
        '''
        
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


