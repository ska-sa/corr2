# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2.misc import log_runtime_error

class Xengine():
    '''
    An X-engine, regardless of where it is located. 
    Xengines cross multiply a subset of channels from a number of fengines and accumulate the result
    '''
    def __init__(self):
        '''Constructor
        '''

        # all fengines must have a config_portal to access configuration information
        if not hasattr(self, 'config_portal'):
            log_runtime_error(LOGGER, 'Xengines can only be ancestors in companion with Engines with config_portals')
        
        self._get_xengine_config()  
   
    def _get_xengine_config(self):
        '''
        '''
        # default accumulation length for vector accumulator
        self.config['vacc_len'] = self.config_portal.get_int(['%s' %self.descriptor, 'vacc_len'])

    def set_accumulation_length(self, accumuluation_length, issue_meta=True):
        ''' Set the accumulation time for the vector accumulator
        @param accumulation_length: the accumulation time in spectra
        @param issue_meta: issue SPEAD meta data indicating the change in time
        @returns: the actual accumulation time in spectra
        '''
        log_not_implemented_error(LOGGER, '%s.set_accumulation_length not implemented' %self.descriptor)
    
    def get_accumulation_length(self):
        ''' Get the current accumulation time of the vector accumulator
        @returns: the accumulation time in spectra
        '''
        log_not_implemented_error(LOGGER, '%s.get_accumulation_length not implemented' %self.descriptor)

# end
