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

    def _skarab_print_reorder_regs(self):
        """
        Debugging the SKARAB RX reorder problems... 
        :return: 
        """
        regs = self.registers
        print('reorder_status: %s' % regs.reorder_status.read()['data'])
        print('reorder_status1: %s' % regs.reorder_status1.read()['data'])

    def _check_rx_reorder_skarab(self):
        """
        Is a SKARAB fhost receiving reordered data?
        :return: 
        """
        required_repetitions = 5
        sleeptime = 0.2
        num_gbes = len(self.gbes)
        if num_gbes != 1:
            raise RuntimeError('FHost %s: should have only '
                               'one FortyGbe?' % self.host)
        test_data = []
        for _ctr in range(0, required_repetitions):
            reorder_ctrs = self.get_rx_reorder_status()
            test_data.append(reorder_ctrs)
            time.sleep(sleeptime)
        if 'dv_cnt' not in test_data[0]:
            errstr = 'FHost %s: No dv_cnt available to test.' % self.host
            LOGGER.debug(errstr)
            raise SkarabReorderError(errstr)
        getting_data = False
        for ctr in range(1, required_repetitions):
            if test_data[ctr]['dv_cnt'] != test_data[0]['dv_cnt']:
                getting_data = True
                break
        if not getting_data:
            errstr = 'FHost %s: dv_cnt is NOT changing: %i' % (
                self.host, test_data[0]['dv_cnt'])
            LOGGER.debug(errstr)
            raise SkarabReorderWarning(errstr)
        for ctr in range(1, required_repetitions):
            for key in ['discard_cnt', 'overflow_err_cnt', 'receive_err_cnt',
                        'relock_err_cnt', 'timestep_err_cnt']:
                v0 = test_data[0][key]
                v1 = test_data[ctr][key]
                if v1 != v0:
                    LOGGER.debug('FHost %s: %s is changing. %i -> %i' % (
                        self.host, key, v1, v0))
                    errstr = 'One or more reorder errors detected, ' \
                             'check logs.'
                    LOGGER.debug(errstr)
                    raise SkarabReorderError(errstr)
        LOGGER.debug('%s: is reordering data okay.' % self.host)
        return True

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

    def _get_rxreg_data_roach2(self):
        reorder_ctrs = self.registers.reorder_ctrs.read()['data']
        if 'reorder_ctrs1' in self.registers.names():
            reorder_ctrs.update(self.registers.reorder_ctrs1.read()['data'])
        data['mcnt_relock'] = reorder_ctrs['mcnt_relock']
        data['timerror'] = reorder_ctrs['timestep_error']
        data['discard'] = reorder_ctrs['discard']
        num_gbes = len(self.gbes)
        for gbe in range(num_gbes):
            data['pktof_ctr%i' % gbe] = reorder_ctrs['pktof%i' % gbe]
        for pol in range(0, 2):
            data['recverr_ctr%i' % pol] = reorder_ctrs['recverr%i' % pol]
        return data

    def check_rx_reorder(self):
        """
        Is this F host reordering received data correctly?
        :return:
        """
        if isinstance(self.transport, casperfpga.SkarabTransport):
            return self._check_rx_reorder_skarab()
        raise DeprecationWarning('Have to properly accomodate both SKARABs'
                                 'and ROACHs in the future.')
        required_repetitions = 5
        sleeptime = 0.2
        num_gbes = len(self.gbes)
        if num_gbes < 1:
            raise RuntimeError('FHost with no 10gbe cores %s?' % self.host)
        test_data = []
        for _ctr in range(0, required_repetitions):
            test_data.append(self._get_rxreg_data_roach2())
            time.sleep(sleeptime)
        got_errors = False
        for _ctr in range(1, required_repetitions):
            for gbe in range(num_gbes):
                _key = 'pktof_ctr%i' % gbe
                if test_data[_ctr][_key] != test_data[0][_key]:
                    LOGGER.error(
                        'FHost %s: packet overflow on interface gbe%i. '
                        '%i -> %i' % (self.host, gbe, test_data[_ctr][_key],
                                      test_data[0][_key]))
                    got_errors = True
            for pol in range(0, 2):
                _key = 'recverr_ctr%i' % pol
                if test_data[_ctr][_key] != test_data[0][_key]:
                    LOGGER.error('FHost %s: pol %i reorder count error. %i '
                                 '-> %i' % (self.host, pol,
                                            test_data[_ctr][_key],
                                            test_data[0][_key]))
                    got_errors = True
            if test_data[_ctr]['mcnt_relock'] != test_data[0]['mcnt_relock']:
                LOGGER.error('FHost %s: mcnt_relock is changing. %i -> %i' % (
                    self.host, test_data[_ctr]['mcnt_relock'],
                    test_data[0]['mcnt_relock']))
                got_errors = True
            if test_data[_ctr]['timerror'] != test_data[0]['timerror']:
                LOGGER.error('FHost %s: timestep error is changing. %i -> %i' %
                             (self.host, test_data[_ctr]['timerror'],
                              test_data[0]['timerror']))
                got_errors = True
            if test_data[_ctr]['discard'] != test_data[0]['discard']:
                LOGGER.error('FHost %s: discarding packets. %i -> %i' % (
                    self.host, test_data[_ctr]['discard'],
                    test_data[0]['discard']))
                got_errors = True
        if got_errors:
            LOGGER.error('One or more errors detected, check logs.')
            return False
        LOGGER.info('%s: is reordering data okay.' % self.host)
        return True

#    def read_spead_counters(self):
#        """
#        Read the SPEAD rx and error counters for this F host
#        :return:
#        """
#        rv = []
#        spead_ctrs = self.registers.spead_ctrs.read()['data']
#        for core_ctr in range(0, len(self.gbes)):
#            counter = spead_ctrs['rx_cnt%i' % core_ctr]
#            error = spead_ctrs['err_cnt%i' % core_ctr]
#            rv.append((counter, error))
#        return rv

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
