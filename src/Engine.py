'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

class Engine(object):
    '''
    A compute engine of some kind.
    '''
    def __init__(self, engine_id):
        '''Constructor
        @param engine_id: a unique id number by which to identify this engine.
        '''
        self.host = None
        self.id = engine_id

    def __str__(self):
        return 'engine %i @ %s' % (self.id, self.host)
# end
