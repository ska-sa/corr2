import logging

from digitiser_receiver import DigitiserStreamReceiver

import utils as c2_utils

LOGGER = logging.getLogger(__name__)


class FpgaFilterHost(DigitiserStreamReceiver):
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
        super(FpgaFilterHost, self).__init__(_hosts[board_id],
                                             katcp_port=_katcp_port,
                                             bitstream=_bof,
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
        LOGGER.info('{}: filter output enabled.'.format(self.host))

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
                rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0],
                                               rxaddr_bits[1],
                                               rxaddr_bits[2])
                for _ctr in range(0, source.ip_range):
                    gbename = self.gbes.names()[gbe_ctr]
                    gbe = self.gbes[gbename]
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
