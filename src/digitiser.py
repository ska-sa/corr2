"""
@author: paulp
"""

import logging
from casperfpga import KatcpClientFpga

LOGGER = logging.getLogger(__name__)


class Digitiser(KatcpClientFpga):
    def __init__(self, host_device, port=7147):
        KatcpClientFpga.__init__(self, host_device, port)
        LOGGER.info('New Digitiser created - %s', str(self))

    def __str__(self):
        return 'digitiser %s @ %i' % (self.host, self.katcp_port)
