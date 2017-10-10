import logging
import time

from casperfpga.casperfpga import CasperFpga
from casperfpga.network import Mac

LOGGER = logging.getLogger(__name__)


class FpgaHost(CasperFpga):
    """
    A Host that is a CASPER FPGA, ROACH2 or SKARAB.
    """

    def check_rx_reorder(self):
        """
        Is the host receiving and reordering data?
        :return:
        """
        raise NotImplementedError

    def read_spead_counters(self):
        """
        Read SPEAD counters on the host.
        :return:
        """
        raise NotImplementedError

    def check_rx(self, max_waittime=30):
        """
        Check the receive path on this FPGA host
        :param max_waittime: the maximum time to wait
        :return:
        """
        # check the reorder, if it fails, go lower
        if not self.check_rx_reorder():
            LOGGER.debug('{}: reorder RX check failed.'.format(self.host))
        else:
            LOGGER.debug('{}: reorder RX passed '.format(self.host))
            return True
        # SPEAD okay?
        if not self.check_rx_spead(max_waittime=max_waittime):
            LOGGER.debug('{}: SPEAD RX check failed. Ignoring '
                         'for now'.format(self.host))
        else:
            LOGGER.debug('{}: SPEAD RX passed.'.format(self.host))
        # raw?
        if not self.check_rx_raw(0.2, 5):
            LOGGER.debug('{}: Raw RX failed.'.format(self.host))
        else:
            LOGGER.debug('{}: Raw RX passed '.format(self.host))
        LOGGER.debug('{}: check_rx() - FALSE.'.format(self.host))
        return False

    def _check_rx_spead_skarab(self, checks=5):
        """

        :return: 
        """
        results = []
        for ctr in range(checks):
            results.append(self.registers.spead_status.read()['data'])
            if ctr == checks - 1:
                break
            time.sleep(0.1)
        pkts_rx = False
        for ctr in range(1, checks):
            if results[ctr]['pkt_cnt'] != results[0]['pkt_cnt']:
                pkts_rx = True
                break
        if not pkts_rx:
            LOGGER.debug('%s: SPEAD packet count not incrementing' % self.host)
            return False
        for key in ['magic_err_cnt', 'header_err_cnt',
                    'pad_err_cnt', 'pkt_len_err_cnt']:
            got_error = False
            for ctr in range(1, checks):
                if results[ctr][key] != results[0][key]:
                    got_error = True
                    break
            if got_error:
                LOGGER.debug('%s: SPEAD error %s incrementing' % (
                    self.host, key))
                return False
        return True

    def check_rx_spead(self, max_waittime=5):
        """
        Check that this host is receiving SPEAD data.
        :param max_waittime: the maximum time to wait
        :return:
        """
        if 'spead_status' in self.registers.names():
            return self._check_rx_spead_skarab()
        start_time = time.time()
        ctrs0 = self.read_spead_counters()
        if len(ctrs0) != len(self.gbes):
            errmsg = '{}: has {} 10gbe cores, but read_spead_counters ' \
                     'returned {} results'.format(self.host, len(self.gbes),
                                                  len(ctrs0))
            LOGGER.error(errmsg)
            raise RuntimeError(errmsg)
        spead_errors = [True] * len(ctrs0)
        ctrs1 = None
        while (time.time() < start_time + max_waittime) and \
                (spead_errors.count(True) > 0):
            time.sleep(0.1)
            ctrs1 = self.read_spead_counters()
            for _core_ctr in range(0, len(spead_errors)):
                counter_incr = ctrs1[_core_ctr][0] != ctrs0[_core_ctr][0]
                errors_the_same = ctrs1[_core_ctr][1] == ctrs0[_core_ctr][1]
                if counter_incr and errors_the_same:
                    spead_errors[_core_ctr] = False
        if spead_errors.count(True) > 0:
            LOGGER.error(
                '%s: not receiving good SPEAD data over a %i second period. '
                'Errors on interfaces: %s.\n\t%s -> %s' % (
                    self.host, max_waittime, spead_errors, ctrs0, ctrs1, ))
            return False
        else:
            LOGGER.info('%s: receiving good SPEAD data.' % self.host)
            return True

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
                gbe.enable()
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
