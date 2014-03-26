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
    i.e. an f-engine on an fpga, or an x-engine on a gpu
    '''
    def __init__(self, parent, descriptor='engine'):
        '''Constructor
        @param parent: an object that hosts this engine
        '''
        self.parent = parent
        self.descriptor = descriptor

    def __str__(self):
        return '%s @ %s' % (self.descriptor, self.parent)
# end
