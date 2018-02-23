import logging
import time

from casperfpga.casperfpga import CasperFpga
from casperfpga.network import Mac

LOGGER = logging.getLogger(__name__)


class FpgaHost(CasperFpga):
    """
    A Host that is a CASPER FPGA, ROACH2 or SKARAB.
    """

    def setup_host_gbes(self, logger, info_dict):
        """
        Set up the gbe ports on hosts
        :param logger: a logger instance
        :param info_dict: a dictionary with the port and hoststr for this
        fpga host
        :return:
        """
        port = info_dict[self.host][0]
        hoststr = info_dict[self.host][1]
        for gbe in self.gbes:
            if gbe.block_info['tag'] == 'xps:forty_gbe':
                # this is not applicable for SKARAB forty gbe ports
                gbe.set_port(30000)
                gbe.fabric_enable()
                continue
            if gbe.block_info['flavour'] == 'sfp+':
                mac_ctr = int(gbe.block_info['slot']) * 4 + int(
                    gbe.block_info['port_r2_sfpp'])
            else:
                raise RuntimeError(
                    'Non-SFP+ network link configurations '
                    'are not supported!')
            this_mac = Mac.from_roach_hostname(self.host, mac_ctr)
            gbe.setup(mac=this_mac, ipaddress='0.0.0.0', port=port)
            logger.info('%s(%s) gbe(%s) mac(%s) port(%i)' %
                        (hoststr, self.host, gbe.name, str(gbe.mac),
                         port))
            # gbe.tap_start(restart=True)
            gbe.dhcp_start()

# end
