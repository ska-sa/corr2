'''
@author: paulp
'''

import logging
import Engine

logger = logging.getLogger(__name__)

class Fengine(Engine.Engine):
    '''
    An F-engine, regardless of where it is located.
    '''
    def __init__(self, fengine_id):
        '''Constructor.
        '''
        Engine.Engine.__init__(self, engine_id=fengine_id)
        self.length = -1
        self.output_format = -1
        logger.info('New Fengine(%i) created.' % (fengine_id))
    
    def eq_get(self):
        raise NotImplementedError
    
    def eq_set(self):
        raise NotImplementedError
    
    def __str__(self):
        return 'fengine %i @ %s' % (self.id, self.host)
# end