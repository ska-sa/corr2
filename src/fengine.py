# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error, log_not_implemented_error 

class Fengine():
    ''' An f-engine, no matter where it is located. Channelises data from
        an antenna input in preparation for producing cross-multiplication products
        using an x-engine.
    '''

    def __init__(self, ant_id):
        ''' Constructor 
        @param ant_id: antenna input identity of data being processed
        @param descriptor: section in config to locate engine specific info at
        '''
        msg = 'ant_id must be a positive integer'
        if not isinstance(ant_id, int):
            log_runtime_error(LOGGER, msg)

        if not ant_id >= 0:
            log_runtime_error(LOGGER, msg)

        self.ant_id = ant_id

        # all fengines must have a config_portal to access configuration information
        if not hasattr(self, 'config_portal'):
            log_runtime_error(LOGGER, 'Fengines can only be ancestors in companion with Engines with config_portals')
        
        self._get_fengine_config()  

    def _get_fengine_config(self):
        ''' Get configuration info common to all fengines
        '''
        self.config['n_chans'] = self.config_portal.get_int(['%s' %self.descriptor, 'n_chans'])

        # delay tracking
        self.config['min_ld_time'] = self.config_portal.get_float(['delay_tracking', 'min_ld_time'])
        self.config['network_latency_adjust'] = self.config_portal.get_float(['delay_tracking', 'network_latency_adjust'])

    def set_delay(self, delay=0, delay_delta=0, phase=0, phase_delta=0, load_time=None):
        ''' Apply delay correction coefficients to polarisation specified from time specified
        @param delay: delay in samples
        @param delay_delta: change in delay in samples per ADC sample 
        @param phase: initial phase offset TODO units
        @param phase_delta: change in phase TODO units
        @param load_time: time to load values in ADC samples since epoch. If None load immediately
        '''
        log_not_implemented_error(LOGGER, '%s.set_delay not implemented' %self.descriptor)

# end
