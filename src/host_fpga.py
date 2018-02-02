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
        rv = None
        if 'spead_status' in self.registers.names():
            rv = self.registers.spead_status.read()['data']
        elif 'unpack_status' in self.registers.names():
            rv = self.registers.unpack_status.read()['data']
            if 'unpack_status1' in self.registers.names():
                rv.update(self.registers.unpack_status1.read()['data'])
        if rv is None:
            msg = '%s: can\'t check SPEAD RX: register not found' % self.host
            LOGGER.error(msg)
            raise RuntimeError(msg)
        return rv

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
        deng_time_ok = 0
        for ctr in range(1, checks):
            if results[ctr]['pkt_cnt'] != results[0]['pkt_cnt']:
                pkts_rx = True
            if 'time_err_cnt' in results[ctr]:
                if results[ctr]['time_err_cnt'] != results[0]['time_err_cnt']:
                    deng_time_ok = 2
            else:
                deng_time_ok = 1
        if not pkts_rx:
            LOGGER.error('%s: SPEAD packet count not incrementing' % self.host)
            return 1, deng_time_ok
        for key in ['magic_err_cnt', 'header_err_cnt',
                    'pad_err_cnt', 'pkt_len_err_cnt']:
            for ctr in range(1, checks):
                if results[ctr][key] != results[0][key]:
                    LOGGER.error('%s: SPEAD error %s incrementing' % (
                        self.host, key))
                    return 2, deng_time_ok
        return 0, deng_time_ok

    def check_rx_spead(self):
        """
        Check that this host is receiving SPEAD data.
        :return:
        """
        return self._check_rx_spead_skarab()

    def check_rx_reorder(self):
        raise NotImplemented

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
