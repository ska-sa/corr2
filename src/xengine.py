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
    def __init__(self, f_offset):
        '''Constructor.
        @param f_index: the index of the band of frequencies this engine processes
        '''
        if not isinstance(f_offset, int):
            log_runtime_error(LOGGER, "f_index must be an integer")        

        #TODO more checking of f_offset
        self.f_offset = f_offset

# end
