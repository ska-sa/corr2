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

import log
import utils
import xhost_fpga
import fhost_fpga
from instrument import Instrument
from data_source import DataSource, FengineSource
from casperfpga import tengbe
from casperfpga import utils as fpgautils

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

        # parent constructor
        Instrument.__init__(self, descriptor, identifier, config_source)

    def initialise(self, program=True, tvg=False, fake_digitiser=False):
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

        # connect to the hosts that make up this correlator
        THREADED_FPGA_FUNC(self.fhosts, 5, 'connect')
        THREADED_FPGA_FUNC(self.xhosts, 5, 'connect')

        # if we need to program the FPGAs, do so
        if program:
            self.logger.info('Programming FPGA hosts')
            ftups = []
            for f in self.xhosts:
                ftups.append((f, f.boffile))
            for f in self.fhosts:
                ftups.append((f, f.boffile))
            fpgautils.program_fpgas(ftups, None, 15)
            # this does not wait for the programming to complete, so it won't get all the system information

        # load information from the running boffiles
        self.logger.info('Loading design information')
        THREADED_FPGA_FUNC(self.fhosts, 10, 'get_system_information')
        THREADED_FPGA_FUNC(self.xhosts, 10, 'get_system_information')

        if program:
            # cal the qdr on all boards
            self.qdr_calibrate()

            # init the f engines
            self._fengine_initialise()

            # init the x engines
            self._xengine_initialise(tvg=tvg)

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
            sys.stdout.flush()

            # subscribe the f-engines to the multicast groups
            self._fengine_subscribe_to_multicast()

        if program and True:
            # reset all counters on fhosts and xhosts
            self.feng_clear_status_all()
            self.xeng_clear_status_all()

            # check to see if the f engines are receiving all their data
            self._feng_check_rx()

            # start f-engine TX
            self.logger.info('Starting f-engine datastream')
            for f in self.fhosts:
                f.registers.control.write(gbe_txen=True)

            # subscribe the x-engines to this data also
            self._xengine_subscribe_to_multicast()

            # check that they are receiving data
            self._xeng_check_rx()

            # arm the vaccs on the x-engines
            self.xeng_vacc_sync()

        # reset all counters on fhosts and xhosts
        self.feng_clear_status_all()
        self.xeng_clear_status_all()

    # def qdr_calibrate_SERIAL(self):
    #     for hostlist in [self.fhosts, self.xhosts]:
    #         for host in hostlist:
    #             print host.host
    #             for qdr in host.qdrs:
    #                 qdr.qdr_cal(fail_hard=False, verbosity=2)

    def qdr_calibrate(self):
        # cal the QDR specifically
        def _qdr_cal(fpga):
            results = {}
            for qdr in fpga.qdrs:
                results[qdr.name] = qdr.qdr_cal(fail_hard=False)
            return results
        self.logger.info('Calibrating QDR on F- and X-engines, this takes a while.')
        results = fpgautils.threaded_fpga_operation(self.fhosts, 30, _qdr_cal)
        for fpga, result in results.items():
            self.logger.info('FPGA %s QDR cal results:' % fpga)
            for qdr, qdrres in result.items():
                self.logger.info('\t%s: cal okay: %s' % (qdr, 'True' if qdrres else 'False'))
        results = fpgautils.threaded_fpga_operation(self.xhosts, 30, _qdr_cal)
        for fpga, result in results.items():
            self.logger.info('FPGA %s QDR cal results:' % fpga)
            for qdr, qdrres in result.items():
                self.logger.info('\t%s: cal okay: %s' % (qdr, 'True' if qdrres else 'False'))
        # for host in self.fhosts:
        #     for qdr in host.qdrs:
        #         qdr.qdr_delay_in_step(0b111111111111111111111111111111111111, -1)
        #
        # for host in self.xhosts:
        #     for qdr in host.qdrs:
        #         qdr.qdr_delay_in_step(0b111111111111111111111111111111111111, -1)

    def _feng_check_rx(self, max_waittime=30):
        """
        Check that the f-engines are receiving data correctly
        :param max_waittime:
        :return:
        """
        self.logger.info('Checking F hosts are receiving data...')
        THREADED_FPGA_FUNC(self.fhosts, max_waittime+1, 'check_rx', max_waittime)
        self.logger.info('\tdone.')

    def feng_get_eq_all(self):
        """
        Return the EQ arrays in a dictionary, arranged by FPGA hostname and source name.
        :return:
        """
        eq_table = {}
        for fhost in self.fhosts:
            eq_table[fhost.host] = fhost.get_source_eq_all()
        return eq_table

    def feng_get_eq_list(self):
        """
        Return the EQ arrays in a list, ordered by source number
        :return:
        """
        eq_list = []
        for source in self.fengine_sources:
            eq_list.append(source.get_eq())
        return eq_list

    def feng_set_eq_all(self, complex_gain_list=None):
        """
        Set the EQ gain for all sources.
        :param complex_gain_list:
        :return:
        """
        self.logger.info('Setting EQ on fengines...')
        THREADED_FPGA_FUNC(self.fhosts, 10, 'set_source_eq_all', complex_gain_list)
        if self.spead_meta_ig is not None:
            for source_ctr, eqs in enumerate(self.feng_get_eq_list()):
                try:
                    eqlen = len(eqs)
                except TypeError:
                    eqs = [eqs]
                    eqlen = 1
                self.spead_meta_ig.add_item(name='eq_coef_%s' % self.fengine_sources[source_ctr].name,
                                            id=0x1400 + source_ctr,
                                            description='The unitless per-channel digital scaling factors implemented '
                                                        'prior to requantisation, post-FFT, for input %s. '
                                                        'Complex number real,imag 32 bit integers.' %
                                                        self.fengine_sources[source_ctr].name,
                                            shape=[eqlen, 2],
                                            fmt=spead.mkfmt(('u',32)),
                                            init_val=[[numpy.real(eq_coeff), numpy.imag(eq_coeff)] for eq_coeff in eqs])
            self.spead_tx.send_heap(self.spead_meta_ig.get_heap())
        self.logger.info('done.')

    def feng_set_fft_shift_all(self, shift_value=None):
        """
        Set the FFT shift on all boards.
        :param shift_value:
        :return:
        """
        if shift_value is None:
            shift_value = int(self.configd['fengine']['fft_shift'])
        if shift_value < 0:
            raise RuntimeError('Shift value cannot be less than zero')
        self.logger.info('Setting FFT shift to %i on all f-engine boards...' % shift_value)
        THREADED_FPGA_FUNC(self.fhosts, 10, 'set_fft_shift', shift_value)
        self.logger.info('done.')
        if self.spead_meta_ig is not None:
            self.spead_meta_ig['fft_shift'] = int(self.configd['fengine']['fft_shift'])
            self.spead_tx.send_heap(self.spead_meta_ig.get_heap())
        return shift_value

    def feng_get_fft_shift_all(self):
        """
        Get the FFT shift value on all boards.
        :return:
        """
        # get the fft shift values
        return THREADED_FPGA_FUNC(self.fhosts, 10, 'get_fft_shift')

    def feng_clear_status_all(self):
        """
        Clear the various status registers and counters on all the fengines
        :return:
        """
        THREADED_FPGA_FUNC(self.fhosts, 10, 'clear_status')

    def _fengine_initialise(self):
        """
        Set up f-engines on this device.
        :return:
        """
        # set eq and shift
        self.feng_set_eq_all()
        self.feng_set_fft_shift_all()

        # set up the fpga comms
        THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_txen=False))
        THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_rst=False))
        self.feng_clear_status_all()

        # where does the f-engine data go?
        self.fengine_output = DataSource.from_mcast_string(self.configd['fengine']['destination_mcast_ips'])
        self.fengine_output.name='fengine_destination'
        fdest_ip = tengbe.str2ip(self.fengine_output.ip)
        THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.iptx_base.write_int(fdest_ip))

        # set up the cores
        feng_ip_octets = [int(bit) for bit in self.configd['fengine']['10gbe_start_ip'].split('.')]
        feng_port = int(self.configd['fengine']['10gbe_port'])
        assert len(feng_ip_octets) == 4, 'That\'s an odd IP address.'
        feng_ip_base = feng_ip_octets[3]
        feng_ip_prefix = '%d.%d.%d.' % (feng_ip_octets[0], feng_ip_octets[1], feng_ip_octets[2])
        macprefix = self.configd['fengine']['10gbe_macprefix']
        macbase = int(self.configd['fengine']['10gbe_macbase'])
        board_id = 0
        for ctr, f in enumerate(self.fhosts):
            for gbe in f.tengbes:
                this_mac = '%s%02x' % (macprefix, macbase)
                this_ip = '%s%d' % (feng_ip_prefix, feng_ip_base)
                gbe.setup(mac=this_mac, ipaddress=this_ip,
                          port=feng_port)
                self.logger.info('fhost(%s) gbe(%s) MAC(%s) IP(%s) port(%i) board(%i) txIP(%s) txPort(%i)' %
                                 (f.host, gbe.name, this_mac, this_ip, feng_port, board_id,
                                 self.fengine_output.ip, self.fengine_output.port))
                macbase += 1
                feng_ip_base += 1
            f.registers.tx_metadata.write(board_id=board_id, porttx=self.fengine_output.port)
            board_id += 1

        # start tap on the f-engines
        for ctr, f in enumerate(self.fhosts):
            for gbe in f.tengbes:
                gbe.tap_start(True)

        # release from reset
        THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_rst=False))

    def _fengine_subscribe_to_multicast(self):
        """
        Subscribe all f-engine data sources to their multicast data
        :return:
        """
        self.logger.info('Subscribing f-engine datasources...')
        for fhost in self.fhosts:
            self.logger.info('\t%s:' % fhost.host)
            gbe_ctr = 0
            for source in fhost.data_sources:
                rxaddr = source.ip
                rxaddr_bits = rxaddr.split('.')
                rxaddr_base = int(rxaddr_bits[3])
                rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0], rxaddr_bits[1], rxaddr_bits[2])
                if (len(fhost.tengbes) / self.f_per_fpga) != source.iprange:
                    raise RuntimeError(
                        '10Gbe ports (%d) do not match sources IPs (%d)' % (len(fhost.tengbes), source.iprange))
                for ctr in range(0, source.iprange):
                    gbename = fhost.tengbes.names()[gbe_ctr]
                    gbe = fhost.tengbes[gbename]
                    rxaddress = '%s%d' % (rxaddr_prefix, rxaddr_base + ctr)
                    self.logger.info('\t\t%s subscribing to address %s' % (gbe.name, rxaddress))
                    gbe.multicast_receive(rxaddress, 0)
                    gbe_ctr += 1
        self.logger.info('one.')

    """
    X-engine functionality
    """

    def _xengine_initialise(self, tvg=False):
        """
        Set up x-engines on this device.
        :return:
        """
        # simulator
        if use_xeng_sim:
            THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.simulator.write(en=False, rst='pulse'))

        # disable transmission, place cores in reset, and give control register a known state
        THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_txen=False))
        self.xeng_clear_status_all()

        # set up accumulation length
        self.xeng_set_acc_len()

        # set up default destination ip and port
        self.set_stream_destination()
        self.set_meta_destination()

        # set up 10gbe cores
        xeng_ip_octets = [int(bit) for bit in self.configd['xengine']['10gbe_start_ip'].split('.')]
        assert len(xeng_ip_octets) == 4, 'That\'s an odd IP address.'
        xeng_ip_base = xeng_ip_octets[3]
        xeng_ip_prefix = '%d.%d.%d.' % (xeng_ip_octets[0], xeng_ip_octets[1], xeng_ip_octets[2])
        xeng_port = int(self.configd['xengine']['10gbe_port'])
        macprefix = self.configd['xengine']['10gbe_macprefix']
        macbase = int(self.configd['xengine']['10gbe_macbase'])
        board_id = 0
        for f in self.xhosts:
            f.registers.board_id.write(reg=board_id)
            for gbe in f.tengbes:
                this_mac = '%s%02x' % (macprefix, macbase)
                this_ip = '%s%d' % (xeng_ip_prefix, xeng_ip_base)
                gbe.setup(mac='%s%02x' % (macprefix, macbase), ipaddress='%s%d' % (xeng_ip_prefix, xeng_ip_base),
                          port=xeng_port)
                self.logger.info('xhost(%s) gbe(%s) MAC(%s) IP(%s) port(%i) board(%i)' %
                                 (f.host, gbe, this_mac, this_ip, xeng_port, board_id))
                macbase += 1
                xeng_ip_base += 1
                gbe.tap_start()
            board_id += 1  # 1 on new systems, 4 on old xeng_rx_reorder system

        # clear gbe status
        THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_debug_rst='pulse'))

        # release cores from reset
        THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_rst=False))

        # simulator
        if use_xeng_sim:
            THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.simulator.write(en=True))

        # clear general status
        THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.control.write(status_clr='pulse'))

        # check for errors
        """
        for f in self.xhosts:
            for eng_index in range(4):
                xeng = f.get_engine(eng_index)
                status = xeng.host.registers['status%d' % eng_index].read()['data']

                # check that all engines are receiving data
                if (status['rxing_data'] == False):
                    print 'xengine %d on host %s is not receiving valid data' %(eng_index, str(f))

                # TODO check that there are no other errors
                
                # check that all engines are producing data ready for transmission
                if (status['txing_data'] == False):
                    print 'xengine %d on host %s is not producing valid data' %(eng_index, str(f))
        """

        # start accumulating
        # for f in self.xhosts:
        #     f.registers.vacc_time_msw.write(arm=0, immediate=0)
        #     f.registers.vacc_time_msw.write(arm=1, immediate=1)

        if use_xeng_sim:
            self.synchronisation_epoch = time.time()

        '''
        # read accumulation count before starting accumulations
        vacc_cnts = []
        for f in self.xhosts:
            for eng_index in range(4):
                vacc_cnt = f.registers['vacc_cnt%d' %eng_index].read()['data']['reg']
                vacc_cnts.append(vacc_cnt)

        print 'waiting for an accumulation' 
        time.sleep(1.5)
        '''

        # check accumulations are happening
        '''
        vacc_cnts.reverse()
        for f in self.xhosts:
            for eng_index in range(4):
                vacc_cnt = f.registers['vacc_cnt%d' %eng_index].read()['data']['reg']
                vacc_cnt_before = vacc_cnts.pop()                

                if vacc_cnt_before == vacc_cnt:
                    print 'no accumulations happening for %s:xeng %d' %(str(f), eng_index)
        '''

    def xeng_clear_status_all(self):
        """
        Clear the various status registers and counters on all the fengines
        :return:
        """
        THREADED_FPGA_FUNC(self.xhosts, 10, 'clear_status')

    def _xengine_subscribe_to_multicast(self):
        """
        Subscribe the x-engines to the f-engine output multicast groups - each one subscribes to
        only one group, with data meant only for it.
        :return:
        """
        source_address = self.fengine_output.ip
        source_bits = source_address.split('.')
        source_base = int(source_bits[3])
        source_prefix = '%s.%s.%s.' % (source_bits[0], source_bits[1], source_bits[2])
        source_ctr = 0
        for host_ctr, host in enumerate(self.xhosts):
            for gbe in host.tengbes:
                rxaddress = '%s%d' % (source_prefix, source_base + source_ctr)
                gbe.multicast_receive(rxaddress, 0)
                source_ctr += 1
                self.logger.debug('xhost %s %s subscribing to address %s' % (host.host, gbe.name, rxaddress))
                self.logger.info('xhost %s %s subscribing to address %s' % (host.host, gbe.name, rxaddress))

    def _xeng_check_rx(self, max_waittime=30):
        """
        Check that the x hosts are receiving data correctly
        :param waittime:
        :return:
        """
        self.logger.info('Checking X hosts are receiving data...')
        THREADED_FPGA_FUNC(self.xhosts, max_waittime+1, 'check_rx', max_waittime)
        self.logger.info('\tdone.')

    def xeng_vacc_sync(self, vacc_load_time=5):
        """
        Sync the vector accumulators on all the x-engines.
        Assumes that the x-engines are all receiving data.
        :return:
        """
        self.logger.info('X-engine VACC sync:')

        # check if the vaccs need resetting
        vaccstat = THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_check_arm_load_counts')
        reset_required = False
        for xhost, result in vaccstat.items():
            if result:
                self.logger.info('%s has a vacc that needs resetting' % xhost)
                reset_required = True

        if reset_required:
            THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_reset')
            vaccstat = THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_check_reset_status')
            for xhost, result in vaccstat.items():
                if not result:
                    self.logger.error('Resetting vaccs on %s failed.' % xhost)
                    raise RuntimeError

        # get current time from f-engines
        current_ftime = self.fhosts[0].get_local_time()
        assert current_ftime & 0xfff == 0, 'Bottom 12 bits of timestamp from f-engine are not zero?!'
        self.logger.info('\tCurrent f engine time: %i' % current_ftime)

        # use that time to set the vacc load time on the xengines
        ldtime = current_ftime + (vacc_load_time * self.sample_rate_hz)
        self.logger.info('\tApplying load time: %i' % ldtime)
        THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_set_loadtime', ldtime)

        # read the current arm and load counts
        def print_vacc_statuses(vstatus):
            self.logger.info('VACC statii:')
            for host in self.xhosts:
                self.logger.info('\t%s:' % host.host)
                for ctr, status in enumerate(vstatus[host.host]):
                    self.logger.info('\t\t%i: %s' % (ctr, status))
        vacc_status = THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_get_status')
        for host in self.xhosts:
            for status in vacc_status[host.host]:
                if (status['loadcount'] != vacc_status[self.xhosts[0].host][0]['loadcount']) or \
                   (status['armcount'] != vacc_status[self.xhosts[0].host][0]['armcount']):
                    self.logger.error('All hosts do not have matching arm and load counts.')
                    print_vacc_statuses(vacc_status)
                    raise RuntimeError
        arm_count = vacc_status[self.xhosts[0].host][0]['armcount']
        load_count = vacc_status[self.xhosts[0].host][0]['loadcount']
        self.logger.info('\tBefore arming: arm_count(%i) load_count(%i)' % (arm_count, load_count))

        # then arm them
        THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_arm')

        # did the arm count increase?
        vacc_status = THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_get_status')
        for host in self.xhosts:
            for status in vacc_status[host.host]:
                if (status['armcount'] != vacc_status[self.xhosts[0].host][0]['armcount']) or \
                   (status['armcount'] != arm_count + 1):
                    self.logger.error('All hosts do not have matching arm counts or arm count did not increase.')
                    print_vacc_statuses(vacc_status)
                    print arm_count
                    raise RuntimeError
        self.logger.info('\tAfter arming: arm_count(%i) load_count(%i)' % (arm_count+1, load_count))

        # check the the load time was stored correctly
        lsws = THREADED_FPGA_OP(self.xhosts, 10, lambda x: x.registers.vacc_time_lsw.read()['data'])
        msws = THREADED_FPGA_OP(self.xhosts, 10, lambda x: x.registers.vacc_time_msw.read()['data'])
        for host in self.xhosts:
            if (lsws[host.host]['lsw'] != lsws[self.xhosts[0].host]['lsw']) or \
               (msws[host.host]['msw'] != msws[self.xhosts[0].host]['msw']):
                self.logger.error('All hosts do not have matching VACC LSWs and MSWs')
                print lsws
                print msws
                vacc_status = THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_get_status')
                print_vacc_statuses(vacc_status)
                raise RuntimeError
        lsw = lsws[self.xhosts[0].host]['lsw']
        msw = msws[self.xhosts[0].host]['msw']
        xldtime = (msw << 32) | lsw
        self.logger.info('\tx engines have vacc ld time %i' % xldtime)

        # wait for the vaccs to arm
        time.sleep(vacc_load_time + 1)

        # check the status to see that the load count increased
        vacc_status = THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_get_status')
        for host in self.xhosts:
            for status in vacc_status[host.host]:
                if (status['loadcount'] != vacc_status[self.xhosts[0].host][0]['loadcount']) or \
                   (status['loadcount'] != load_count + 1):
                    self.logger.error('All hosts did not load the VACCs.')
                    print_vacc_statuses(vacc_status)
                    print load_count
                    raise RuntimeError
        self.logger.info('\tAfter trigger: arm_count(%i) load_count(%i)' % (arm_count+1, load_count+1))
        self.logger.info('\tAll VACCs triggered correctly. Checking for errors & accumulations...')

        THREADED_FPGA_FUNC(self.xhosts, 10, 'clear_status')
        time.sleep(self.xeng_get_acc_time()+1)
        vacc_status = THREADED_FPGA_FUNC(self.xhosts, 10, 'vacc_get_status')
        for host in self.xhosts:
            for status in vacc_status[host.host]:
                if status['errors'] > 0:
                    self.logger.error('\tVACC errors > 0. Que pasa?')
                if status['count'] <= 0:
                    self.logger.error('\tVACC counts <= 0. Que pasa?')
                    print_vacc_statuses(vacc_status)
                    raise RuntimeError
        self.logger.info('\t...accumulations rolling in without error.')

    def xeng_set_acc_time(self, acc_time_s):
        """
        Set the vacc accumulation length based on a required dump time, in seconds
        :param acc_time_s: new dump time, in seconds
        :return:
        """
        if use_xeng_sim:
            raise RuntimeError('That\'s not an option anymore.')
        else:
            new_acc_len = (self.sample_rate_hz * acc_time_s) / (self.xeng_accumulation_len * self.n_chans * 2.0)
            new_acc_len = round(new_acc_len)
            self.logger.info('New accumulation time %.2f becomes accumulation length %d' % (acc_time_s, new_acc_len))
            self.xeng_set_acc_len(new_acc_len)
        if self.spead_meta_ig is not None:
            self.spead_meta_ig['n_accs'] = self.accumulation_len * self.xeng_accumulation_len
            self.spead_meta_ig['int_time'] = self.xeng_get_acc_time()
            self.spead_tx.send_heap(self.spead_meta_ig.get_heap())

    def xeng_get_acc_time(self):
        """
        Get the dump time currently being used.
        :return:
        """
        return (self.xeng_accumulation_len * self.accumulation_len * self.n_chans * 2.0) / self.sample_rate_hz

    def xeng_set_acc_len(self, acc_len=None):
        """
        Set the QDR vector accumulation length.
        :param new_acc_len:
        :return:
        """
        if acc_len is not None:
            self.accumulation_len = acc_len
        THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.acc_len.write_int(self.accumulation_len))
        self.logger.info('Set accumulation length %d system-wide (%.2f seconds)' % (self.accumulation_len,
                                                                                    self.xeng_get_acc_time()))
        if self.spead_meta_ig is not None:
            self.spead_meta_ig['n_accs'] = self.accumulation_len * self.xeng_accumulation_len
            self.spead_meta_ig['int_time'] = self.xeng_get_acc_time()
            self.spead_tx.send_heap(self.spead_meta_ig.get_heap())


    #################################
    # Configuration information     #
    #################################

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
            source.name = newlist[ctr]
            metalist.append((source.name, ctr))
        if self.spead_meta_ig is not None:
            self.spead_meta_ig['input_labelling'] = numpy.array(metalist)
            self.spead_tx.send_heap(self.spead_meta_ig.get_heap())

    def get_labels(self):
        """
        Get the current fengine source labels.
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

        # what data sources have we been allocated?
        self._handle_sources()

        # turn the product names into a list
        self.configd['xengine']['output_products'] = self.configd['xengine']['output_products'].split(',')

    def _handle_sources(self):
        """
        Sort out sources and eqs for them
        :return:
        """
        assert len(self.fhosts) > 0

        source_names = self.configd['fengine']['source_names'].strip().split(',')
        source_mcast = self.configd['fengine']['source_mcast_ips'].strip().split(',')
        assert len(source_mcast) == len(source_names), \
            'Source names (%d) must be paired with multicast source addresses (%d)' % (len(source_names),
                                                                                       len(source_mcast))

        # assemble the sources given into a list
        self.fengine_sources = []
        source_ctr = 0
        for counter, address in enumerate(source_mcast):
            new_source = FengineSource.from_mcast_string(address)
            new_source.name = source_names[counter]
            new_source.source_number = source_ctr
            assert new_source.iprange == self.ports_per_fengine, \
                'F-engines should be receiving from %d streams.' % self.ports_per_fengine
            self.fengine_sources.append(new_source)
            source_ctr += 1

        # assign sources to fhosts
        self.logger.info('Assigning data sources to f-engines...')
        source_ctr = 0
        for fhost in self.fhosts:
            self.logger.info('\t%s:' % fhost.host)
            for fengnum in range(0, self.f_per_fpga):
                _source = self.fengine_sources[source_ctr]
                assert _source.iprange == self.fengine_sources[0].iprange, \
                    'All f-engines should be receiving from %d streams.' % self.ports_per_fengine
                _source.eq_poly = complex(int(self.configd['fengine']['eq_poly_%i' % source_ctr]))
                _source.host = fhost
                fhost.add_source(_source)
                self.logger.info('\t\t%s' % _source)
                source_ctr += 1
        if source_ctr != len(self.fhosts) * self.f_per_fpga:
            raise RuntimeError('We have different numbers of sources (%d) and f-engines (%d). Problem.',
                               source_ctr, len(self.fhosts) * self.f_per_fpga)
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
        raise NotImplementedError('Still have to do this')

    def set_stream_destination(self, txip_str=None, txport=None):
        """
        Set destination for output of fxcorrelator.
        :param txip_str: A dotted-decimal string representation of the IP address. e.g. '1.2.3.4'
        :param txport: An integer port number.
        :param issue_meta: A boolean, True to issue metadata, False to skip it.
        :return: <nothing>
        """
        if txip_str is None:
            txip = tengbe.str2ip(self.xeng_tx_destination[0])
        else:
            txip = tengbe.str2ip(txip_str)
        if txport is None:
            txport = self.xeng_tx_destination[1]
        else:
            txport = int(txport)
        self.logger.info('Setting stream destination to %s:%d' % (tengbe.ip2str(txip), txport))
        try:
            THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.gbe_iptx.write(reg=txip))
            THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.gbe_porttx.write(reg=txport))
        except AttributeError:
            self.logger.warning('Set SPEAD stream destination called, but devices NOT written! Have they been created?')
        self.xeng_tx_destination = (tengbe.ip2str(txip), txport)

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
            self.logger.error('Cannot set part of meta destination to None - %s:%d' % (txip_str, txport))
            raise RuntimeError('Cannot set part of meta destination to None - %s:%d' % (txip_str, txport))
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

        THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_txen=False))
        if stop_f:
            self.logger.info('Stopping F transmission')
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(comms_en=False))

    def xeng_get_baseline_order(self):
        """
        Return the order of baseline data output by a CASPER correlator X engine.
        :return:
        """
        # TODO - nants vs number of inputs?
        assert len(self.fengine_sources)/2 == self.n_antennas
        order1 = []
        order2 = []
        for ctr1 in range(self.n_antennas):
            # print 'ctr1(%d)' % ctr1
            for ctr2 in range(int(self.n_antennas/2), -1, -1):
                temp = (ctr1 - ctr2) % self.n_antennas
                # print '\tctr2(%d) temp(%d)' % (ctr2, temp)
                if ctr1 >= temp:
                    order1.append((temp, ctr1))
                else:
                    order2.append((ctr1, temp))
        order2 = [order_ for order_ in order2 if order_ not in order1]
        baseline_order = order1 + order2
        source_names = []
        for source in self.fengine_sources:
            source_names.append(source.name)
        rv = []
        for baseline in baseline_order:
            rv.append((source_names[baseline[0] * 2],       source_names[baseline[1] * 2]))
            rv.append((source_names[baseline[0] * 2 + 1],   source_names[baseline[1] * 2 + 1]))
            rv.append((source_names[baseline[0] * 2],       source_names[baseline[1] * 2 + 1]))
            rv.append((source_names[baseline[0] * 2 + 1],   source_names[baseline[1] * 2]))
        return rv

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
        # update the multicast socket option
        mcast_interface = self.configd['xengine']['multicast_interface_address']
        self.spead_tx.t._udp_out.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF,
                                            socket.inet_aton(mcast_interface))
        # self.spead_tx.t._udp_out.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP,
        #                                     socket.inet_aton(txip_str) + socket.inet_aton(mcast_interface))
        # make the item group we're going to use
        self.spead_meta_ig = spead.ItemGroup()

        self.spead_meta_ig.add_item(name='adc_sample_rate', id=0x1007,
                                    description='The expected ADC sample rate (samples per second) of incoming data.',
                                    shape=[], fmt=spead.mkfmt(('u', 64)),
                                    init_val=self.sample_rate_hz)

        self.spead_meta_ig.add_item(name='n_bls', id=0x1008,
                                    description='Number of baselines in the data product.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=len(self.xeng_get_baseline_order()))

        self.spead_meta_ig.add_item(name='n_chans', id=0x1009,
                                    description='Number of frequency channels in an integration.',
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
                                    description='The baseline ordering in the output data product.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=numpy.array([baseline for baseline in self.xeng_get_baseline_order()]))

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
                                    description='The input (analogue) bandwidth of the system.',
                                    shape=[], fmt=spead.mkfmt(('f', 64)),
                                    init_val=int(self.configd['fengine']['bandwidth']))

        self.spead_meta_ig.add_item(name='n_accs', id=0x1015,
                                    description='The number of spectra that are accumulated per X-engine dump.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.accumulation_len * self.xeng_accumulation_len)

        self.spead_meta_ig.add_item(name='int_time', id=0x1016,
                                    description='The time per integration, in seconds.',
                                    shape=[], fmt=spead.mkfmt(('f', 64)),
                                    init_val=self.xeng_get_acc_time())

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
                                    description='Number of spectra accumulated inside X engine. Determines minimum '
                                                'integration time and user-configurable integration time stepsize. '
                                                'X-engine correlator internals.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=self.xeng_accumulation_len)

        quant_bits = int(self.configd['fengine']['quant_format'].split('.')[0])
        self.spead_meta_ig.add_item(name='requant_bits', id=0x1020,
                                    description='Number of bits after requantisation in the F engines (post FFT and any '
                                                'phasing stages).',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                                    init_val=quant_bits)

        pkt_len = int(self.configd['fengine']['10gbe_pkt_len'])
        self.spead_meta_ig.add_item(name='feng_pkt_len', id=0x1021,
                                    description='Payload size of 10GbE packet exchange between F and X engines '
                                                'in 64 bit words. Usually equal to the number of spectra accumulated '
                                                'inside X engine. F-engine correlator internals.',
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
                                    description='Timestamp scaling factor. Divide the SPEAD data packet timestamp by '
                                                'this number to get back to seconds since last sync.',
                                    shape=[], fmt=spead.mkfmt(('f', 64)),
                                    init_val=self.sample_rate_hz)

        # spead_ig.add_item(name='b_per_fpga', id=0x1047,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        self.spead_meta_ig.add_item(name='xeng_out_bits_per_sample', id=0x1048,
                                    description='The number of bits per value of the xeng accumulator output. '
                                                'Note this is for a single value, not the combined complex size.',
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

        for source_ctr, eqs in enumerate(self.feng_get_eq_list()):
            try:
                eqlen = len(eqs)
            except TypeError:
                eqs = [eqs]
                eqlen = 1
            self.spead_meta_ig.add_item(name='eq_coef_%s' % self.fengine_sources[source_ctr].name,
                                        id=0x1400 + source_ctr,
                                        description='The unitless per-channel digital scaling factors implemented '
                                                    'prior to requantisation, post-FFT, for input %s. '
                                                    'Complex number real,imag 32 bit integers.' %
                                                    self.fengine_sources[source_ctr].name,
                                        shape=[eqlen, 2],
                                        fmt=spead.mkfmt(('u', 32)),
                                        init_val=[[numpy.real(eq_coeff), numpy.imag(eq_coeff)] for eq_coeff in eqs])

        # spead_ig.add_item(name='eq_coef_MyAntStr', id=0x1400+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', 32)),
        #                        init_val=)

        # ndarray = numpy.dtype(numpy.int64), (4096 * 40 * 1, 1, 1)

        # do not issue timestamp here; will be wrong initial value.
        self.spead_meta_ig.add_item(name='timestamp', id=0x1600,
                                    description='Timestamp of start of this integration. uint counting multiples '
                                                'of ADC samples since last sync (sync_time,id=0x1027). Divide this '
                                                'number by timestamp_scale (id=0x1046) to get back to seconds since '
                                                'last sync when this integration was actually started.',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)))
        
        self.spead_meta_ig.add_item(name='flags_xeng_raw', id=0x1601,
                                    description='Flags associated with xeng_raw data output.'
                                                'bit 34 - corruption or data missing during integration '
                                                'bit 33 - overrange in data path '
                                                'bit 32 - noise diode on during integration '
                                                'bits 0 - 31 reserved for internal debugging',
                                    shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)), init_val=0)

        ndarray = numpy.dtype(numpy.int32), (self.n_chans, len(self.xeng_get_baseline_order()), 2)
        self.spead_meta_ig.add_item(name='xeng_raw', id=0x1800,
                                    description='Raw data for %i xengines in the system. This item represents a '
                                                'full spectrum (all frequency channels) assembled from lowest '
                                                'frequency to highest frequency. Each frequency channel contains '
                                                'the data for all baselines (n_bls given by SPEAD ID 0x100b). '
                                                'Each value is a complex number -- two (real and imaginary) '
                                                'unsigned integers.' % len(self.xhosts * self.x_per_fpga),
                                    ndarray=ndarray)

        #TODO hard-coded !!!!!!! :(
#        self.spead_ig.add_item(name=("xeng_raw"),id=0x1800,
#                               description="Raw data for %i xengines in the system. This item represents a full spectrum (all frequency channels) assembled from lowest frequency to highest frequency. Each frequency channel contains the data for all baselines (n_bls given by SPEAD ID 0x100B). Each value is a complex number -- two (real and imaginary) unsigned integers."%(32),
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

    # def _get_fxcorrelator_config(self):
    #     """
    #     """
    #     # attributes we need
    #     self.n_ants = None
    #     self.x_ip_base = None
    #     self.x_port = None
    #
    #     self.fengines = []
    #     self.xengines = []

    ###################################
    # Host creation and configuration #
    ###################################
    '''
    def fxcorrelator_initialise(self, start_tx_f=True, issue_meta=True):
        """
        @param start_tx_f: start f engine transmission
        """

        #set up and start output from fengines
        if start_tx_f:
            ip_base = self.x_ip_base
            port = self.x_port

            #turn on fengine outputs
            for fengine in self.fengines:
                #we will wait to issue spead meta data if initialising
                fengine.set_txip(ip_base, issue_meta=False)
                fengine.set_txport(port, issue_meta=False)

                #turn on transmission
                fengine.start_tx()

        if issue_meta:
            self.spead_issue_meta()

    ###########################
    # f and x engine creation #
    ###########################

    def create_fengines(self):
        """ Generic commands, overload if different
        """
        for ant_id in range(self.n_ants):
            engine = self.create_fengine(ant_id)
            # from an fxcorrelator's view, it is important that these are in order
            self.fengines.append(engine)
        return self.fengines

    def create_xengines(self):
        """ Generic xengine creation, overload if different
        """
        for xengine_index in range(self.n_xengines):
            engine = self.create_xengine(xengine_index)
            # f7rom an fxcorrelator's view, it is important that these are in order
            self.xengines.append(engine)
        return self.xengines

    # the specific fxcorrelator must know about it's specific f and x engine components
    def create_fengine(self, ant_id):
        """Create an fengine.
           Overload in decendant class
        """
        raise NotImplementedError('%s.create_fengine not implemented'%self.descriptor)

    def create_xengine(self, xengine_index):
        """ Create an xengine.
        """
        raise NotImplementedError('%s.create_xengine not implemented'%self.descriptor)
    ########################
    # operational commands #
    ########################

    # These can all be done with generic f and xengine commands
    def check_host_links(self):
        """Ping hosts to see if katcp connections are functioning.
        """
        return (False in self.ping_hosts().values())

    def calculate_integration_time(self):
        """Calculate the number of accumulations and integration time for this system.
        """
        raise NotImplementedError('%s.calculate_integration_time not implemented'%self.descriptor)

    def calculate_bandwidth(self):
        """Determine the bandwidth the system is processing.
        The ADC on the running system must report how much bandwidth it is processing.
        """
        raise NotImplementedError('%s.calculate_bandwidth not implemented'%self.descriptor)

    def connect(self):
        """Connect to the correlator and test connections to all the nodes.
        """
        return self.ping_hosts()
    '''

# end
