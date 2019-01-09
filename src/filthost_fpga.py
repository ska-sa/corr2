from logging import INFO

from host_fpga import FpgaHost
from casperfpga.transport_skarab import SkarabTransport
from corr2LogHandlers import getLogger

import utils as c2_utils

# LOGGER = logging.getLogger(__name__)


# Technically an instance of this should never exist (?)
class FpgaFilterHost(FpgaHost):
    """
    A Host, that hosts SNB filter engines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, board_id, instrument_config, *args, **kwargs):
        """
        Create a filter host
        :param board_id:
        :param instrument_config:
        :return:
        """
        # Just in case...
        try:
            self.getLogger = kwargs['getLogger']
        except KeyError:
            self.getLogger = getLogger

        # No idea
        logger_name = 'FpgaFilterHost_{}'.format(board_id)
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)

        result, self.logger = self.getLogger(logger_name=logger_name,
                                     log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(self.descriptor)
            raise ValueError(errmsg)

        if isinstance(instrument_config, basestring):
            instrument_config = c2_utils.parse_ini_file(instrument_config)
        self._config = instrument_config['filter']

        self.new_style = self._config['new_style'] == 'true'

        self._instrument_config = instrument_config
        _katcp_port = int(self._instrument_config['FxCorrelator']['katcp_port'])
        _bof = self._config['bitstream']
        _hosts = self._config['hosts'].strip().split(',')

        super(FpgaFilterHost, self).__init__(_hosts[board_id],
                                             katcp_port=_katcp_port,
                                             bitstream=_bof,
                                             transport=SkarabTransport,
                                             connect=True)

        self.board_id = board_id
        self.data_sources = []
        self.data_destinations = []

    def enable_tx(self):
        """
        Enable transmission on this filter engine.
        :return:
        """
        self.registers.control.write(gbe_txen=True)
        self.logger.info('{}: filter output enabled.'.format(self.host))

    def subscribe_to_source_data(self):
        """
        Subscribe the multicast source data as configured.
        :return:
        """
        self.logger.info('{}: subscribing to filter datasources...'.format(
            self.host))
        gbe_ctr = 0
        for source in self.data_sources:
            if not source.is_multicast():
                self.logger.info('\tsource address {} is not multicast?'.format(
                    str(source.ip_address)))
            else:
                rxaddr = str(source.ip_address)
                rxaddr_bits = rxaddr.split('.')
                rxaddr_base = int(rxaddr_bits[3])
                rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0],
                                               rxaddr_bits[1],
                                               rxaddr_bits[2])
                for _ctr in range(0, source.ip_range):
                    gbename = self.gbes.names()[gbe_ctr]
                    gbe = self.gbes[gbename]
                    rxaddress = '%s%d' % (rxaddr_prefix, rxaddr_base + _ctr)
                    self.logger.info('\t{} subscribing to address {}'.format(
                        str(gbe.name), str(rxaddress),
                    ))
                    gbe.multicast_receive(rxaddress, 0)
                    gbe_ctr += 1
        self.logger.info('done.')

    def host_okay(self):
        """
        Is this host/LRU okay?
        :return:
        """
        if not self.check_rx():
            self.logger.error('{}: host_okay() - FALSE.'.format(self.host))
            return False
        self.logger.info('{}: host_okay() - TRUE.'.format(self.host))
        return True

    # Methods from DigitiserStreamReceiver
    def get_rx_reorder_status(self):
        """
        Read the reorder block counters
        :return:
        """
        if 'reorder_ctrs' in self.registers.names():
            reorder_ctrs = self.registers.reorder_ctrs.read()['data']
            self.logger.debug('found reorder_ctrs')
        else:
            reorder_ctrs = self.registers.reorder_status.read()['data']
            self.logger.debug('found reorder_status'.format(reorder_ctrs))
        try:
            reorder_ctrs.update(self.registers.reorder_status1.read()['data'])
            self.logger.debug('found reorder_status1'.format(reorder_ctrs))
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
        self.logger.debug('{}: status cleared.'.format(self.host))