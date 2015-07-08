__author__ = 'paulp'

import time
import logging

from host_fpga import FpgaHost

LOGGER = logging.getLogger(__name__)

class FpgaFilterHost(FpgaHost):
    """
    A Host, that hosts SNB filter engines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, board_id, instrument_config):
        """
        Create a filter host
        :param board_id:
        :param instrument_config:
        :return:
        """
        self._config = instrument_config['filter']
        self._instrument_config = instrument_config
        _katcp_port = int(self._instrument_config['FxCorrelator']['katcp_port'])
        _bof = self._config['bitstream']
        _hosts = self._config['hosts'].strip().split(',')
        FpgaHost.__init__(self, _hosts[board_id], katcp_port=_katcp_port, boffile=_bof, connect=True)
        self.board_id = board_id
        self.data_sources = []
        self.data_destinations = []

    def enable_tx(self):
        """
        Enable transmission on this filter engine.
        :return:
        """
        self.registers.control.write(gbe_txen=True)
        LOGGER.info('{}: filter output enabled.'.format(self.host))

    def clear_status(self):
        """
        Clear the status registers and counters on this filter board
        :return:
        """
        self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse', cnt_rst='pulse')
        LOGGER.debug('{}: filter status cleared.'.format(self.host))

    def subscribe_to_source_data(self):
        """
        Subscribe the multicast source data as configured.
        :return:
        """
        LOGGER.info('{}: subscribing to filter datasources...'.format(
            self.host))
        gbe_ctr = 0
        for source in self.data_sources:
            if not source.is_multicast():
                LOGGER.info('\tsource address {} is not multicast?'.format(
                    str(source.ip_address)))
            else:
                rxaddr = str(source.ip_address)
                rxaddr_bits = rxaddr.split('.')
                rxaddr_base = int(rxaddr_bits[3])
                rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0], rxaddr_bits[1], rxaddr_bits[2])
                for _ctr in range(0, source.ip_range):
                    gbename = self.tengbes.names()[gbe_ctr]
                    gbe = self.tengbes[gbename]
                    rxaddress = '%s%d' % (rxaddr_prefix, rxaddr_base + _ctr)
                    LOGGER.info('\t{} subscribing to address {}'.format(
                        str(gbe.name), str(rxaddress),
                    ))
                    gbe.multicast_receive(rxaddress, 0)
                    gbe_ctr += 1
        LOGGER.info('done.')

    def host_okay(self):
        """
        Is this host/LRU okay?
        :return:
        """
        if not self.check_rx():
            LOGGER.error('{}: host_okay() - FALSE.'.format(self.host))
            return False
        LOGGER.info('{}: host_okay() - TRUE.'.format(self.host))
        return True

    def check_rx_reorder(self):
        """
        Is this Filter host reordering received data correctly?
        :return:
        """
        def get_gbe_data():
            data = {}
            for pol in [0, 1]:
                reord_errors = self.registers['updebug_reord_err%i' % pol].read()['data']
                data['re%i_cnt' % pol] = reord_errors['cnt']
                data['re%i_time' % pol] = reord_errors['time']
                data['re%i_tstep' % pol] = reord_errors['timestep']
                data['timerror%i' % pol] = reord_errors['timestep']
            valid_cnt = self.registers.updebug_validcnt.read()['data']
            data['valid_arb'] = valid_cnt['arb']
            data['valid_reord'] = valid_cnt['reord']
            data['mcnt_relock'] = self.registers.mcnt_relock.read()['data']['reg']
            return data
        _sleeptime = 1
        rxregs = get_gbe_data()
        time.sleep(_sleeptime)
        rxregs_new = get_gbe_data()
        if rxregs_new['valid_arb'] == rxregs['valid_arb']:
            LOGGER.error('%s: arbiter is not counting packets. %i -> %i' %
                         (self.host, rxregs_new['valid_arb'], rxregs['valid_arb']))
            return False
        if rxregs_new['valid_reord'] == rxregs['valid_reord']:
            LOGGER.error('%s: reorder is not counting packets. %i -> %i' %
                         (self.host, rxregs_new['valid_reord'], rxregs['valid_reord']))
            return False
        if rxregs_new['mcnt_relock'] > rxregs['mcnt_relock']:
            LOGGER.error('%s: mcnt_relock is triggering. %i -> %i' %
                         (self.host, rxregs_new['mcnt_relock'], rxregs['mcnt_relock']))
            return False
        for pol in [0, 1]:
            if rxregs_new['re%i_cnt' % pol] > rxregs['re%i_cnt' % pol]:
                LOGGER.error('%s: pol %i reorder count error. %i -> %i' %
                             (self.host, pol, rxregs_new['re%i_cnt' % pol], rxregs['re%i_cnt' % pol]))
                return False
            if rxregs_new['re%i_time' % pol] > rxregs['re%i_time' % pol]:
                LOGGER.error('%s: pol %i reorder time error. %i -> %i' %
                             (self.host, pol, rxregs_new['re%i_time' % pol], rxregs['re%i_time' % pol]))
                return False
            if rxregs_new['re%i_tstep' % pol] > rxregs['re%i_tstep' % pol]:
                LOGGER.error('%s: pol %i timestep error. %i -> %i' %
                             (self.host, pol, rxregs_new['re%i_tstep' % pol], rxregs['re%i_tstep' % pol]))
                return False
            if rxregs_new['timerror%i' % pol] > rxregs['timerror%i' % pol]:
                LOGGER.error('%s: pol %i time error? %i -> %i' %
                             (self.host, pol, rxregs_new['timerror%i' % pol], rxregs['timerror%i' % pol]))
                return False
        LOGGER.info('%s: reordering data okay.' % self.host)
        return True

    def read_spead_counters(self):
        """
        Read the SPEAD rx and error counters for this Filter host
        :return:
        """
        rv = []
        for core_ctr in range(0, len(self.tengbes)):
            counter = self.registers['updebug_sp_val%i' % core_ctr].read()['data']['reg']
            error = self.registers['updebug_sp_err%i' % core_ctr].read()['data']['reg']
            rv.append((counter, error))
        return rv

    def get_local_time(self):
        """
        Get the local timestamp of this board, received from the digitiser
        :return: time in samples since the digitiser epoch
        """
        first_msw = self.registers.local_time_msw.read()['data']['timestamp_msw']
        while self.registers.local_time_msw.read()['data']['timestamp_msw'] == first_msw:
            time.sleep(0.01)
        lsw = self.registers.local_time_lsw.read()['data']['timestamp_lsw']
        msw = self.registers.local_time_msw.read()['data']['timestamp_msw']
        assert msw == first_msw + 1  # if this fails the network is waaaaaaaay slow
        return (msw << 32) | lsw
