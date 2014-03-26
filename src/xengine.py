# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2.engine import Engine

class Xengine(Engine):
    '''
    An X-engine, regardless of where it is located.
    '''
    def __init__(self, parent):
        '''Constructor.
        '''
        Engine.__init__(self, parent, 'x-engine')
        LOGGER.info('Xengine created @ %s', str(self.parent))
# end
