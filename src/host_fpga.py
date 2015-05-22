__author__ = 'paulp'

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

    def check_tx_raw(self):
        """
        Check to see whether this host is transmitting packets without
        error on all its GBE interfaces.
        :return:
        """
        def _get_gbe_data():
            _returndata = {}
            for gbecore in self.tengbes:
                _returndata[gbecore.name] = gbecore.read_tx_counters()
            return _returndata
        tx_one = _get_gbe_data()
        time.sleep(1)
        tx_two = _get_gbe_data()
        for _core in tx_one:
            _d1 = tx_one[_core]
            _d2 = tx_two[_core]
            if ((_d2['%s_txctr' % _core]['data']['reg'] - _d1['%s_txctr' % _core]['data']['reg'] <= 0) or
                    (_d2['%s_txvldctr' % _core]['data']['reg'] - _d1['%s_txvldctr' % _core]['data']['reg'] <= 0)):
                return False
            if ((_d2['%s_txofctr' % _core]['data']['reg'] - _d1['%s_txofctr' % _core]['data']['reg'] > 0) or
                    (_d2['%s_txerrctr' % _core]['data']['reg'] - _d1['%s_txerrctr' % _core]['data']['reg'] > 0) or
                    (_d2['%s_txfullctr' % _core]['data']['reg'] - _d1['%s_txfullctr' % _core]['data']['reg'] > 0)):
                return False
        return True

    def check_rx_raw(self, max_waittime=30):
        """
        Is this host receiving 10gbe data correctly?
        :param max_waittime: maximum time to try for data
        :return:
        """
        def get_gbe_data():
            returndata = {}
            for gbecore in self.tengbes:
                returndata[gbecore.name] = gbecore.read_counters()
            return returndata
        rxregs = get_gbe_data()
        start_time = time.time()
        rx_okay = False
        while time.time() < start_time + max_waittime:
            time.sleep(1)
            rxregs_new = get_gbe_data()
            still_the_same = False
            for core in rxregs.keys():
                rxctr_old = rxregs[core]['%s_rxctr' % core]['data']['reg']
                rxctr_new = rxregs_new[core]['%s_rxctr' % core]['data']['reg']
                #rxbad_old = rxregs[core]['%s_rxbadctr' % core]['data']['reg']
                #rxbad_new = rxregs_new[core]['%s_rxbadctr' % core]['data']['reg']
                rxerr_old = rxregs[core]['%s_rxerrctr' % core]['data']['reg']
                rxerr_new = rxregs_new[core]['%s_rxerrctr' % core]['data']['reg']
                #if (rxctr_old == rxctr_new) or (rxbad_old != rxbad_new) or (rxerr_old != rxerr_new):
                if (rxctr_old == rxctr_new) or (rxerr_old != rxerr_new):
                    still_the_same = True
                    continue
            if still_the_same:
                continue
            else:
                rx_okay = True
                break
            rxregs = rxregs_new
        if not rx_okay:
            LOGGER.error('Host %s RX data error after %d seconds.' % (self.host, max_waittime))
            return False
        else:
            LOGGER.info('Host %s is receiving 10gbe data' % self.host)
            return True

    def check_rx_spead(self):
        """
        Check that this host is receiving SPEAD data.
        :return:
        """
        _sleeptime = 1
        _ctrs0 = self.read_spead_counters()
        time.sleep(_sleeptime)
        _ctrs1 = self.read_spead_counters()
        for core_ctr in range(0, len(_ctrs0)):
            # ctrs must have changed
            if _ctrs1[core_ctr][0] == _ctrs0[core_ctr][0]:
                LOGGER.error('Host %s core %i is not receiving SPEAD data, bailing' %
                             (self.host, core_ctr))
                return False
            # but the errors must not
            if _ctrs1[core_ctr][1] != _ctrs0[core_ctr][1]:
                LOGGER.error('Host %s core %i has a changing SPEAD error counter: '
                             'initially %i errors and %is later had %i SPEAD errors, bailing.' %
                             (self.host, core_ctr, _ctrs0[core_ctr][1],
                              _sleeptime, _ctrs1[core_ctr][1]))
                return False
        LOGGER.info('Host %s is receiving SPEAD data' % self.host)
        return True
