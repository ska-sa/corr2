import logging
logger = logging.getLogger(__name__)

from Fpga import Memory
import Types

class Sbram(Memory.Memory):
    '''General SBRAM memory on the FPGA.
    '''
    def __init__(self, parent, name, info=None):
        Memory.Memory.__init__(self, name=name, address=-1, width=32, length=1, direction=Types.BIDIRECTIONAL, blockpath='')
        self.update_info(info)
        logger.info('New SBRAM block - %s' % self.__str__())
    
    def update_info(self, info):
        '''Set this Sbram's extra information.
        '''
        self.options = info
