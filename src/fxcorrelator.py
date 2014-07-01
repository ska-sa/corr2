# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

# things all fxcorrelators Instruments do

import logging
LOGGER = logging.getLogger(__name__)

from casperfpga.misc import log_not_implemented_error

class FxCorrelator():
    '''
    A generic FxCorrelator composed of fengines that channelise antenna inputs and xengines that each produce cross products 
    from a continuous portion of the channels and accumulate the result. SPEAD data products are produced.
    '''
    def __init__(self):
        '''
        '''
        # all fxcorrelators must have a config_portal to access configuration information
        if not hasattr(self, 'config_portal'):
            log_runtime_error(LOGGER, 'FxCorrelators can only be ancestors in companion with Instruments with config_portals')
    
        # get configuration information
        self._get_fxcorrelator_config()

        self.fengines = []
        self.xengines = []

    ##############################
    ## Configuration information #
    ##############################

    def _get_fxcorrelator_config(self):
        '''
        '''

    ###################################
    # Host creation and configuration #
    ###################################

    def fxcorrelator_initialise(start_tx_f=True, issue_meta=True):
        '''
        @param start_tx_f: start f engine transmission
        '''

        #set up and start output from fengines
        if start_tx_f: 
            ip_base = self.x_ip_base
            port = self.x_port

            #turn on fengine outputs
            for fengine in self.fengines:
                #we will wait to issue spead meta data if initialising
                fengine.set_txip(ip_base, issue_meta=False) 
                fengine.set_txport(port, issue_meta=False) 

                #turn on transmission
                fengine.start_tx()

        if issue_meta:
            self.fxcorrelator_issue_meta()        

    ###########################
    # f and x engine creation #
    ###########################

    def create_fengines(self):
        for fengine_index in range(self.n_ants):
            engine = self.create_fengine(fengine_index)
        # from an fxcorrelator's view, it is important that these are in order
        self.fengines.append(engine) 
    
    def create_xengines(self):
        for xengine_index in range(self.n_xengines):
            engine = self.create_xengine(xengine_index)
        # from an fxcorrelator's view, it is important that these are in order
        self.xengines.append(engine)  

    # the specific fxcorrelator must know about it's specific f and x engine components
    def create_fengine(self, ant_id):
        '''Create an fengine.
           Overload in decendant class
        '''
        log_not_implemented_error(LOGGER, '%s.create_fengine not implemented'%self.descriptor)

    def create_xengine(self):
        ''' Create an xengine.
        '''
        log_not_implemented_error(LOGGER, '%s.create_xengine not implemented'%self.descriptor)

    ########################
    # operational commands #
    ########################
    
    # These can all be done with generic f and xengine commands

    def check_host_links(self):
        '''Ping hosts to see if katcp connections are functioning.
        '''
        return (False in self.ping_hosts().values())

    def calculate_integration_time(self):
        '''Calculate the number of accumulations and integration time for this system.
        '''
        log_not_implemented_error(LOGGER, '%s.calculate_integration_time not implemented'%self.descriptor)

    def calculate_bandwidth(self):
        '''Determine the bandwidth the system is processing.
        The ADC on the running system must report how much bandwidth it is processing.
        '''
        log_not_implemented_error(LOGGER, '%s.calculate_bandwidth not implemented'%self.descriptor)

    def connect(self):
        '''Connect to the correlator and test connections to all the nodes.
        '''
        return self.ping_hosts()

    def set_destination(self, txip_str=None, txport=None, issue_meta=True):
        '''Set destination for output of fxcorrelator.
        '''
        if txip_str == None:
            txip_str = self.config['txip_str']

        if txport == None:
            txport = self.config['txport']

        #set destinations for all xengines
        for xengine in self.xengines:
            xengine.set_txip(txip_str)
            xengine.set_txport(txport)

#TODO   
#        if issue_meta:
 
    def start_tx(self):
        ''' Turns on xengine output pipes needed to start data flow from xengines
        '''
        #turn on xengine outputs
        for xengine in self.xengines:
            xengine.start_tx()
    
    def stop_tx(self, stop_f=False, issue_meta=True):
        '''Turns off output pipes to start data flow from xengines
        @param stop_f: stop output of fengines too
        '''
        # does not make sense to stop only certain xengines
        for xengine in self.xengines:
            xengine.stop_tx()

        if stop_f:
            for fengine in self.fengines:
                fengine.stop_tx()

    def fxcorrelator_issue_meta(self):
        '''All fxcorrelators issued SPEAD in the same way, with tweakings that
           are implemented by the child class
        '''
        #TODO
        log_not_implemented_error(LOGGER, '%s.fxcorrelator_issue_meta not implemented'%self.descriptor)

# end
