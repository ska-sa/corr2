__author__ = 'paulp'

import time
import logging
from casperfpga import tengbe

from host_fpga import FpgaHost
from data_source import DataSource

LOGGER = logging.getLogger(__name__)


class FpgaFilterHost(FpgaHost):
    """
    A Host, that hosts SNB filter engines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, boffile=None, connect=True, config=None, board_id=-1):
        FpgaHost.__init__(self, host, katcp_port=katcp_port, boffile=boffile, connect=connect)
        self._config = config
        self.board_id = board_id
        self.data_sources = []  # a list of DataSources received by this filter host

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source, board_id):
        return cls(hostname, katcp_port=katcp_port,
                   boffile=config_source['bitstream'],
                   connect=True, config=config_source, board_id=board_id)

    def initialise(self):
        """
        Initialise this filter board once data from the digitiser is available.
        :return:
        """
        self.set_igmp_version(2)  # TODO - get this from the config, not hardcoded
        self._set_destination()
        self._handle_sources()
        self.setup_rx()
        self._subscribe_to_source_data()
        self.check_rx()

    def _set_destination(self):
        """
        Set the destination for the filtered data, as configured
        :return:
        """
        self.registers.gbe_iptx0.write_int(
            int(tengbe.IpAddress(self._config['pol0_destination_ip'])))
        self.registers.gbe_iptx1.write_int(
            int(tengbe.IpAddress(self._config['pol1_destination_ip'])))
        self.registers.gbe_porttx.write_int(int(self._config['destination_port']))

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
        _ip_base = _ip_octets[3] + (self.board_id * _num_tengbes)
        _ip_prefix = '%d.%d.%d.' % (_ip_octets[0], _ip_octets[1], _ip_octets[2])
        _mac_prefix = self._config['10gbe_macprefix']
        _mac_base = int(self._config['10gbe_macbase']) + (self.board_id * _num_tengbes)
        for _gbe in self.tengbes:
            this_mac = '%s%02x' % (_mac_prefix, _mac_base)
            this_ip = '%s%d' % (_ip_prefix, _ip_base)
            _gbe.setup(mac=this_mac, ipaddress=this_ip,
                       port=_port)
            LOGGER.info('filthost({}) gbe({}) MAC({}) IP({}) port({}) board({})'.format(
                self.host, _gbe.name, this_mac, this_ip, _port, self.board_id))
            _mac_base += 1
            _ip_base += 1

        for _gbe in self.tengbes:
            _gbe.tap_start(True)

        # release the cores from reset
        self.registers.control.write(gbe_rst=False)

    def _handle_sources(self):
        """
        Sort out sources for this filter host
        :return:
        """
        source_names = self._config['source_names'].strip().split(',')
        source_mcast = self._config['source_mcast_ips'].strip().split(',')
        assert len(source_mcast) == len(source_names), (
            'Source names (%i) must be paired with multicast source '
            'addresses (%i)' % (len(source_names), len(source_mcast)))

        # assemble the sources given into a list
        _sources = []
        source_ctr = 0
        for counter, address in enumerate(source_mcast):
            new_source = DataSource.from_mcast_string(address)
            new_source.name = source_names[counter]
            new_source.source_number = source_ctr
            _sources.append(new_source)
            if source_ctr > 0:
                assert(new_source.ip_range == _sources[0].ip_range,
                       'DataSources have to offer the same IP range.')
            source_ctr += 1

        # assign the correct sources to this filter host
        _sources_per_filter = len(_sources) / len(self._config['hosts'].strip().split(','))
        LOGGER.info('Assuming {} source items per filter board'.format(_sources_per_filter))

        _source_offset = self.board_id * _sources_per_filter
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
        LOGGER.info('{} subscribing to filter datasources...'.format(
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
            return False
        LOGGER.info('Filter host {} host_okay() - TRUE.'.format(self.host))
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
            LOGGER.error('Filter host %s arbiter is not counting packets. %i -> %i' %
                         (self.host, rxregs_new['valid_arb'], rxregs['valid_arb']))
            return False
        if rxregs_new['valid_reord'] == rxregs['valid_reord']:
            LOGGER.error('Filter host %s reorder is not counting packets. %i -> %i' %
                         (self.host, rxregs_new['valid_reord'], rxregs['valid_reord']))
            return False
        if rxregs_new['mcnt_relock'] > rxregs['mcnt_relock']:
            LOGGER.error('Filter host %s mcnt_relock is triggering. %i -> %i' %
                         (self.host, rxregs_new['mcnt_relock'], rxregs['mcnt_relock']))
            return False
        for pol in [0, 1]:
            if rxregs_new['re%i_cnt' % pol] > rxregs['re%i_cnt' % pol]:
                LOGGER.error('Filter host %s pol %i reorder count error. %i -> %i' %
                             (self.host, pol, rxregs_new['re%i_cnt' % pol], rxregs['re%i_cnt' % pol]))
                return False
            if rxregs_new['re%i_time' % pol] > rxregs['re%i_time' % pol]:
                LOGGER.error('Filter host %s pol %i reorder time error. %i -> %i' %
                             (self.host, pol, rxregs_new['re%i_time' % pol], rxregs['re%i_time' % pol]))
                return False
            if rxregs_new['re%i_tstep' % pol] > rxregs['re%i_tstep' % pol]:
                LOGGER.error('Filter host %s pol %i timestep error. %i -> %i' %
                             (self.host, pol, rxregs_new['re%i_tstep' % pol], rxregs['re%i_tstep' % pol]))
                return False
            if rxregs_new['timerror%i' % pol] > rxregs['timerror%i' % pol]:
                LOGGER.error('Filter host %s pol %i time error? %i -> %i' %
                             (self.host, pol, rxregs_new['timerror%i' % pol], rxregs['timerror%i' % pol]))
                return False
        LOGGER.info('Filter host %s is reordering data okay.' % self.host)
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

    def add_source(self, data_source):
        """
        Add a new data source to this Filter host
        :param data_source: A DataSource object
        :return:
        """
        # check that it doesn't already exist before adding it
        for source in self.data_sources:
            assert source.source_number != data_source.source_number
            assert source.name != data_source.name
        self.data_sources.append(data_source)
