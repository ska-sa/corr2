# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

import engine

class Xengine(engine.Engine):
    '''
    An X-engine, regardless of where it is located.
    '''
    def __init__(self, xengine_id):
        '''Constructor.
        '''
        engine.Engine.__init__(self, engine_id=xengine_id)

        self.xeng_sample_bits = 32 # FROM DESIGN

        LOGGER.info('New Xengine(%i) created.', xengine_id)

    def __str__(self):
        return 'xengine %i @ %s' % (self.engine_id, self.host)
# end
