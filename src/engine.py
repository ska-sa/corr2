# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

class Engine(object):
    '''
    A compute engine of some kind, hosted on something.
    '''
    def __init__(self, engine_id):
        '''Constructor
        @param engine_id: a unique id number by which to identify this engine.
        '''
        self.host = None
        self.engine_id = engine_id

    def __str__(self):
        return 'engine %i @ %s' % (self.engine_id, self.host)
# end
