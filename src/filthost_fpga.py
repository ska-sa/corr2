__author__ = 'paulp'

import time
import logging

from host_fpga import FpgaHost
import utils as c2_utils

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
        if isinstance(instrument_config, basestring):
            instrument_config = c2_utils.parse_ini_file(instrument_config)
        self._config = instrument_config['filter']

        self.new_style = self._config['new_style'] == 'true'

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
        if not self.new_style:
            self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse',
                                         cnt_rst='pulse', unpack_cnt_rst='pulse')
        else:
            self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse',
                                         cnt_rst='pulse', )
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
        Is this F host reordering received data correctly?
        :return:
        """

        if not self.new_style:
            return self.OLD_check_rx_reorder()

        def get_gbe_data():
            data = {}
            reorder_ctrs = self.registers.reorder_ctrs.read()['data']
            data['mcnt_relock'] = reorder_ctrs['mcnt_relock']
            data['timerror'] = reorder_ctrs['timestep_error']
            data['discard'] = reorder_ctrs['discard']
            num_tengbes = len(self.tengbes)
            for gbe in range(num_tengbes):
                data['pktof_ctr%i' % gbe] = reorder_ctrs['pktof%i' % gbe]
            for pol in range(0, 2):
                data['recverr_ctr%i' % pol] = reorder_ctrs['recverr%i' % pol]
            return data
        _sleeptime = 1
        rxregs = get_gbe_data()
        time.sleep(_sleeptime)
        rxregs_new = get_gbe_data()
        num_tengbes = len(self.tengbes)
        if num_tengbes < 1:
            raise RuntimeError('F-host with no 10gbe cores %s' % self.host)
        got_errors = False
        for gbe in range(num_tengbes):
            if rxregs_new['pktof_ctr%i' % gbe] != rxregs['pktof_ctr%i' % gbe]:
                LOGGER.error('F host %s packet overflow on interface gbe%i. %i -> %i' % (
                    self.host, gbe, rxregs_new['pktof_ctr%i' % gbe],
                    rxregs['pktof_ctr%i' % gbe]))
                got_errors = True
        for pol in range(0, 2):
            if rxregs_new['recverr_ctr%i' % pol] != rxregs['recverr_ctr%i' % pol]:
                LOGGER.error('F host %s pol %i reorder count error. %i -> %i' % (
                    self.host, pol, rxregs_new['recverr_ctr%i' % pol],
                    rxregs['recverr_ctr%i' % pol]))
                got_errors = True
        if rxregs_new['mcnt_relock'] != rxregs['mcnt_relock']:
            LOGGER.error('F host %s mcnt_relock is changing. %i -> %i' % (
                self.host, rxregs_new['mcnt_relock'], rxregs['mcnt_relock']))
            got_errors = True
        if rxregs_new['timerror'] != rxregs['timerror']:
            LOGGER.error('F host %s timestep error is changing. %i -> %i' % (
                self.host, rxregs_new['timerror'], rxregs['timerror']))
            got_errors = True
        if rxregs_new['discard'] != rxregs['discard']:
            LOGGER.error('F host %s discarding packets. %i -> %i' % (
                self.host, rxregs_new['discard'], rxregs['discard']))
            got_errors = True
        if got_errors:
            LOGGER.error('One or more errors detected, check logs.')
            return False
        LOGGER.info('%s: is reordering data okay.' % self.host)
        return True

    def OLD_check_rx_reorder(self):
        attempts = 5
        done = self._check_rx_reorder()
        while (not done) and (attempts > 0):
            self.clear_status()
            done = self._check_rx_reorder()
            attempts -= 1
        return done

    def _check_rx_reorder(self):
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
            valid_cnt = self.registers.updebug_validcnt.read()['data']
            data['valid_arb'] = valid_cnt['arb']
            data['valid_reord'] = valid_cnt['reord']
            data['mcnt_relock'] = self.registers.mcnt_relock.read()['data']['reg']
            return data
        _sleeptime = 1
        rxregs = get_gbe_data()
        time.sleep(_sleeptime)
        rxregs_new = get_gbe_data()
        got_error = False
        if rxregs_new['valid_arb'] == rxregs['valid_arb']:
            LOGGER.error('%s: arbiter is not counting packets. %i -> %i' %
                         (self.host, rxregs_new['valid_arb'], rxregs['valid_arb']))
            got_error = True
        if rxregs_new['valid_reord'] == rxregs['valid_reord']:
            LOGGER.error('%s: reorder is not counting packets. %i -> %i' %
                         (self.host, rxregs_new['valid_reord'], rxregs['valid_reord']))
            got_error = True
        if rxregs_new['mcnt_relock'] > rxregs['mcnt_relock']:
            LOGGER.error('%s: mcnt_relock is triggering. %i -> %i' %
                         (self.host, rxregs_new['mcnt_relock'], rxregs['mcnt_relock']))
            got_error = True
        for pol in [0, 1]:
            regname = 're%i_tstep' % pol
            if (rxregs_new[regname] != 0) or (rxregs[regname] != 0):
                LOGGER.error('%s: pol %i timestep error. %i, %i' %
                             (self.host, pol, rxregs_new['re%i_tstep' % pol], rxregs['re%i_tstep' % pol]))
                got_error = True
        if got_error:
            return False
        LOGGER.info('%s: reordering data okay.' % self.host)
        return True

    def OLD_read_spead_counters(self):
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

    def read_spead_counters(self):
        """
        Read the SPEAD rx and error counters for this F host
        :return:
        """

        if not self.new_style:
            return self.OLD_read_spead_counters()

        rv = []
        spead_ctrs = self.registers.spead_ctrs.read()['data']
        for core_ctr in range(0, len(self.tengbes)):
            counter = spead_ctrs['rx_cnt%i' % core_ctr]
            error = spead_ctrs['err_cnt%i' % core_ctr]
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
