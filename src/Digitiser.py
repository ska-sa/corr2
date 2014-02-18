'''
@author: paulp
'''

import logging
import katcpclientfpga

logger = logging.getLogger(__name__)

class Digitiser(katcpclientfpga.KatcpClientFpga):
    def __init__(self, host, port=7147):
        katcpclientfpga.KatcpClientFpga.__init__(self, host, host, port)
        logger.info('New Digitiser created - %s' % str(self))

    def __str__(self):
        return 'digitiser %s @ %i' % (self.host, self.katcp_port)
