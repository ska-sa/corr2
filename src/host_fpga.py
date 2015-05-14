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

    def _no_implement_connect(self, program=True, program_port=-1):
        """
        Initialise this host node to its normal running state.
        :param program: Should the FPGA be reprogrammed?
        :param program_port: Which port should be used for programming. -1 means random.
        :return: True if the FPGA client is running and connected.
        """
        raise NotImplementedError
        if not self.is_connected():
            KatcpFpga.connect(self)
        if program:
            self.upload_to_ram_and_program(self.boffile, port=program_port)
        self.test_connection()
        self.get_system_information()
        return self.is_running()

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
            raise RuntimeError('Host %s RX data error after %d seconds.' % (self.host, max_waittime))
        else:
            LOGGER.info('Host %s is receiving 10gbe data' % self.host)

    def check_rx_spead(self):
        """
        Check that this host is receiving SPEAD data.
        :return:
        """
        xrxspead_ctrs0 = self.read_spead_counters()
        time.sleep(1)
        xrxspead_ctrs1 = self.read_spead_counters()
        for core_ctr in range(0, len(xrxspead_ctrs0)):
            # ctrs must have changed
            if xrxspead_ctrs1[core_ctr][0] == xrxspead_ctrs0[core_ctr][0]:
            	LOGGER.error('Host %s core %i is not receiving SPEAD data, bailing' % (self.host, core_ctr))
                raise RuntimeError('Host %s core %i is not receiving SPEAD data, bailing' % (self.host, core_ctr))
            # but the errors must not
            if xrxspead_ctrs1[core_ctr][1] != xrxspead_ctrs0[core_ctr][1]:
                LOGGER.error('Host %s core %i has an changing SPEAD error counter: initially %i errors and 1s later had %i SPEAD errors, bailing.' % (self.host, core_ctr, xrxspead_ctrs0[core_ctr][1],xrxspead_ctrs1[core_ctr][1]))
                raise RuntimeError('Host %s core %i has a changing SPEAD error counter: initially %i errors and 1s later had %i SPEAD errors, bailing.' % (self.host, core_ctr, xrxspead_ctrs0[core_ctr][1],xrxspead_ctrs1[core_ctr][1]))
        LOGGER.info('Host %s is not receiving SPEAD data errors' % self.host)
