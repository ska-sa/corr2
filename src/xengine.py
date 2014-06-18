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
        '''Constructor.
        '''

# end
