# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2.engine import Engine

import iniparse

class Fengine(Engine):
    ''' An F-engine  
    '''

    def __init__(self, parent, engine_id, config_file=None, descriptor='f-engine'):
        ''' Constructor 
        '''
        Engine.__init__(self, parent, engine_id, descriptor)

    #TODO generic fengine stuff

# end
