'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

class Engine(object):
    '''
    A compute engine of some kind
    '''
    def __init__(self, engine_id):
        '''Constructor. Duplicate engine ids in a system are a really bad idea.
        '''
        self.id = engine_id

# end
