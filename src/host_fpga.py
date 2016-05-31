import logging
import time

from casperfpga.katcp_fpga import KatcpFpga
from host import Host

LOGGER = logging.getLogger(__name__)


class FpgaHost(Host, KatcpFpga):
    """
    A Host that is a CASPER KATCP FPGA.
    """

    def __init__(self, host, katcp_port=7147, boffile=None, connect=False):
        Host.__init__(self, host, katcp_port)
        KatcpFpga.__init__(self, host, katcp_port, connect=connect)
        self.boffile = boffile

    def check_rx_reorder(self):
        """

        :return:
        """
        raise NotImplementedError

    def check_rx(self, max_waittime=30):
        """
        Check the receive path on this FPGA host
        :param max_waittime: the maximum time to wait for raw 10gbe data
        :return:
        """
        if not self.check_rx_raw(0.2, 5):
            LOGGER.error('{}: Raw RX failed.'.format(self.host))
            return False
        else:
            LOGGER.info('{}: Raw RX passed '.format(self.host))

        if not self.check_rx_spead(max_waittime=max_waittime):
            LOGGER.error('{}: SPEAD RX check failed. Ignoring '
                         'for now'.format(self.host))
        else:
            LOGGER.info('{}: SPEAD RX passed.'.format(self.host))

        if not self.check_rx_reorder():
            LOGGER.error('{}: reorder RX check failed.'.format(self.host))
            return False
        else:
            LOGGER.info('{}: reorder RX passed '.format(self.host))

        LOGGER.info('{}: check_rx() - TRUE.'.format(self.host))
        return True

    def check_rx_spead(self, max_waittime=5):
        """
        Check that this host is receiving SPEAD data.
        :return:
        """
        start_time = time.time()
        ctrs0 = self.read_spead_counters()
        if len(ctrs0) != len(self.tengbes):
            errstr = '{}: has {} 10gbe cores, but read_spead_counters ' \
                     'returned {} results'.format(self.host, len(self.tengbes),
                                                  len(ctrs0))
            LOGGER.error(errstr)
            raise RuntimeError(errstr)
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
            LOGGER.error('%s: not receiving good SPEAD data '
                         'over a %i second period. Errors on '
                         'interfaces: %s.\n\t%s -> %s' % (self.host,
                                                          max_waittime,
                                                          spead_errors,
                                                          ctrs0, ctrs1, ))
            return False
        else:
            LOGGER.info('%s: receiving good SPEAD data.' % self.host)
            return True
