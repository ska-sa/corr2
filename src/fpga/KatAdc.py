'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

class KatAdc(object):
    '''Information above KatAdc yellow blocks.
    '''
    def __init__(self, parent, name):
        '''
        @param parent: The owner of this block.
        @param name: The name of this block.
        @param kwargs: Other keyword args
        '''
        self.parent = parent
        self.name = name
        self.options = {}
        logger.info('New KatADC %s' % self.name)

    def update_info(self, info):
        '''Set this memory's extra information.
        '''
        print 'dfgdssfd'
        self.options = info

# end