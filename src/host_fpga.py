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
                    _d1val = _d1[keyname]['data']['reg']
                    _d2val = _d2[keyname]['data']['reg']
                    _d3val = _d3[keyname]['data']['reg']

                    if not equal:
                        if (_d2val == _d1val) and (_d3val == _d2val):
                            LOGGER.info('%s: %s not changing' % (self.host,
                                                                 keyname))
                            return False
                    else:
                        if (_d2val != _d1val) and (_d3val != _d2val):
                            LOGGER.info('%s: %s changing' % (self.host,
                                                             keyname))
                            return False
                else:
                    if required:
                        LOGGER.error('%s: %s does not exist' % (self.host,
                                                                keyname))
                        return False
                    else:
                        LOGGER.warn('%s: %s does not exist' % (self.host,
                                                               keyname))
                return True

            # tx counter and error counter registers MUST exist
            if not _checkregs('{}_txctr'.format(_core),
                              required=True, equal=False):
                return False
            if not _checkregs('{}_txerrctr'.format(_core),
                              required=True, equal=True):
                return False

            # certain registers can not exist but absence are noted
            if not _checkregs('{}_txvldctr'.format(_core),
                              required=False, equal=False):
                return False
            if not _checkregs('{}_txofctr'.format(_core),
                              required=False, equal=True):
                return False
            if not _checkregs('{}_txfullctr'.format(_core),
                              required=False, equal=True):
                return False

            # if ((_d2['%s_txctr' % _core]['data']['reg'] - _d1['%s_txctr' % _core]['data']['reg'] <= 0) or
            #         (_d2['%s_txvldctr' % _core]['data']['reg'] - _d1['%s_txvldctr' % _core]['data']['reg'] <= 0)):
            #     return False
            # if ((_d2['%s_txofctr' % _core]['data']['reg'] - _d1['%s_txofctr' % _core]['data']['reg'] > 0) or
            #         (_d2['%s_txerrctr' % _core]['data']['reg'] - _d1['%s_txerrctr' % _core]['data']['reg'] > 0) or
            #         (_d2['%s_txfullctr' % _core]['data']['reg'] - _d1['%s_txfullctr' % _core]['data']['reg'] > 0)):
            #     return False
        return True

    def check_rx(self, max_waittime=30):
        """
        Check the receive path on this X host
        :param max_waittime: the maximum time to wait for raw 10gbe data
        :return:
        """
        if not self.check_rx_raw(max_waittime=max_waittime):
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

    def get_tengbe_counters(self):
        """
        Read all the tengbe counters on this device.
        :return:
        """
        returndata = {}
        for gbecore in self.tengbes:
            returndata[gbecore.name] = gbecore.read_counters()
        return returndata

    def check_rx_raw(self, max_waittime=10):
        """
        Is this host receiving 10gbe data correctly?
        :param max_waittime: maximum time to try for data
        :return:
        """
        rxregs = self.get_tengbe_counters()
        start_time = time.time()
        still_the_same = self.tengbes.names()[:]
        while ((time.time() < start_time + max_waittime) and
              (len(still_the_same) > 0)):

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
            LOGGER.error('%s: not receiving 10GbE data on interfaces %s, '
                         'or is receiving bad data, over a %.3f second '
                         'period.' % (self.host, still_the_same, max_waittime))
            return False
        else:
            LOGGER.info('%s: receiving data on all '
                        'GbE interfaces.' % self.host)
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
