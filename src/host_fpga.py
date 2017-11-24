import logging
import time

from casperfpga.casperfpga import CasperFpga
from casperfpga.network import Mac

LOGGER = logging.getLogger(__name__)


class FpgaHost(CasperFpga):
    """
    A Host that is a CASPER FPGA, ROACH2 or SKARAB.
    """

    def check_rx(self):
        """
        Check the receive path on this FPGA host
        :param max_waittime: the maximum time to wait
        :return:
        """
        # check the reorder, if it fails, go lower
        if not self.check_rx_reorder():
            LOGGER.error('{}: reorder RX check failed.'.format(self.host))
        else:
            LOGGER.info('{}: reorder RX passed '.format(self.host))
            return True
        # SPEAD okay?
        if not self.check_rx_spead():
            LOGGER.error('{}: SPEAD RX check failed. Ignoring '
                         'for now.'.format(self.host))
        else:
            LOGGER.info('{}: SPEAD RX passed.'.format(self.host))
        # raw?
        if not self.check_rx_raw():
            LOGGER.error('{}: Raw RX failed.'.format(self.host))
        else:
            LOGGER.info('{}: Raw RX passed '.format(self.host))
        LOGGER.error('{}: check_rx() - FALSE.'.format(self.host))
        return False


    def get_spead_status(self):
        """
        Returns the SPEAD counters on this FPGA.
        """
        if 'spead_status' in self.registers.names():
            return self.registers.spead_status.read()['data']
        else:
            LOGGER.error("Can't check SPEAD RX: register not found")
            raise RuntimeError("Can't check SPEAD RX: register not found")
            return


    def _check_rx_spead_skarab(self, checks=5):
        """
        Checks the SPEAD unpack block on a SKARAB FPGA.
        :return: 
        """
        results = []
        for ctr in range(checks):
            results.append(self.get_spead_status())
            time.sleep(0.1)
        pkts_rx = False
        for ctr in range(1, checks):
            if results[ctr]['pkt_cnt'] != results[0]['pkt_cnt']:
                pkts_rx = True
                break
        if not pkts_rx:
            LOGGER.error('%s: SPEAD packet count not incrementing' % self.host)
            return False
        for key in ['magic_err_cnt', 'header_err_cnt',
                    'pad_err_cnt', 'pkt_len_err_cnt']:
            got_error = False
            for ctr in range(1, checks):
                if results[ctr][key] != results[0][key]:
                    got_error = True
                    break
            if got_error:
                LOGGER.error('%s: SPEAD error %s incrementing' % (
                    self.host, key))
                return False
        return True

    def check_rx_spead(self):
        """
        Check that this host is receiving SPEAD data.
        :param max_waittime: the maximum time to wait
        :return:
        """
        if 'spead_status' in self.registers.names():
            return self._check_rx_spead_skarab()
        else:
            LOGGER.error("Can't check SPEAD RX: register not found")
            return False

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
