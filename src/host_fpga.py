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
        time.sleep(0.5)
        tx_two = _get_gbe_data()
        time.sleep(0.5)
        tx_three = _get_gbe_data()
        for _core in tx_one:
            _d1 = tx_one[_core]
            _d2 = tx_two[_core]
            _d3 = tx_three[_core]

            def _checkregs(keyname, required, equal):
                if keyname in _d1:
                    if not equal:
                        if _d2[keyname]['data']['reg'] == _d1[keyname]['data']['reg']\
                                and _d3[keyname]['data']['reg'] == _d2[keyname]['data']['reg']:
                            LOGGER.info('%s - %s not changing' % (self.host, keyname))
                            return False
                    else:
                        if _d2[keyname]['data']['reg'] != _d1[keyname]['data']['reg']\
                                and _d3[keyname]['data']['reg'] != _d2[keyname]['data']['reg']:
                            LOGGER.info('%s - %s changing' % (self.host, keyname))
                            return False
                else:
                    if required:
                        LOGGER.error('%s - %s does not exist' % (self.host, keyname))
                        return False
                    else:
                        LOGGER.warn('%s - %s does not exist' % (self.host, keyname))
                return True

            # tx counter and error counter registers MUST exist
            if not _checkregs('{}_txctr'.format(_core), required=True, equal=False):
                return False
            if not _checkregs('{}_txerrctr'.format(_core), required=True, equal=True):
                return False

            # certain registers can not exist but absence are noted
            _checkregs('{}_txvldctr'.format(_core), required=False, equal=False)
            _checkregs('{}_txofctr'.format(_core), required=False, equal=True)
            _checkregs('{}_txfullctr'.format(_core), required=False, equal=True)

#            if ((_d2['%s_txctr' % _core]['data']['reg'] - _d1['%s_txctr' % _core]['data']['reg'] <= 0) or
#                    (_d2['%s_txvldctr' % _core]['data']['reg'] - _d1['%s_txvldctr' % _core]['data']['reg'] <= 0)):
#                return False
#            if ((_d2['%s_txofctr' % _core]['data']['reg'] - _d1['%s_txofctr' % _core]['data']['reg'] > 0) or
#                    (_d2['%s_txerrctr' % _core]['data']['reg'] - _d1['%s_txerrctr' % _core]['data']['reg'] > 0) or
#                    (_d2['%s_txfullctr' % _core]['data']['reg'] - _d1['%s_txfullctr' % _core]['data']['reg'] > 0)):
#                return False
        return True

    def check_rx(self, max_waittime=30):
        """
        Check the receive path on this X host
        :param max_waittime: the maximum time to wait for raw 10gbe data
        :return:
        """
        start_time = time.time()
        if not self.check_rx_spead(max_waittime=max_waittime):
            LOGGER.error('\tSPEAD RX check failed.')
            _waittime = max_waittime - (time.time() - start_time)
            if _waittime < 0:
                return False
            if not self.check_rx_raw(max_waittime=_waittime):
                LOGGER.error('\tRaw RX also failed.')
            else:
                LOGGER.error('\tRaw RX passed - problem is likely in the SPEAD stage.')
            return False
        else:
            LOGGER.info('\tSPEAD RX passed - checking reorder stage.')
        if not self.check_rx_reorder():
            LOGGER.error('FPGA host {0} reorder RX check failed.'.format(self.host))
            return False
        LOGGER.info('FPGA host %s check_rx() - TRUE.' % self.host)
        return True

    def check_rx_raw(self, max_waittime=5):
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
        still_the_same = self.tengbes.names()[:]
        while (time.time() < start_time + max_waittime) and \
                (len(still_the_same) > 0):
            time.sleep(0.1)
            core = still_the_same[0]
            rxregs_new = self.tengbes[core].read_counters()
            rxctr_old = rxregs[core]['%s_rxctr' % core]['data']['reg']
            rxerr_old = rxregs[core]['%s_rxerrctr' % core]['data']['reg']
            rxctr_new = rxregs_new['%s_rxctr' % core]['data']['reg']
            rxerr_new = rxregs_new['%s_rxerrctr' % core]['data']['reg']
            if (rxctr_old != rxctr_new) and (rxerr_old == rxerr_new):
                still_the_same.remove(core)
        if len(still_the_same) > 0:
            LOGGER.error('Host %s is not receiving 10GbE data on interfaces %s, '
                         'or is receiving bad data, over a %.3f second '
                         'period.' % (self.host, still_the_same, max_waittime))
            return False
        else:
            LOGGER.info('Host %s is receiving data on all '
                        'GbE interfaces.' % self.host)
            return True

    def check_rx_spead(self, max_waittime=5):
        """
        Check that this host is receiving SPEAD data.
        :return:
        """
        start_time = time.time()
        ctrs0 = self.read_spead_counters()
        still_the_same = [True for gbe in ctrs0]
        while (time.time() < start_time + max_waittime) and \
                (still_the_same.count(True) > 0):
            time.sleep(0.1)
            ctrs1 = self.read_spead_counters()
            for _core_ctr in range(0, len(still_the_same)):
                if (ctrs1[_core_ctr][0] != ctrs0[_core_ctr][0]) and \
                        (ctrs1[_core_ctr][1] == ctrs0[_core_ctr][1]):
                    still_the_same[_core_ctr] = False
        if still_the_same.count(True) > 0:
            LOGGER.error('Host %s is not receiving good SPEAD data '
                         'over a %i second period. Errors on '
                         'interfaces: %s.\n\t%s -> %s' % (self.host,
                                                          max_waittime,
                                                          still_the_same,
                                                          ctrs0, ctrs1, ))
            return False
        else:
            LOGGER.info('Host %s is receiving good SPEAD data.' % self.host)
            return True
