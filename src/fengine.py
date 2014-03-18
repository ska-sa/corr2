# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from katcp_client_fpga import KatcpClientFpga

class Fengine(KatcpClientFpga):
    '''
    An F-engine, regardless of where it is located.
    '''
    def __init__(self, host, port=7147):
        '''Constructor.
        '''
        KatcpClientFpga.__init__(self, host, port)
        self.num_channels = -1
        self.output_format = -1
        LOGGER.info('New %i-channel Fengine created @ %s:%i.',
            self.num_channels, self.host, self.katcp_port)

    def eq_get(self):
        raise NotImplementedError

    def eq_set(self):
        raise NotImplementedError

    def __str__(self):
        return 'fengine @ %s:%s' % (self.host, self.katcp_port)
# end
