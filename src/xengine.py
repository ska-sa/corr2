# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from katcp_client_fpga import KatcpClientFpga

class Xengine(KatcpClientFpga):
    '''
    An X-engine, regardless of where it is located.
    '''
    def __init__(self, host, port=7147):
        '''Constructor.
        '''
        KatcpClientFpga.__init__(self, host, port)

        self.xeng_sample_bits = 32 # FROM DESIGN

        LOGGER.info('New Xengine created @ %s:%i.',
            self.host, self.katcp_port)

    def __str__(self):
        return 'xengine @ %s : %s' % (self.host, self.katcp_port)
# end
