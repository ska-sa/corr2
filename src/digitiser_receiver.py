import logging
import time

from host_fpga import FpgaHost

LOGGER = logging.getLogger(__name__)


class DigitiserStreamReceiver(FpgaHost):
    """
    The RX section of a fengine and filter engine are the same - receive
    the digitiser data.
    """

    def __init__(self, host, katcp_port=7147, bitstream=None, connect=True):
        super(DigitiserStreamReceiver, self).__init__(
            host=host, katcp_port=katcp_port, bitstream=bitstream, connect=connect)

    def _get_rxreg_data(self):
        """
        Get the rx register data for this host
        :return:
        """
        data = {}
        if 'reorder_ctrs1' in self.registers.names():
            reorder_ctrs = self.registers.reorder_ctrs.read()['data']
            reorder_ctrs.update(self.registers.reorder_ctrs1.read()['data'])
        else:
            reorder_ctrs = self.registers.reorder_ctrs.read()['data']
        data['mcnt_relock'] = reorder_ctrs['mcnt_relock']
        data['timerror'] = reorder_ctrs['timestep_error']
        data['discard'] = reorder_ctrs['discard']
        num_gbes = len(self.gbes)
        for gbe in range(num_gbes):
            data['pktof_ctr%i' % gbe] = reorder_ctrs['pktof%i' % gbe]
        for pol in range(0, 2):
            data['recverr_ctr%i' % pol] = reorder_ctrs['recverr%i' % pol]
        return data

    def _check_rx_reorder_skarab(self):
        """
        
        :return: 
        """
        # TODO - this must actually work
        return True

    def check_rx_reorder(self):
        """
        Is this F host reordering received data correctly?
        :return:
        """
        if 'status_reo0' in self.registers.names():
            return self._check_rx_reorder_skarab()
        _required_repetitions = 5
        _sleeptime = 0.2
        num_gbes = len(self.gbes)
        if num_gbes < 1:
            raise RuntimeError('F-host with no 10gbe cores %s?' % self.host)
        test_data = []
        for _ctr in range(0, _required_repetitions):
            test_data.append(self._get_rxreg_data())
            time.sleep(_sleeptime)
        got_errors = False
        for _ctr in range(1, _required_repetitions):
            for gbe in range(num_gbes):
                _key = 'pktof_ctr%i' % gbe
                if test_data[_ctr][_key] != test_data[0][_key]:
                    LOGGER.error(
                        'F host %s packet overflow on interface gbe%i. '
                        '%i -> %i' % (self.host, gbe, test_data[_ctr][_key],
                                      test_data[0][_key]))
                    got_errors = True
            for pol in range(0, 2):
                _key = 'recverr_ctr%i' % pol
                if test_data[_ctr][_key] != test_data[0][_key]:
                    LOGGER.error('F host %s pol %i reorder count error. %i '
                                 '-> %i' % (self.host, pol,
                                            test_data[_ctr][_key],
                                            test_data[0][_key]))
                    got_errors = True
            if test_data[_ctr]['mcnt_relock'] != test_data[0]['mcnt_relock']:
                LOGGER.error('F host %s mcnt_relock is changing. %i -> %i' % (
                    self.host, test_data[_ctr]['mcnt_relock'],
                    test_data[0]['mcnt_relock']))
                got_errors = True
            if test_data[_ctr]['timerror'] != test_data[0]['timerror']:
                LOGGER.error('F host %s timestep error is changing. %i -> %i' %
                             (self.host, test_data[_ctr]['timerror'],
                              test_data[0]['timerror']))
                got_errors = True
            if test_data[_ctr]['discard'] != test_data[0]['discard']:
                LOGGER.error('F host %s discarding packets. %i -> %i' % (
                    self.host, test_data[_ctr]['discard'],
                    test_data[0]['discard']))
                got_errors = True
        if got_errors:
            LOGGER.error('One or more errors detected, check logs.')
            return False
        LOGGER.info('%s: is reordering data okay.' % self.host)
        return True

    def read_spead_counters(self):
        """
        Read the SPEAD rx and error counters for this F host
        :return:
        """
        rv = []
        spead_ctrs = self.registers.spead_ctrs.read()['data']
        for core_ctr in range(0, len(self.gbes)):
            counter = spead_ctrs['rx_cnt%i' % core_ctr]
            error = spead_ctrs['err_cnt%i' % core_ctr]
            rv.append((counter, error))
        return rv

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
        assert msw == first_msw + 1  # if this fails the network is waaaaay slow
        return (msw << 32) | lsw

    def clear_status(self):
        """
        Clear the status registers and counters on this host
        :return:
        """
        self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse',
                                     cnt_rst='pulse')
        LOGGER.debug('{}: status cleared.'.format(self.host))
