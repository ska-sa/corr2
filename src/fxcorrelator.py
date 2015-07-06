"""
Created on Feb 28, 2013

@author: paulp
"""

# things all fxcorrelators Instruments do

# to start the digitiser in the lab:

# paulp@dbertsc:/home/henno/work/projects/d_engine/scripts/svn/dig003$ ./m1130_2042sdp_rev1_of_start.py

# if power cycles, then: ./config.py -b 3
# this will configure the correct image on the digitiser, not the test one

import logging
import socket
import time
import sys

import numpy
import struct
import spead64_48 as spead

from casperfpga import tengbe
from casperfpga import utils as fpgautils

import log
import utils
import xhost_fpga
import fhost_fpga

from instrument import Instrument
from data_source import DataSource
import fxcorrelator_fengops as fengops
import fxcorrelator_xengops as xengops

use_xeng_sim = False

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

class FxCorrelator(Instrument):
    """
    A generic FxCorrelator composed of fengines that channelise antenna inputs and
    xengines that each produce cross products from a continuous portion of the channels and accumulate the result.
    SPEAD data products are produced.
    """
    def __init__(self, descriptor, identifier=-1, config_source=None, logger=None, log_level=logging.INFO):
        """
        An abstract base class for instruments.
        :param descriptor: A text description of the instrument. Required.
        :param identifier: An optional integer identifier.
        :param config_source: The instrument configuration source. Can be a text file, hostname, whatever.
        :param logger: Use the module logger by default, unless something else is given.
        :param logger: The loglevel to use by default, logging.INFO.
        :return: <nothing>
        """
        # first thing to do is handle the logging - set the root logging handler - submodules loggers will
        # automatically use it
        self.loghandler = log.Corr2LogHandler()
        logging.root.addHandler(self.loghandler)
        logging.root.setLevel(log_level)
        self.logger = logger or logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        self.logger.addHandler(self.loghandler)

        # set the SPEAD logger to warning only
        spead_logger = logging.getLogger('spead')
        spead_logger.setLevel(logging.WARNING)

        # we know about f and x hosts and engines, not just engines and hosts
        self.fhosts = []
        self.xhosts = []

        # attributes
        self.katcp_port = None
        self.f_per_fpga = None
        self.x_per_fpga = None
        self.accumulation_len = None
        self.xeng_accumulation_len = None
        self.xeng_tx_destination = None
        self.meta_destination = None
        self.fengine_sources = None

        self.spead_tx = None
        self.spead_meta_ig = None

        self._sensors = {}

        # parent constructor
        Instrument.__init__(self, descriptor, identifier, config_source)

        self._initialised = False

    def initialise(self, program=True, tvg=False, fake_digitiser=False, qdr_cal=True):
        """
        Set up the correlator using the information in the config file.
        :return:

        fengine init:
            eq
            set up interfaces (10gbe) - remember the sequence of holding in reset
            check feng rx
            check producing data?
            enable feng tx
            (check status?)
            check qdr cal?

        xengine init:
            vacc
            set up interfaces (10gbe) - remember the sequence of holding in reset
            check rx
            errors?
            check producing
            enable tx
        """

        # set up the filter boards if we need to
        if 'filter' in self.configd:
            self.logger.info('Adding filter hosts:')
            import filthost_fpga
            self.filthosts = []
            _filthosts = self.configd['filter']['hosts'].strip().split(',')
            for ctr, _ in enumerate(_filthosts):
                _fpga = filthost_fpga.FpgaFilterHost(ctr, self.configd)
                self.filthosts.append(_fpga)
                self.logger.info('\tFilter host {} added'.format(_fpga.host))
            self.logger.info('done.')
            # program the boards
            THREADED_FPGA_FUNC(self.filthosts, timeout=10, target_function=('upload_to_ram_and_program',
                                                                            (self.filthosts[0].boffile,),))
            # initialise them
            THREADED_FPGA_FUNC(self.filthosts, timeout=10, target_function=('initialise', (),))

        # connect to the other hosts that make up this correlator
        THREADED_FPGA_FUNC(self.fhosts, timeout=5, target_function='connect')
        THREADED_FPGA_FUNC(self.xhosts, timeout=5, target_function='connect')

        igmp_version = self.configd['FxCorrelator'].get('igmp_version')
        if igmp_version is not None:
            self.logger.info('Setting FPGA hosts IGMP version to %s', igmp_version)
            THREADED_FPGA_FUNC(
                self.fhosts + self.xhosts, timeout=5, target_function=(
                    'set_igmp_version', (igmp_version, ), {}))

        # if we need to program the FPGAs, do so
        if program:
            self.logger.info('Programming FPGA hosts')
            ftups = []
            for f in self.xhosts:
                ftups.append((f, f.boffile))
            for f in self.fhosts:
                ftups.append((f, f.boffile))
            fpgautils.program_fpgas(ftups, progfile=None, timeout=15)
            # this does not wait for the programming to complete, so it won't get all the
            # system information

        # load information from the running boffiles
        self.logger.info('Loading design information')
        THREADED_FPGA_FUNC(self.fhosts, timeout=10, target_function='get_system_information')
        THREADED_FPGA_FUNC(self.xhosts, timeout=10, target_function='get_system_information')

        if program:
            # cal the qdr on all boards
            if qdr_cal:
                self.qdr_calibrate()
            else:
                self.logger.info('Skipping QDR cal - are you sure you want to do this?')

            # init the f engines
            fengops.feng_initialise(self)

            # init the x engines
            xengops.xeng_initialise(self)

            # for fpga_ in self.fhosts:
            #     fpga_.tap_arp_reload()
            # for fpga_ in self.xhosts:
            #     fpga_.tap_arp_reload()
            self.logger.info('Waiting %d seconds for ARP to settle...' % self.arp_wait_time)
            sys.stdout.flush()
            starttime = time.time()
            time.sleep(self.arp_wait_time)
            # raw_input('wait for arp')
            end_time = time.time()
            self.logger.info('\tDone. That took %d seconds.' % (end_time - starttime))
            # sys.stdout.flush()

            # subscribe all the engines to the multicast groups
            fengops.feng_subscribe_to_multicast(self)
            xengops.xeng_subscribe_to_multicast(self)
            post_mess_delay = 5
            self.logger.info('post mess-with-the-switch delay of %is' % post_mess_delay)
            time.sleep(post_mess_delay)
            
            self.logger.info('Forcing an f-engine resync')
            for f in self.fhosts:
                f.registers.control.write(sys_rst='pulse')
            time.sleep(1)

            # reset all counters on fhosts and xhosts
            fengops.feng_clear_status_all()
            xengops.xeng_clear_status_all(self)

            # check to see if the f engines are receiving all their data
            if not fengops.feng_check_rx():
                raise RuntimeError('The f-engines RX have a problem.')

            # start f-engine TX
            self.logger.info('Starting f-engine datastream')
            THREADED_FPGA_OP(self.fhosts, timeout=5,
                             target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=True),))

            # check that the F-engines are transmitting data correctly
            if not fengops.feng_check_tx():
                raise RuntimeError('The f-engines TX have a problem.')

            # check that the X-engines are receiving data
            if not xengops.xeng_check_rx(self):
                raise RuntimeError('The x-engines RX have a problem.')

            # arm the vaccs on the x-engines
            xengops.xeng_vacc_sync(self)

        # reset all counters on fhosts and xhosts
        fengops.feng_clear_status_all()
        xengops.xeng_clear_status_all(self)

        # set an initialised flag
        self._initialised = True

        # start the vacc check timer
        xengops.xeng_setup_vacc_check_timer(self)

    # def qdr_calibrate_SERIAL(self):
    #     for hostlist in [self.fhosts, self.xhosts]:
    #         for host in hostlist:
    #             print host.host
    #             for qdr in host.qdrs:
    #                 qdr.qdr_cal(fail_hard=False, verbosity=2)

    def qdr_calibrate(self):
        """
        Run a software calibration routine on all the FPGA hosts.
        :return:
        """
        # cal the QDR specifically
        def _qdr_cal(_fpga):
            _results = {}
            for _qdr in _fpga.qdrs:
                _results[_qdr.name] = _qdr.qdr_cal(fail_hard=False)
            return _results
        qdr_calfail = False
        self.logger.info('Calibrating QDR on F- and X-engines, this takes a while.')
        for hostlist in [self.fhosts, self.xhosts]:
            results = THREADED_FPGA_OP(hostlist, timeout=30, target_function=(_qdr_cal,))
            for fpga, result in results.items():
                self.logger.info('FPGA %s QDR cal results:' % fpga)
                for qdr, qdrres in result.items():
                    if not qdrres:
                        qdr_calfail = True
                    self.logger.info('\t%s: cal okay: %s' % (qdr, 'True' if qdrres else 'False'))
        if qdr_calfail:
            raise RuntimeError('QDR calibration failure.')
        # for host in self.fhosts:
        #     for qdr in host.qdrs:
        #         qdr.qdr_delay_in_step(0b111111111111111111111111111111111111, -1)
        #
        # for host in self.xhosts:
        #     for qdr in host.qdrs:
        #         qdr.qdr_delay_in_step(0b111111111111111111111111111111111111, -1)

    def set_labels(self, newlist):
        """
        Apply new source labels to the configured fengine sources.
        :param newlist:
        :return:
        """
        if len(newlist) != len(self.fengine_sources):
            self.logger.error('Number of supplied source labels does not match number of configured sources.')
            return False
        metalist = []
        for ctr, source in enumerate(self.fengine_sources):
            # update the source name
            old_name = source.name
            source.name = newlist[ctr]
            # update the eq associated with that name
            found_eq = False
            for fhost in self.fhosts:
                if old_name in fhost.eqs.keys():
                    fhost.eqs[source.name] = fhost.eqs.pop(old_name)
                    found_eq = True
                    break
            if not found_eq:
                raise ValueError('Could not find the old EQ value, %s, to update to new name, %s.' %
                                 (old_name, source.name))
            metalist.append((source.name, ctr))
        if self.spead_meta_ig is not None:
            self.spead_meta_ig['input_labelling'] = numpy.array(metalist)
            self.spead_tx.send_heap(self.spead_meta_ig.get_heap())

    def get_labels(self):
        """
        Get the current fengine source labels as a string.
        :return:
        """
        source_names = ''
        for source in self.fengine_sources:
            source_names += source.name + ' '
        source_names = source_names.strip()
        return source_names

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if the instrument read a config successfully, raise an error if not?
        """
        Instrument._read_config(self)

        # check that the bitstream names are present
        try:
            open(self.configd['fengine']['bitstream'], 'r').close()
            open(self.configd['xengine']['bitstream'], 'r').close()
        except IOError:
            self.logger.error('xengine bitstream: %s' % self.configd['xengine']['bitstream'])
            self.logger.error('fengine bitstream: %s' % self.configd['fengine']['bitstream'])
            self.logger.error('One or more bitstream files not found.')
            raise IOError('One or more bitstream files not found.')

        # TODO: Load config values from the bitstream meta information - f per fpga, x per fpga, etc
        self.arp_wait_time = int(self.configd['FxCorrelator']['arp_wait_time'])
        self.sensor_poll_time = int(self.configd['FxCorrelator']['sensor_poll_time'])
        self.katcp_port = int(self.configd['FxCorrelator']['katcp_port'])
        self.f_per_fpga = int(self.configd['fengine']['f_per_fpga'])
        self.x_per_fpga = int(self.configd['xengine']['x_per_fpga'])
        self.sample_rate_hz = int(self.configd['FxCorrelator']['sample_rate_hz'])
        self.accumulation_len = int(self.configd['xengine']['accumulation_len'])
        self.xeng_accumulation_len = int(self.configd['xengine']['xeng_accumulation_len'])
        self.n_chans = int(self.configd['fengine']['n_chans'])
        self.n_antennas = int(self.configd['fengine']['n_antennas'])

        self.set_stream_destination(self.configd['xengine']['output_destination_ip'],
                                    int(self.configd['xengine']['output_destination_port']))
        self.set_meta_destination(self.configd['xengine']['output_destination_ip'],
                                  int(self.configd['xengine']['output_destination_port']))

        # get this from the running x-engines?
        self.xeng_clk = int(self.configd['xengine']['x_fpga_clock'])
        self.xeng_outbits = int(self.configd['xengine']['xeng_outbits'])

        # the f-engines have this many 10Gbe ports per f-engine unit of operation
        self.ports_per_fengine = int(self.configd['fengine']['ports_per_fengine'])

        # set up the hosts and engines based on the configuration in the ini file
        self.fhosts = []
        for host in self.configd['fengine']['hosts'].split(','):
            host = host.strip()
            fpgahost = fhost_fpga.FpgaFHost.from_config_source(host, self.katcp_port,
                                                               config_source=self.configd['fengine'])
            self.fhosts.append(fpgahost)
        self.xhosts = []
        for host in self.configd['xengine']['hosts'].split(','):
            host = host.strip()
            fpgahost = xhost_fpga.FpgaXHost.from_config_source(host, self.katcp_port,
                                                               config_source=self.configd['xengine'])
            self.xhosts.append(fpgahost)

        # check that no hosts overlap
        for _fh in self.fhosts:
            for _xh in self.xhosts:
                if _fh.host == _xh.host:
                    self.logger.error('Host %s is assigned to both X- and F-engines' % _fh.host)
                    raise RuntimeError

        # what data sources have we been allocated?
        self._handle_sources()

        # turn the product names into a list
        prodlist = self.configd['xengine']['output_products'].replace('[', '').replace(']', '').split(',')
        self.configd['xengine']['output_products'] = []
        for prod in prodlist:
            self.configd['xengine']['output_products'].append(prod.strip(''))

    def _handle_sources(self):
        """
        Sort out sources and eqs for them
        :return:
        """
        assert len(self.fhosts) > 0

        source_names = self.configd['fengine']['source_names'].strip().split(',')
        source_mcast = self.configd['fengine']['source_mcast_ips'].strip().split(',')
        assert len(source_mcast) == len(source_names), (
            'Source names (%d) must be paired with multicast source '
            'addresses (%d)' % (len(source_names), len(source_mcast)))

        # match eq polys to source names
        eq_polys = {}
        for src_name in source_names:
            eq_polys[src_name] = utils.process_new_eq(self.configd['fengine']['eq_poly_%s' % src_name])

        # assemble the sources given into a list
        self.fengine_sources = []
        source_ctr = 0
        for counter, address in enumerate(source_mcast):
            new_source = DataSource.from_mcast_string(address)
            new_source.name = source_names[counter]
            # adding a new instance attribute here, be careful
            new_source.source_number = source_ctr
            assert new_source.ip_range == self.ports_per_fengine, (
                'F-engines should be receiving from %d streams.' % self.ports_per_fengine)
            self.fengine_sources.append(new_source)
            source_ctr += 1

        # assign sources and eqs to fhosts
        self.logger.info('Assigning DataSources and EQs to f-engines...')
        source_ctr = 0
        for fhost in self.fhosts:
            self.logger.info('\t%s:' % fhost.host)
            _eq_dict = {}
            for fengnum in range(0, self.f_per_fpga):
                _source = self.fengine_sources[source_ctr]
                _eq_dict[_source.name] = {'eq': eq_polys[_source.name], 'bram_num': fengnum}
                assert _source.ip_range == self.fengine_sources[0].ip_range, (
                    'All f-engines should be receiving from %d streams.' % self.ports_per_fengine)
                # adding a new instance attribute here, be careful
                _source.host = fhost
                fhost.add_source(_source)
                self.logger.info('\t\t%s' % _source)
                source_ctr += 1
            fhost.eqs = _eq_dict
        if source_ctr != len(self.fhosts) * self.f_per_fpga:
            raise RuntimeError('We have different numbers of sources (%d) and '
                               'f-engines (%d). Problem.', source_ctr,
                               len(self.fhosts) * self.f_per_fpga)
        self.logger.info('done.')

    def _read_config_file(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if we read the file successfully, False if not
        """
        self.configd = utils.parse_ini_file(self.config_source)

    def _read_config_server(self):
        """
        Get instance-specific setup information from a given server. Via KATCP?
        :return:
        """
        raise NotImplementedError('_read_config_server not implemented')

    def set_stream_destination(self, txip_str=None, txport=None):
        """
        Set destination for output of fxcorrelator.
        :param txip_str: A dotted-decimal string representation of the IP address. e.g. '1.2.3.4'
        :param txport: An integer port number.
        :return: <nothing>
        """
        if txip_str is None:
            txip = tengbe.IpAddress.str2ip(self.xeng_tx_destination[0])
        else:
            txip = tengbe.IpAddress.str2ip(txip_str)
        if txport is None:
            txport = self.xeng_tx_destination[1]
        else:
            txport = int(txport)
        self.logger.info('Setting stream destination to %s:%d' %
                         (tengbe.IpAddress.ip2str(txip), txport))
        try:
            THREADED_FPGA_OP(self.xhosts, timeout=10,
                             target_function=(lambda fpga_:
                                              fpga_.registers.gbe_iptx.write(reg=txip),))
            THREADED_FPGA_OP(self.xhosts, timeout=10,
                             target_function=(lambda fpga_:
                                              fpga_.registers.gbe_porttx.write(reg=txport),))
        except AttributeError:
            self.logger.warning('Set SPEAD stream destination called, but '
                                'devices NOT written! Have they been created?')
        self.xeng_tx_destination = (tengbe.IpAddress.ip2str(txip), txport)

    def set_meta_destination(self, txip_str=None, txport=None):
        """
        Set destination for meta info output of fxcorrelator.
        :param txip_str: A dotted-decimal string representation of the IP address. e.g. '1.2.3.4'
        :param txport: An integer port number.
        :return: <nothing>
        """
        if txip_str is None:
            txip_str = self.meta_destination[0]
        if txport is None:
            txport = self.meta_destination[1]
        else:
            txport = int(txport)
        if txport is None or txip_str is None:
            self.logger.error('Cannot set part of meta destination to None - %s:%d' %
                              (txip_str, txport))
            raise RuntimeError('Cannot set part of meta destination to None - %s:%d' %
                               (txip_str, txport))
        self.meta_destination = (txip_str, txport)
        self.logger.info('Setting meta destination to %s:%d' % (txip_str, txport))

    def tx_start(self, issue_spead=True):
        """
        Turns on xengine output pipes needed to start data flow from xengines
        """
        self.logger.info('Starting transmission')
        if issue_spead:
            self.spead_issue_meta()
        # start tx on the x-engines
        for f in self.xhosts:
            f.registers.control.write(gbe_txen=True)

    def tx_stop(self, stop_f=False):
        """
        Turns off output pipes to start data flow from xengines
        :param stop_f: stop output of fengines as well
        """
        self.logger.info('Stopping X transmission')

        THREADED_FPGA_OP(self.xhosts, timeout=10,
                         target_function=(
                             lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))
        if stop_f:
            self.logger.info('Stopping F transmission')
            THREADED_FPGA_OP(self.fhosts, timeout=10,
                             target_function=(
                                 lambda fpga_: fpga_.registers.control.write(comms_en=False),))

    def spead_issue_meta(self):
        """
        All FxCorrelators issued SPEAD in the same way, with tweakings that are implemented by the child class.
        :return: <nothing>
        """
        if self.meta_destination is None:
            logging.info('SPEAD meta destination is still unset, NOT sending metadata at this time.')
            return
        # make a new SPEAD transmitter
        del self.spead_tx, self.spead_meta_ig
        self.spead_tx = spead.Transmitter(spead.TransportUDPtx(*self.meta_destination))
        # update the multicast socket option to use a TTL of 2, 
        # in order to traverse the L3 network on site.
        ttl_bin = struct.pack('@i', 2)
        self.spead_tx.t._udp_out.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl_bin)
        #mcast_interface = self.configd['xengine']['multicast_interface_address']
        #self.spead_tx.t._udp_out.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF,
        #                                    socket.inet_aton(mcast_interface))
        # self.spead_tx.t._udp_out.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP,
        #                                     socket.inet_aton(txip_str) + socket.inet_aton(mcast_interface))
        # make the item group we're going to use
        self.spead_meta_ig = spead.ItemGroup()

        self.spead_meta_ig.add_item(name='adc_sample_rate', id=0x1007,
                                    description='The expected ADC sample rate (samples '
                                                'per second) of incoming data.',
                                    shape=[], fmt=spead.mkfmt(('u', 64)),
                                    init_val=self.sample_rate_hz)

        self.spead_meta_ig.add_item(name='n_bls', id=0x1008,
                                    description='Number of baselines in the data product.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=len(xengops.xeng_get_baseline_order(self)))

        self.spead_meta_ig.add_item(name='n_chans', id=0x1009,
                                    description='Number of frequency channels in '
                                                'an integration.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.n_chans)

        self.spead_meta_ig.add_item(name='n_ants', id=0x100A,
                                    description='The number of antennas in the system.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.n_antennas)

        self.spead_meta_ig.add_item(name='n_xengs', id=0x100B,
                                    description='The number of x-engines in the system.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=(len(self.xhosts) * self.x_per_fpga))

        self.spead_meta_ig.add_item(name='bls_ordering', id=0x100C,
                                    description='The baseline ordering in the output '
                                                'data product.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=numpy.array(
                                        [baseline for baseline in xengops.xeng_get_baseline_order(self)]))

        # spead_ig.add_item(name='crosspol_ordering', id=0x100D,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        metalist = []
        for ctr, source in enumerate(self.fengine_sources):
            metalist.append((source.name, ctr))
        self.spead_meta_ig.add_item(name='input_labelling', id=0x100E,
                                    description='input labels and numbers',
                                    init_val=numpy.array(metalist))

        # spead_ig.add_item(name='n_bengs', id=0x100F,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        self.spead_meta_ig.add_item(name='center_freq', id=0x1011,
                                    description='The on-sky centre-frequency.',
                                    shape=[], fmt=spead.mkfmt(('f', 64)),
                                    init_val=int(self.configd['fengine']['true_cf']))

        self.spead_meta_ig.add_item(name='bandwidth', id=0x1013,
                                    description='The input (analogue) bandwidth of '
                                                'the system.',
                                    shape=[], fmt=spead.mkfmt(('f', 64)),
                                    init_val=int(self.configd['fengine']['bandwidth']))

        self.spead_meta_ig.add_item(name='n_accs', id=0x1015,
                                    description='The number of spectra that are '
                                                'accumulated per X-engine dump.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.accumulation_len * self.xeng_accumulation_len)

        self.spead_meta_ig.add_item(name='int_time', id=0x1016,
                                    description='The time per integration, in seconds.',
                                    shape=[], fmt=spead.mkfmt(('f', 64)),
                                    init_val=xengops.xeng_get_acc_time(self))

        # spead_ig.add_item(name='coarse_chans', id=0x1017,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)
        #
        # spead_ig.add_item(name='current_coarse_chan', id=0x1018,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)
        #
        # spead_ig.add_item(name='fft_shift_fine', id=0x101C,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)
        #
        # spead_ig.add_item(name='fft_shift_coarse', id=0x101D,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        self.spead_meta_ig.add_item(name='fft_shift', id=0x101E,
                                    description='The FFT bitshift pattern. F-engine correlator internals.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=int(self.configd['fengine']['fft_shift']))

        self.spead_meta_ig.add_item(name='xeng_acc_len', id=0x101F,
                                    description='Number of spectra accumulated inside X engine. '
                                                'Determines minimum integration time and '
                                                'user-configurable integration time stepsize. '
                                                'X-engine correlator internals.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.xeng_accumulation_len)

        quant_bits = int(self.configd['fengine']['quant_format'].split('.')[0])
        self.spead_meta_ig.add_item(name='requant_bits', id=0x1020,
                                    description='Number of bits after requantisation in the '
                                                'F engines (post FFT and any '
                                                'phasing stages).',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=quant_bits)

        pkt_len = int(self.configd['fengine']['10gbe_pkt_len'])
        self.spead_meta_ig.add_item(name='feng_pkt_len', id=0x1021,
                                    description='Payload size of 10GbE packet exchange between '
                                                'F and X engines in 64 bit words. Usually equal '
                                                'to the number of spectra accumulated inside X '
                                                'engine. F-engine correlator internals.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=pkt_len)

        # port = int(self.configd['xengine']['output_destination_port'])
        # spead_ig.add_item(name='rx_udp_port', id=0x1022,
        #                   description='Destination UDP port for X engine output.',
        #                   shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                   init_val=port)

        port = int(self.configd['fengine']['10gbe_port'])
        self.spead_meta_ig.add_item(name='feng_udp_port', id=0x1023,
                                    description='Port for F-engines 10Gbe links in the system.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=port)

        # ip = self.configd['xengine']['output_destination_ip']
        # spead_ig.add_item(name='rx_udp_ip_str', id=0x1024,
        #                   description='Destination UDP IP for X engine output.',
        #                   shape=[-1], fmt=spead.STR_FMT,
        #                   init_val=ip)

        ip = struct.unpack('>I', socket.inet_aton(self.configd['fengine']['10gbe_start_ip']))[0]
        self.spead_meta_ig.add_item(name='feng_start_ip', id=0x1025,
                                    description='Start IP address for F-engines in the system.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=ip)

        self.spead_meta_ig.add_item(name='xeng_rate', id=0x1026,
                                    description='Target clock rate of processing engines (xeng).',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.xeng_clk)

        self.spead_meta_ig.add_item(name='sync_time', id=0x1027,
                                    description='The time at which the digitisers were synchronised. '
                                                'Seconds since the Unix Epoch.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.synchronisation_epoch)

        # spead_ig.add_item(name='n_stokes', id=0x1040,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        x_per_fpga = int(self.configd['xengine']['x_per_fpga'])
        self.spead_meta_ig.add_item(name='x_per_fpga', id=0x1041,
                                    description='Number of X engines per FPGA host.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=x_per_fpga)

        # n_ants_per_xaui = 1
        # spead_ig.add_item(name='n_ants_per_xaui', id=0x1042,
        #                   description='',
        #                   shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                   init_val=n_ants_per_xaui)

        # spead_ig.add_item(name='ddc_mix_freq', id=0x1043,
        #                        description='',
        #                        shape=[],fmt=spead.mkfmt(('f', 64)),
        #                        init_val=)

        # spead_ig.add_item(name='ddc_bandwidth', id=0x1044,
        #                        description='',
        #                        shape=[],fmt=spead.mkfmt(('f', 64)),
        #                        init_val=)

        sample_bits = int(self.configd['fengine']['sample_bits'])
        self.spead_meta_ig.add_item(name='adc_bits', id=0x1045,
                                    description='How many bits per ADC sample.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=sample_bits)

        self.spead_meta_ig.add_item(name='scale_factor_timestamp', id=0x1046,
                                    description='Timestamp scaling factor. Divide the SPEAD '
                                                'data packet timestamp by this number to get '
                                                'back to seconds since last sync.',
                                    shape=[], fmt=spead.mkfmt(('f', 64)),
                                    init_val=self.sample_rate_hz)

        # spead_ig.add_item(name='b_per_fpga', id=0x1047,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        self.spead_meta_ig.add_item(name='xeng_out_bits_per_sample', id=0x1048,
                                    description='The number of bits per value of the xeng '
                                                'accumulator output. Note this is for a '
                                                'single value, not the combined complex size.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.xeng_outbits)

        self.spead_meta_ig.add_item(name='f_per_fpga', id=0x1049,
                                    description='Number of F engines per FPGA host.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.f_per_fpga)

        # spead_ig.add_item(name='beng_out_bits_per_sample', id=0x1050,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='rf_gain_MyAntStr ', id=0x1200+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('f', 64)),
        #                        init_val=)

        # 0x1400 +++
        fengops.feng_eq_update_metadata()

        # spead_ig.add_item(name='eq_coef_MyAntStr', id=0x1400+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', 32)),
        #                        init_val=)

        # ndarray = numpy.dtype(numpy.int64), (4096 * 40 * 1, 1, 1)

        self.spead_meta_ig.add_item(name='timestamp', id=0x1600,
                                    description='Timestamp of start of this integration. uint counting multiples '
                                                'of ADC samples since last sync (sync_time, id=0x1027). Divide this '
                                                'number by timestamp_scale (id=0x1046) to get back to seconds since '
                                                'last sync when this integration was actually started.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)))
        
        self.spead_meta_ig.add_item(name='flags_xeng_raw', id=0x1601,
                                    description='Flags associated with xeng_raw data output.'
                                                'bit 34 - corruption or data missing during integration '
                                                'bit 33 - overrange in data path '
                                                'bit 32 - noise diode on during integration '
                                                'bits 0 - 31 reserved for internal debugging',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)))

        ndarray = numpy.dtype(numpy.int32), (self.n_chans, len(self.xeng_get_baseline_order()), 2)
        self.spead_meta_ig.add_item(name='xeng_raw', id=0x1800,
                                    description='Raw data for %i xengines in the system. This item represents a '
                                                'full spectrum (all frequency channels) assembled from lowest '
                                                'frequency to highest frequency. Each frequency channel contains '
                                                'the data for all baselines (n_bls given by SPEAD ID 0x100b). '
                                                'Each value is a complex number -- two (real and imaginary) '
                                                'unsigned integers.' % len(self.xhosts * self.x_per_fpga),
                                    ndarray=ndarray)

        # TODO hard-coded !!!!!!! :(
#        self.spead_ig.add_item(name=("xeng_raw"),id=0x1800,
#                               description="Raw data for %i xengines in the system. This
# item represents a full spectrum (all frequency channels) assembled from lowest frequency
# to highest frequency. Each frequency channel contains the data for all baselines
# (n_bls given by SPEAD ID 0x100B). Each value is a complex number -- two
# (real and imaginary) unsigned integers."%(32),
#                               ndarray=(numpy.dtype(numpy.int32),(4096,((4*(4+1))/2)*4,2)))

        # spead_ig.add_item(name='beamweight_MyAntStr', id=0x2000+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', 32)),
        #                        init_val=)

        # spead_ig.add_item(name='incoherent_sum', id=0x3000,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', 32)),
        #                        init_val=)

        # spead_ig.add_item(name='n_inputs', id=0x3100,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='digitiser_id', id=0x3101,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='digitiser_status', id=0x3102,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='pld_len', id=0x3103,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='raw_data_MyAntStr', id=0x3300+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='Reserved for SP-CAM meta-data', id=0x7000-0x7fff,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='feng_id', id=0xf101,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='feng_status', id=0xf102,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='frequency', id=0xf103,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='raw_freq_MyAntStr', id=0xf300+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='bf_MyBeamName', id=0xb000+beamN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        self.spead_tx.send_heap(self.spead_meta_ig.get_heap())
        self.logger.info('Issued SPEAD data descriptor to %s:%i.' % (self.meta_destination[0],
                                                                     self.meta_destination[1]))
# end
