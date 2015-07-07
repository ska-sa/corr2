__author__ = 'paulp'

import time
import logging

from host_fpga import FpgaHost
from data_source import DataSource
from casperfpga.tengbe import Mac
from casperfpga.tengbe import IpAddress

LOGGER = logging.getLogger(__name__)

def parse_sources(name_string, ip_string):
    """
    Parse lists of source name and IPs into a list of DataSource objects.
    :return:
    """
    source_names = name_string.strip().split(',')
    source_mcast = ip_string.strip().split(',')
    assert len(source_mcast) == len(source_names), (
        'Source names (%i) must be paired with multicast source '
        'addresses (%i)' % (len(source_names), len(source_mcast)))
    _sources = []
    source_ctr = 0
    for counter, address in enumerate(source_mcast):
        new_source = DataSource.from_mcast_string(address)
        new_source.name = source_names[counter]
        new_source.source_number = source_ctr
        _sources.append(new_source)
        if source_ctr > 0:
            assert new_source.ip_range == _sources[0].ip_range,\
                'DataSources have to offer the same IP range.'
        source_ctr += 1
    return _sources


class FpgaFilterHost(FpgaHost):
    """
    A Host, that hosts SNB filter engines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, board_id, instrument_config):
        self._config = instrument_config['filter']
        self._instrument_config = instrument_config
        _katcp_port = int(self._instrument_config['FxCorrelator']['katcp_port'])
        _bof = self._config['bitstream']
        _hosts = self._config['hosts'].strip().split(',')
        FpgaHost.__init__(self, _hosts[board_id], katcp_port=_katcp_port, boffile=_bof, connect=True)
        self.board_id = board_id
        self.data_sources = []
        self.data_destinations = []

    def initialise(self):
        """
        Initialise this filter board once data from the digitiser is available.
        :return:
        """
        self.registers.receptor_id.write(pol0_id=0, pol1_id=1)
        self.set_igmp_version(self._instrument_config['FxCorrelator']['igmp_version'])
        self._set_destinations()
        self._handle_sources()
        self.setup_rx()
        self._subscribe_to_source_data()
        if not self.check_rx():
            raise RuntimeError('Filter {} is not receiving data correctly.'.format(self.host))
        self.enable_tx()
        # TODO - check tx must not bail hard if the registers aren't there
        # if not self.check_tx_raw():
        #     raise RuntimeError('Filter {} is not transmitting data correctly.'.format(self.host))

    def enable_tx(self):
        """
        Enable transmission on this filter engine.
        :return:
        """
        self.registers.control.write(gbe_txen=True)
        LOGGER.info('{}: filter output enabled.'.format(self.host))

    def _set_destinations(self):
        """
        Set the destination for the filtered data, as configured
        :return:
        """
        _destinations_per_filter = 4  # eish, this is hardcoded for now...
        _destinations = parse_sources(name_string=self._instrument_config['fengine']['source_names'],
                                      ip_string=self._instrument_config['fengine']['source_mcast_ips'],)
        LOGGER.info('{}: assuming {} source items per filter board'.format(
            self.host, _destinations_per_filter))
        _offset = self.board_id * _destinations_per_filter
        self.data_destinations = []
        for _ctr in range(_offset, _offset + _destinations_per_filter):
            self.data_destinations.append(_destinations[_ctr])
            LOGGER.info('{}: assigning destination {} to host at position {}.'.format(
                self.host, _destinations[_ctr], _ctr,
            ))
        assert len(self.data_destinations) == _destinations_per_filter,\
            'Currently only %i outputs are accepted for filter boards.' % _destinations_per_filter

        for d in self.data_destinations:
            print str(d.ip_address)

        from casperfpga import tengbe
        self.data_destinations[0].ip_address = tengbe.IpAddress('239.2.0.20')
        self.data_destinations[1].ip_address = tengbe.IpAddress('239.2.0.21')
        self.data_destinations[2].ip_address = tengbe.IpAddress('239.2.0.22')
        self.data_destinations[3].ip_address = tengbe.IpAddress('239.2.0.23')

        self.registers.gbe_iptx0.write_int(int(self.data_destinations[0].ip_address))
        self.registers.gbe_iptx1.write_int(int(self.data_destinations[1].ip_address))
        self.registers.gbe_iptx2.write_int(int(self.data_destinations[2].ip_address))
        self.registers.gbe_iptx3.write_int(int(self.data_destinations[3].ip_address))
        self.registers.gbe_porttx.write_int(self.data_destinations[0].port)

    def clear_status(self):
        """
        Clear the status registers and counters on this filter board
        :return:
        """
        self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse', cnt_rst='pulse')

    def setup_rx(self):
        """
        Set up the RX side of the filter. 10gbe ports, etc.
        Check that the board is receiving data correctly.
        :return:
        """
        assert self.board_id > -1, 'The board ID cannot be -1, it must be zero or greater.'
        self.registers.control.write(gbe_txen=False)
        self.registers.control.write(gbe_rst=True)
        self.clear_status()
        _num_tengbes = len(self.tengbes)
        _ip_octets = [int(bit) for bit in self._config['10gbe_start_ip'].split('.')]
        _port = int(self._config['10gbe_port'])
        assert len(_ip_octets) == 4, 'That\'s an odd IP address: {}'.format(str(_ip_octets))
        _ip_base = 0 + (self.board_id * _num_tengbes)
        _ip_start = int(IpAddress(self._config['10gbe_start_ip']))

        _mac_start = int(Mac(self._config['10gbe_start_mac']))
        _mac_base = 0 + (self.board_id * _num_tengbes)
        for _gbe in self.tengbes:
            this_mac = _mac_start + _mac_base
            this_ip = _ip_start + _ip_base
            _gbe.setup(mac=this_mac, ipaddress=this_ip,
                       port=_port)
            LOGGER.info('{}: gbe({}) MAC({}) IP({}) port({}) board({})'.format(
                self.host, _gbe.name, str(Mac(this_mac)), str(IpAddress(this_ip)), _port, self.board_id))
            _mac_base += 1
            _ip_base += 1
        for _gbe in self.tengbes:
            _gbe.tap_start(True)
        self.registers.control.write(gbe_rst=False)

    def _handle_sources(self):
        """
        Sort out sources for this filter host
        :return:
        """
        _sources = parse_sources(name_string=self._config['source_names'],
                                 ip_string=self._config['source_mcast_ips'])
        # assign the correct sources to this filter host
        _sources_per_filter = len(_sources) / len(self._config['hosts'].strip().split(','))
        LOGGER.info('{}: assuming {} source items per filter board'.format(
            self.host, _sources_per_filter))

        _source_offset = self.board_id * _sources_per_filter
        self.data_sources = []
        for _ctr in range(_source_offset, _source_offset + _sources_per_filter):
            self.data_sources.append(_sources[_ctr])
            LOGGER.info('{}: assigning source {} to host at position {}.'.format(
                self.host, _sources[_ctr], _ctr,
            ))

    def _subscribe_to_source_data(self):
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
