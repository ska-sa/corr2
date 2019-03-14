import logging
import time

import casperfpga
from casperfpga.transport_skarab import SkarabTransport, \
    SkarabReorderError, SkarabReorderWarning

from host_fpga import FpgaHost

LOGGER = logging.getLogger(__name__)


class DigitiserStreamReceiver(FpgaHost):
    """
    The RX section of a fengine and filter engine are the same - receive
    the digitiser data.
    """
    def __init__(self, host, katcp_port=7147, bitstream=None, connect=True):
        super(DigitiserStreamReceiver, self).__init__(
            host=host, katcp_port=katcp_port, bitstream=bitstream,
            connect=connect, transport=SkarabTransport)

    def get_rx_reorder_status(self):
        """
        Read the reorder block counters
        :return:
        """
        if 'reorder_ctrs' in self.registers.names():
            reorder_ctrs = self.registers.reorder_ctrs.read()['data']
            LOGGER.debug('found reorder_ctrs')
        else:
            reorder_ctrs = self.registers.reorder_status.read()['data']
            LOGGER.debug('found reorder_status'.format(reorder_ctrs))
        try:
            reorder_ctrs.update(self.registers.reorder_status1.read()['data'])
            LOGGER.debug('found reorder_status1'.format(reorder_ctrs))
        except (AttributeError, KeyError):
            pass
        return reorder_ctrs

    def get_local_time(self):
        """
        Get the local timestamp of this board, received from the digitiser
        :return: time in samples since the digitiser epoch
        """
        _msw = self.registers.local_time_msw
        _lsw = self.registers.local_time_lsw
        first_msw = _msw.read()['data']['timestamp_msw']
        while _msw.read()['data']['timestamp_msw'] == first_msw:
            time.sleep(0.01)
        lsw = _lsw.read()['data']['timestamp_lsw']
        msw = _msw.read()['data']['timestamp_msw']
        if msw != first_msw + 1:
            raise RuntimeError(
                '%s get_local_time() - network is too slow to allow accurate '
                'time read (%i -> %i)' % (self.host, first_msw, msw))
        rv = (msw << 32) | lsw
        return rv

    def clear_status(self):
        """
        Clear the status registers and counters on this host
        :return:
        """
        self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse',
                                     cnt_rst='pulse')
        # self.registers.control.write(gbe_cnt_rst='pulse')
        LOGGER.debug('{}: status cleared.'.format(self.host))

# end
