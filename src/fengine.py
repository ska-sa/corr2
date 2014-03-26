# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2.engine import Engine

class Fengine(Engine):
    '''
    An F-engine, regardless of where it is located.
    '''
    def __init__(self, parent):
        '''Constructor.
        '''
        Engine.__init__(self, parent, 'f-engine')
        self.num_output_channels = -1
        LOGGER.info('%i-channel Fengine created @ %s',
            self.num_output_channels, str(self.parent))

    def eq_get(self):
        raise NotImplementedError

    def eq_set(self):
        raise NotImplementedError
# end
