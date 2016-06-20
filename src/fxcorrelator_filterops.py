import time

from casperfpga import utils as fpgautils
from casperfpga import tengbe

import filthost_fpga
from data_source import DataSource

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


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


class FilterOperations(object):

    def __init__(self, corr_obj):
        """
        A collection of filter operations that act on/with a correlator instance.
        :param corr_obj:
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.fhosts
        self.logger = corr_obj.logger
        # do config things

    def initialise(self, program=True):
        """
        Set up filter engines
        :return:
        """
        self.hosts = []
        _filthosts = self.corr.configd['filter']['hosts'].strip().split(',')
        self.logger.info('Adding filter boards:')
        for ctr, _ in enumerate(_filthosts):
            _fpga = filthost_fpga.FpgaFilterHost(ctr, self.corr.configd)
            self.hosts.append(_fpga)
            self.logger.info('\t{} added to filters'.format(_fpga.host))
        self.logger.info('done.')
    
        # hand out source and destination IPs
        self._process_sources()
        self._process_destinations()
    
        # program the boards
        if program:
            THREADED_FPGA_FUNC(self.hosts, timeout=10,
                               target_function=('upload_to_ram_and_program',
                                                (self.hosts[0].boffile,),))
        else:
            THREADED_FPGA_FUNC(self.hosts, timeout=5,
                               target_function='get_system_information')
    
        if program:
            # TODO read the pol IDs from the stream?
            THREADED_FPGA_OP(self.hosts, timeout=5,
                             target_function=(lambda fpga_:
                                              fpga_.registers.receptor_id.write(pol0_id=0, pol1_id=1),))
            THREADED_FPGA_FUNC(self.hosts, timeout=5,
                               target_function=('set_igmp_version',
                                                (self.corr.configd['FxCorrelator']['igmp_version'])))
    
            THREADED_FPGA_OP(self.hosts, timeout=5,
                             target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))
            THREADED_FPGA_OP(self.hosts, timeout=5,
                             target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=True),))
    
            # write the TX registers
            self._write_tx_registers()
    
            # write the TX port
            THREADED_FPGA_OP(self.hosts, timeout=5,
                             target_function=(lambda fpga_:
                                              fpga_.registers.gbe_porttx.write_int(
                                                  fpga_.data_destinations[0].port),))
    
            # set up the 10gbe cores
            self._setup_tengbe()
    
            THREADED_FPGA_OP(self.hosts, timeout=5,
                             target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=False),))
    
            # subscribe to multicast data
            THREADED_FPGA_FUNC(self.hosts, timeout=5,
                               target_function='subscribe_to_source_data')
    
            # check the RX data
            self.logger.info('filter_ops: waiting for data.')
            time.sleep(5.0)
            THREADED_FPGA_OP(
                self.hosts, timeout=5,
                target_function=(
                    lambda fpga_: fpga_.registers.control.write(sys_rst='pulse'),))
            THREADED_FPGA_FUNC(self.hosts, timeout=5,
                               target_function='clear_status')
            time.sleep(1.0)
            if not self._check_rx():
                raise RuntimeError('One or more filter engines are not '
                                   'receiving data.')
    
            # enable TX
            THREADED_FPGA_FUNC(self.hosts, timeout=5,
                               target_function='enable_tx')
            # check the TX data
            THREADED_FPGA_FUNC(self.hosts, timeout=5,
                               target_function='clear_status')
            if not self._check_tx_raw():
                raise RuntimeError('One or more filter engines are not transmitting data.')

    def _check_tx_raw(self, max_waittime=30):
        """
        Check that the filter-engines are transmitting data correctly
        :param max_waittime:
        :return:
        """
        self.logger.info('Checking Filter hosts are transmitting data...')
        results = THREADED_FPGA_FUNC(self.hosts, timeout=max_waittime+1,
                                     target_function='check_tx_raw',)
        all_okay = True
        for _v in results.values():
            all_okay = all_okay and _v
        if not all_okay:
            self.logger.error('\tERROR in Filter-engine tx data.')
        self.logger.info('\tdone.')
        return all_okay

    def _check_rx(self, max_waittime=30):
        """
        Check that the filter-engines are receiving data correctly
        :param max_waittime:
        :return:
        """
        self.logger.info('Checking Filter hosts are receiving data...')
        results = THREADED_FPGA_FUNC(self.hosts, timeout=max_waittime+1,
                                     target_function=('check_rx', (max_waittime,),))
        all_okay = True
        for _v in results.values():
            all_okay = all_okay and _v
        if not all_okay:
            self.logger.error('\tERROR in Filter-engine rx data.')
        self.logger.info('\tdone.')
        return all_okay

    def _setup_tengbe(self):
        """
        Set up the 10gbe cores on the filter hosts
        :param corr: the correlator instance
        :return:
        """
        # set up the 10gbe cores
        feng_port = int(self.corr.configd['filter']['10gbe_port'])
        mac_start = tengbe.Mac(self.corr.configd['filter']['10gbe_start_mac'])
        # set up shared board info
        boards_info = {}
        board_id = 0
        mac = int(mac_start)
        for f in self.hosts:
            macs = []
            for gbe in f.tengbes:
                macs.append(mac)
                mac += 1
            boards_info[f.host] = board_id, macs
            board_id += 1
    
        def setup_gbes(f):
            board_id, macs = boards_info[f.host]
            for gbe, this_mac in zip(f.tengbes, macs):
                gbe.setup(mac=this_mac, ipaddress='0.0.0.0', port=feng_port)
                self.logger.debug(
                    'filthost(%s) gbe(%s) mac(%s) port(%i) board_id(%i)' %
                    (f.host, gbe.name, str(gbe.mac), feng_port, f.board_id,))
                gbe.dhcp_start()
        # THREADED_FPGA_OP(self.hosts, timeout=30, target_function=(setup_gbes,))
        for _fpga in self.hosts:
            setup_gbes(_fpga)
    
        for _fpga in self.hosts:
            for _gbe in _fpga.tengbes:
                self.logger.info('{}: {} got address {}'.format(_fpga.host, _gbe.name,
                                                                _gbe.core_details['ip']))
    
    def _process_destinations(self):
        """
        Process the destinations found in the config file, assigning them
        to the filter hosts.
        :param corr: the correlator instance
        :return:
        """
        _destinations_per_filter = 2  # eish, this is hardcoded for now...
        _destinations = parse_sources(
            name_string=self.corr.configd['fengine']['source_names'],
            ip_string=self.corr.configd['fengine']['source_mcast_ips'],)
        self.logger.info('filterops._process_destinations: assuming '
                         '{} destinations per filter '
                         'board'.format(_destinations_per_filter))
    
        for _filtfpga in self.hosts:
            _offset = _filtfpga.board_id * _destinations_per_filter
            _filtfpga.data_destinations = []
            for _ctr in range(_offset, _offset + _destinations_per_filter):
                _filtfpga.data_destinations.append(_destinations[_ctr])
                self.logger.info('{}: assigning destination {} to host at '
                                 'position {}.'.format(_filtfpga.host,
                                                       _destinations[_ctr],
                                                       _ctr, ))
            assert len(_filtfpga.data_destinations) == _destinations_per_filter,\
                'Currently only %i outputs are accepted for filter ' \
                'boards.' % _destinations_per_filter

    def _write_tx_registers(self):
        """
        Actually write the IP addresses to the TX registers
        """
        def _write_tx_regs(filthost):
            _dest_ctr = 0
            for _dest in filthost.data_destinations:
                for _range in range(0, _dest.ip_range):
                    _dest_ip = int(_dest.ip_address) + _range
                    filthost.registers['gbe_iptx%i' % _dest_ctr].write_int(_dest_ip)
                    self.logger.debug('{}: wrote TX IP {} to register {}'.format(
                        filthost.host, str(tengbe.IpAddress(_dest_ip)),
                        'gbe_iptx%i' % _dest_ctr,
                    ))
                    _dest_ctr += 1
        THREADED_FPGA_OP(self.hosts, timeout=5,
                         target_function=_write_tx_regs)

    def _process_sources(self):
        """
        Process the sources found in the config file, assigning them to the
        filter hosts.
        :param corr: the correlator instance
        :return:
        """
        _config = self.corr.configd['filter']
        _sources = parse_sources(name_string=_config['source_names'],
                                 ip_string=_config['source_mcast_ips'])
        _sources_per_filter = len(_sources) / len(self.hosts)
        self.logger.info('filterops._process_sources: assuming {} DataSources '
                         'per filter board'.format(_sources_per_filter))
        for _filtfpga in self.hosts:
            _source_offset = _filtfpga.board_id * _sources_per_filter
            _filtfpga.data_sources = []
            for _ctr in range(_source_offset, _source_offset + _sources_per_filter):
                _filtfpga.data_sources.append(_sources[_ctr])
                self.logger.info('{}: assigning source {} to host at position {}.'.format(
                    _filtfpga.host, _sources[_ctr], _ctr,
                ))

# end
