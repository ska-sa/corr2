import logging
import time

from casperfpga.casperfpga import CasperFpga
from casperfpga.network import Mac

LOGGER = logging.getLogger(__name__)


class FpgaHost(CasperFpga):
    """
    A Host that is a CASPER FPGA, ROACH2 or SKARAB.
    """

    def setup_host_gbes(self):
        """
        Set up the gbe ports on hosts
        :return:
        """
        for gbe in self.gbes:
            if gbe.block_info['tag'] == 'xps:forty_gbe':
                gbe.fabric_enable()
            else:
                raise RuntimeError("This gbe core is not supported!")
# end
