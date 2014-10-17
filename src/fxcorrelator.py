"""
Created on Feb 28, 2013

@author: paulp
"""

# things all fxcorrelators Instruments do

import logging
import socket
import time
import sys
import numpy
import struct
import spead64_48 as spead

import utils
from host_fpga import FpgaHost
from instrument import Instrument
from xengine_fpga import XengineCasperFpga
from fengine_fpga import FengineCasperFpga
from casperfpga import tengbe
from casperfpga.katcp_fpga import KatcpFpga
from casperfpga import utils as fpgautils

use_xeng_sim = False
use_demo_fengine = True
START_DIGITISER = False
FENG_TX = False

#dbof = '/srv/bofs/deng/r2_deng_tvg_2014_Jul_21_0838.fpg'
dbof = '/srv/bofs/deng/r2_deng_tvg_2014_Aug_27_1619.fpg'
dbof = '/home/paulp/r2_deng_tvg_2014_Sep_11_1230.fpg'
dhost = 'roach020922'
dip_start = '10.100.0.70'
dmac_start = '02:02:00:00:00:01'

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

class DataSource(object):
    def __init__(self, name, ip, iprange, port):
        self.name = name
        self.ip = ip
        self.iprange = iprange
        self.port = port


def digitiser_stop():
    logger = logging.getLogger(__name__)
    logger.info('Stopping digitiser')
    fdig = KatcpFpga(dhost)
    if fdig.is_running():
        fdig.test_connection()
        fdig.get_system_information()
        fdig.registers.control.write(gbe_txen=False)
        fdig.deprogram()
    fdig.disconnect()


def digitiser_start(dig_tx_source):
    logger = logging.getLogger(__name__)
    logger.info('Programming digitiser')
    fdig = KatcpFpga(dhost)
    fdig.deprogram()
    stime = time.time()
    sys.stdout.flush()
    fdig.upload_to_ram_and_program(dbof)
    print time.time() - stime
    fdig.test_connection()
    fdig.get_system_information()
    # stop sending data
    fdig.registers.control.write(gbe_txen=False)
    # start the local timer on the test d-engine - mrst, then a fake sync
    fdig.registers.control.write(mrst='pulse')
    fdig.registers.control.write(msync='pulse')
    # the all_fpgas have tengbe cores, so set them up
    ip_bits = dip_start.split('.')
    ipbase = int(ip_bits[3])
    mac_bits = dmac_start.split(':')
    macbase = int(mac_bits[5])
    for ctr in range(0, 4):
        mac = '%s:%s:%s:%s:%s:%d' % (mac_bits[0], mac_bits[1], mac_bits[2], mac_bits[3], mac_bits[4], macbase + ctr)
        ip = '%s.%s.%s.%d' % (ip_bits[0], ip_bits[1], ip_bits[2], ipbase + ctr)
        fdig.tengbes['gbe%d' % ctr].setup(mac=mac, ipaddress=ip, port=7148)
    for gbe in fdig.tengbes:
        gbe.tap_start(True)
    # set the destination IP and port for the tx
    txaddr = dig_tx_source.ip
    txaddr_bits = txaddr.split('.')
    txaddr_base = int(txaddr_bits[3])
    txaddr_prefix = '%s.%s.%s.' % (txaddr_bits[0], txaddr_bits[1], txaddr_bits[2])
    print 'digitisers sending to: %s%d port %d' % (txaddr_prefix, txaddr_base + 0, dig_tx_source.port)
    print 'digitisers sending to: %s%d port %d' % (txaddr_prefix, txaddr_base + 1, dig_tx_source.port)
    print 'digitisers sending to: %s%d port %d' % (txaddr_prefix, txaddr_base + 2, dig_tx_source.port)
    print 'digitisers sending to: %s%d port %d' % (txaddr_prefix, txaddr_base + 3, dig_tx_source.port)
    fdig.write_int('gbe_iptx0', tengbe.str2ip('%s%d' % (txaddr_prefix, txaddr_base + 0)))
    fdig.write_int('gbe_iptx1', tengbe.str2ip('%s%d' % (txaddr_prefix, txaddr_base + 1)))
    fdig.write_int('gbe_iptx2', tengbe.str2ip('%s%d' % (txaddr_prefix, txaddr_base + 2)))
    fdig.write_int('gbe_iptx3', tengbe.str2ip('%s%d' % (txaddr_prefix, txaddr_base + 3)))
    fdig.write_int('gbe_porttx', dig_tx_source.port)
    fdig.registers.control.write(gbe_rst=False)
    # enable the tvg on the digitiser and set up the pol id bits
    fdig.registers.control.write(tvg_select0=1)
    fdig.registers.control.write(tvg_select1=1)
    fdig.registers.id2.write(pol1_id=1)
    # start tx
    print 'Starting dig TX...',
    sys.stdout.flush()
    fdig.registers.control.write(gbe_txen=True)
    print 'done.'
    sys.stdout.flush()
    fdig.disconnect()


class FxCorrelator(Instrument):
    """
    A generic FxCorrelator composed of fengines that channelise antenna inputs and
    xengines that each produce cross products from a continuous portion of the channels and accumulate the result.
    SPEAD data products are produced.
    """
    def __init__(self, descriptor, identifier=-1, config_source=None, logger=None):
        """
        An abstract base class for instruments.
        :param descriptor: A text description of the instrument. Required.
        :param identifier: An optional integer identifier.
        :param config_source: The instrument configuration source. Can be a text file, hostname, whatever.
        :param logger: Use the module logger by default, unless something else is given.
        :return: <nothing>
        """
        self.logger = logger or logging.getLogger(__name__)

        # we know about f and x hosts and engines, not just engines and hosts
        self.fhosts = []
        self.xhosts = []

        # attributes
        self.katcp_port = None
        self.f_per_fpga = None
        self.x_per_fpga = None
        self.sources = None
        self.spead_tx = None
        self.accumulation_len = -1

        self.xeng_tx_destination = None
        self.meta_destination = None

        # parent constructor
        Instrument.__init__(self, descriptor, identifier, config_source)

    def initialise(self, program=True, tvg=False):
        """
        Set up the correlator using the information in the config file
        :return:
        """

        # TODO
        # digitiser_stop()

        if program:
            logging.info('Programming FPGA hosts.')
            ftups = []
            for f in self.xhosts:
                ftups.append((f, f.boffile))
            for f in self.fhosts:
                ftups.append((f, f.boffile))
            fpgautils.program_fpgas(ftups, None, 15)

        fpgautils.threaded_fpga_function(self.fhosts, 10, 'initialise', False)
        fpgautils.threaded_fpga_function(self.xhosts, 10, 'initialise', False)

        # for f in self.fhosts:
        #     f.initialise(program=False)
        # for f in self.xhosts:
        #     f.initialise(program=False)

        if program:
            # init the f engines
            self._fengine_initialise()
            # init the x engines
            self._xengine_initialise(tvg=tvg)

        if program:
            for fpga_ in self.fhosts:
                fpga_.tap_arp_reload()
            for fpga_ in self.xhosts:
                fpga_.tap_arp_reload()
            sleeptime = 80
            print 'Waiting %d seconds for ARP to settle...' % sleeptime,
            sys.stdout.flush()
            starttime = time.time()
            time.sleep(sleeptime)
            # raw_input('wait for arp')
            end_time = time.time()
            print 'done. That took %d seconds.' % (end_time - starttime)
            sys.stdout.flush()

        # TODO
        if START_DIGITISER:
            digitiser_start(self.sources[0])

        # check to see if the f engines are receiving all their data
        print 'Waiting up to 20 seconds for f engines to receive data',
        sys.stdout.flush()
        self._feng_check_rx_okay()
        print 'okay.'
        sys.stdout.flush()

        # start f-engine TX
        if FENG_TX:
            logging.info('Starting f-engine datastream')
            for f in self.fhosts:
                #f.registers.control.write(tvg_ct=True)
                if use_demo_fengine:
                    f.registers.control.write(gbe_txen=True)
                else:
                    f.registers.control.write(comms_en=True)

        '''
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
        '''

    def feng_status_clear(self):
        for f in self.fhosts:
            f.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse', cnt_rst='pulse')

    def xeng_status_clear(self):
        for f in self.xhosts:
            f.registers.control.write(clr_status='pulse', gbe_debug_rst='pulse')

    def _feng_check_rx_okay(self):
        # check to see if the f engines are receiving all their data
        def get_gbe_data(fpga_):
            """
            Get 10gbe data counters from the fpga.
            """
            returndata = {}
            for gbecore in fpga_.tengbes:
                returndata[gbecore.name] = gbecore.read_counters()
            return returndata
        timeout = 20
        stime = time.time()
        frxregs = THREADED_FPGA_OP(self.fhosts, 5, get_gbe_data)
        rx_okay = False
        while time.time() < stime + timeout:
            time.sleep(1)
            frxregs_new = THREADED_FPGA_OP(self.fhosts, 5, get_gbe_data)
            still_the_same = False
            for fpga in frxregs.keys():
                for core in frxregs[fpga].keys():
                    rxctr_old = frxregs[fpga][core]['%s_rxctr' % core]['data']['reg']
                    rxctr_new = frxregs_new[fpga][core]['%s_rxctr' % core]['data']['reg']
                    rxbad_old = frxregs[fpga][core]['%s_rxbadctr' % core]['data']['reg']
                    rxbad_new = frxregs_new[fpga][core]['%s_rxbadctr' % core]['data']['reg']
                    rxerr_old = frxregs[fpga][core]['%s_rxerrctr' % core]['data']['reg']
                    rxerr_new = frxregs_new[fpga][core]['%s_rxerrctr' % core]['data']['reg']
                    if (rxctr_old == rxctr_new) or (rxbad_old != rxbad_new) or (rxerr_old != rxerr_new):
                        still_the_same = True
                        continue
                if still_the_same:
                    continue
            if not still_the_same:
                # print 'all rx'
                rx_okay = True
                break
            # else:
            #     print 'nope', time.time()
            frxregs = frxregs_new
        if not rx_okay:
            raise RuntimeError('F engine RX data error after %d seconds.' % timeout)

    def _fengine_initialise(self):
        """
        Set up f-engines on this device.
        :return:
        """
        feng_ip_octets = [int(bit) for bit in self.configd['fengine']['10gbe_start_ip'].split('.')]
        assert len(feng_ip_octets) == 4, 'That\'s an odd IP address.'
        feng_ip_base = feng_ip_octets[3]
        feng_ip_prefix = '%d.%d.%d.' % (feng_ip_octets[0], feng_ip_octets[1], feng_ip_octets[2])
        macbase = 10
        board_id = 0
        iptx = tengbe.str2ip(self.configd['xengine']['10gbe_start_ip'])
        porttx = int(self.configd['xengine']['10gbe_start_port'])

        if use_demo_fengine:
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_txen=False))
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_rst=False))
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(status_clr='pulse',
                                                                                          gbe_cnt_rst='pulse',
                                                                                          cnt_rst='pulse'))
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.iptx_base.write_int(iptx))
        else:
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(comms_en=False))
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(comms_rst=True))
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(status_clr='pulse',
                                                                                          comms_status_clr='pulse'))
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.txip.write_int(iptx))
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.txport.write_int(porttx))

        for ctr, f in enumerate(self.fhosts):
            # comms stuff
            for gbe in f.tengbes:
                gbe.setup(mac='02:02:00:00:01:%02x' % macbase, ipaddress='%s%d' % (feng_ip_prefix, feng_ip_base),
                          port=7148)
                macbase += 1
                feng_ip_base += 1
            if use_demo_fengine:
                f.registers.tx_metadata.write(board_id=board_id, porttx=porttx)
            else:
                f.registers.board_id.write_int(board_id)
            board_id += 1

        # start tap on the f-engines
        for ctr, f in enumerate(self.fhosts):
            for gbe in f.tengbes:
                gbe.tap_start(True)

        # release from reset
        if use_demo_fengine:
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_rst=False))
        else:
            THREADED_FPGA_OP(self.fhosts, 10, lambda fpga_: fpga_.registers.control.write(comms_rst=False))

        # subscribe to multicast data
        source_ctr = 0
        for host_ctr, host in enumerate(self.fhosts):
            gbe_ctr = 0
            for fengine_ctr in range(0, self.f_per_fpga):
                source = self.sources[source_ctr]
                # print 'host %s(%d) fengine(%d) source %s %s %d' %
                # (host.host, host_ctr, fengine_ctr, source.name, source.ip, source_ctr)
                rxaddr = source.ip
                rxaddr_bits = rxaddr.split('.')
                rxaddr_base = int(rxaddr_bits[3])
                rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0], rxaddr_bits[1], rxaddr_bits[2])
                if (len(host.tengbes) / self.f_per_fpga) != source.iprange:
                    raise RuntimeError(
                        '10Gbe ports (%d) do not match sources IPs (%d)' % (len(host.tengbes), source.iprange))
                for ctr in range(0, source.iprange):
                    gbename = host.tengbes.names()[gbe_ctr]
                    gbe = host.tengbes[gbename]
                    rxaddress = '%s%d' % (rxaddr_prefix, rxaddr_base + ctr)
                    self.logger.debug('host %s %s subscribing to address %s', host.host, gbe.name, rxaddress)
                    self.logger.info('host %s %s subscribing to address %s', host.host, gbe.name, rxaddress)
                    gbe.multicast_receive(rxaddress, 0)
                    gbe_ctr += 1
                source_ctr += 1

    def _xengine_initialise(self, tvg=False):
        """
        Set up x-engines on this device.
        :return:
        """
        # simulator
        if use_xeng_sim:
            THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.simulator.write(en=False, rst='pulse'))

        # disable transmission, place cores in reset, and give control register a known state
        THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.control.write(gbe_txen=False,
                                                                                      gbe_rst=True,
                                                                                      status_clr='pulse',
                                                                                      gbe_debug_rst='pulse'))

        # set up accumulation length
        self.xeng_set_acc_len(200)

        # set up default destination ip and port
        self.set_stream_destination(issue_meta=False)
        self.set_meta_destination()

        # set up board id
        board_id = 0
        for f in self.xhosts:
            f.registers.board_id.write(reg=board_id)
            board_id += 1  # 1 on new systems, 4 on old xeng_rx_reorder system

        #set up 10gbe cores 
        xipbase = 110
        macbase = 10
        for f in self.xhosts:
            for gbe in f.tengbes:
                gbe.setup(mac='02:02:00:00:02:%02x' % macbase, ipaddress='10.100.0.%d' % xipbase, port=7148)
                macbase += 1
                xipbase += 1
                gbe.tap_start()
        # tvg
        # if tvg:
        #     for f in self.xhosts:
        #         f.registers.tvg_select.write(xeng=2)
        # else:
        #     for f in self.xhosts:
        #         f.registers.tvg_control.write(vacc=0, xeng=0)
        #         # f.registers.tvg_sel.write(xaui=0, vacc=0, descr=0, xeng=0)

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

    def xeng_set_acc_time(self, acc_time_s):
        # calculate the acc_len to write for the required time
        if use_xeng_sim:
            new_acc_len = round((acc_time_s * self.xeng_clk) / (self.xeng_accumulation_len * self.n_chans))
            if new_acc_len == 0:
                raise RuntimeError('Accumulation length of zero makes no sense')
            self.logger.info('New accumulation time %.2f becomes accumulation length %d' % (acc_time_s, new_acc_len))
            self.xeng_set_acc_len(new_acc_len)
        else:
            return
            raise NotImplementedError('Not done for real x-engines yet')

    def xeng_get_acc_time(self):
        return (self.accumulation_len * self.xeng_accumulation_len * self.n_chans) / (self.xeng_clk * 1.0)

    def xeng_set_acc_len(self, new_acc_len=-1):
        """
        Set the QDR vector accumulation length.
        :param new_acc_len:
        :return:
        """
        if new_acc_len != -1:
            self.logger.debug('Setting new accumulation length %d' % new_acc_len)
            self.accumulation_len = new_acc_len
        THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.acc_len.write_int(self.accumulation_len))

    def xeng_get_acc_len(self):
        return self.accumulation_len

    ##############################
    ## Configuration information #
    ##############################

    def set_labels(self, newlist):
        if len(newlist) != len(self.sources):
            self.logger.error('Number of supplied source labels does not match number of configured sources.')
            return False
        for ctr, source in enumerate(self.sources):
            source.name = newlist[ctr]
        return True

    def get_labels(self):
        source_names = ''
        for source in self.sources:
            source_names += source.name + ' '
        source_names = source_names.rstrip(' ')
        return source_names

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if the instrument read a config successfully, raise an error if not?
        """
        Instrument._read_config(self)

        if use_demo_fengine:
            self.configd['fengine']['bitstream'] = '/srv/bofs/feng/feng_rx_test_2014_Aug_27_1835.fpg'
            # self.configd['fengine']['bitstream'] = '/home/paulp/frt_aa_2014_Sep_17_1242.fpg'
            #self.configd['fengine']['bitstream'] = '/home/paulp/frt_aa_2014_Oct_06_1152.fpg'
            # self.configd['fengine']['bitstream'] = '/home/paulp/frt_a_2014_Sep_17_1058.fpg'
            self.configd['fengine']['bitstream'] = '/home/paulp/frt_a_2014_Oct_06_1702.fpg'
            # self.configd['fengine']['bitstream'] = '/home/paulp/frt_b_2014_Sep_17_1110.fpg'
       #     self.configd['fengine']['bitstream'] = '/home/paulp/frt_c_2014_Sep_17_1343.fpg'
            self.configd['fengine']['bitstream'] = '/home/paulp/frt_e_2014_Oct_16_1632.fpg'
            #self.configd['fengine']['bitstream'] = '/home/paulp/frt_e_txsnap_2014_Oct_03_1057.fpg'
            # self.configd['fengine']['bitstream'] = '/home/paulp/feng_rx_test_2014_Sep_17_1442.fpg'

        # check that the bitstream names are present
        try:
            open(self.configd['fengine']['bitstream'], 'r').close()
            open(self.configd['xengine']['bitstream'], 'r').close()
        except IOError:
            self.logger.error('xengine bitstream: %s' % self.configd['xengine']['bitstream'])
            self.logger.error('fengine bitstream: %s' % self.configd['fengine']['bitstream'])
            self.logger.error('One or more bitstream files not found.')
            raise IOError('One or more bitstream files not found.')

        # TODO: Load config values from the bitstream meta information

        self.katcp_port = int(self.configd['FxCorrelator']['katcp_port'])
        self.f_per_fpga = int(self.configd['fengine']['f_per_fpga'])
        self.x_per_fpga = int(self.configd['xengine']['x_per_fpga'])
        self.sample_rate_hz = int(self.configd['FxCorrelator']['sample_rate_hz'])
        self.accumulation_len = int(self.configd['xengine']['accumulation_len'])
        self.xeng_accumulation_len = int(self.configd['xengine']['xeng_accumulation_len'])
        self.n_chans = int(self.configd['fengine']['n_chans'])

        self.set_stream_destination(self.configd['xengine']['output_destination_ip'],
                                    int(self.configd['xengine']['output_destination_port']))
        self.set_meta_destination(self.configd['xengine']['output_destination_ip'],
                                  int(self.configd['xengine']['output_destination_port']))

        if use_xeng_sim:
            self.xeng_clk = 225000000
        else:
            self.xeng_clk = 230000000
            #raise NotImplementedError

        # the f-engines have this many 10Gbe ports per f-engine unit of operation
        self.ports_per_fengine = int(self.configd['fengine']['ports_per_fengine'])

        # what antenna ids have we been allocated?
        self.sources = []
        source_names = self.configd['fengine']['source_names'].strip().split(',')
        source_mcast = self.configd['fengine']['source_mcast_ips'].strip().split(',')
        assert len(source_mcast) == len(source_names), \
            'Source names (%d) must be paired with multicast source addresses (%d)' % (len(source_names),
                                                                                       len(source_mcast))
        for counter, address in enumerate(source_mcast):
            try:
                bits = address.split(':')
                port = int(bits[1])
                address, number = bits[0].split('+')
            except ValueError, err:
                self.logger.error('The address %s is not correctly formed. Expect 1.2.3.4+50:7777. Bailing.', address)
                raise err
            self.sources.append(DataSource(source_names[counter], address, int(number) + 1, int(port)))
        comparo = self.sources[0].iprange
        assert comparo == self.ports_per_fengine, \
            'F-engines should be receiving from %d streams.' % self.ports_per_fengine
        for mcast_address in self.sources:
            assert mcast_address.iprange == comparo, \
                'All f-engines should be receiving from %d streams.' % self.ports_per_fengine

        # set up the hosts and engines based on the config
        self.fhosts = []
        self.xhosts = []
        for hostconfig, hostlist in [(self.configd['fengine'], self.fhosts), (self.configd['xengine'], self.xhosts)]:
            hosts = hostconfig['hosts'].strip().split(',')
            for host in hosts:
                host = host.strip()
                fpgahost = FpgaHost(host, self.katcp_port, hostconfig['bitstream'], connect=True)
                hostlist.append(fpgahost)
        if len(self.sources) != len(self.fhosts) * self.f_per_fpga:
            raise RuntimeError('We have different numbers of sources (%d) and f-engines (%d). Problem.',
                               len(self.sources), len(self.fhosts))
        for fnum, fhost in enumerate(self.fhosts):
            # TODO - logic for inputs vs fengines
            for ctr in range(0, self.f_per_fpga):
                engine = FengineCasperFpga(fhost, ctr, self.sources[fnum].name, self.configd)
                fhost.add_engine(engine)
        for xnum, xhost in enumerate(self.xhosts):
            for ctr in range(0, self.x_per_fpga):
                engine = XengineCasperFpga(xhost, ctr, self.configd)
                xhost.add_engine(engine)

        # turn the product names into a list
        self.configd['xengine']['output_products'] = self.configd['xengine']['output_products'].split(',')

        # done
        return True

    def _read_config_file(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if we read the file successfully, False if not
        """
        try:
            self.configd = utils.parse_ini_file(self.config_source)
        except IOError:
            return False
        return True

    def _read_config_server(self):
        """
        Get instance-specific setup information from a given server. Via KATCP?
        :return:
        """
        raise NotImplementedError('Still have to do this')

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

    def set_stream_destination(self, txip_str=None, txport=None, issue_meta=True):
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
        self.logger.info('Setting stream destination to %s:%d', tengbe.ip2str(txip), txport)
        try:
            THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.gbe_iptx.write(reg=txip))
            THREADED_FPGA_OP(self.xhosts, 10, lambda fpga_: fpga_.registers.gbe_porttx.write(reg=txport))
        except AttributeError:
            self.logger.warning('Set SPEAD stream destination called, but devices NOT written! Have they been created?')
        self.xeng_tx_destination = (tengbe.ip2str(txip), txport)
        if issue_meta:
            self.spead_issue_meta()

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
            self.logger.error('Cannot set part of meta destination to None - %s:%d', txip_str, txport)
            raise RuntimeError('Cannot set part of meta destination to None - %s:%d', txip_str, txport)
        self.logger.info('Setting meta destination to %s:%d', txip_str, txport)
        # make a new SPEAD receiver
        del self.spead_tx
        mcast_interface = self.configd['xengine']['multicast_interface_address']
        self.spead_tx = spead.Transmitter(spead.TransportUDPtx(txip_str, txport))

        # update the multicast socket option
        mcast_interface = self.configd['xengine']['multicast_interface_address']
        self.spead_tx.t._udp_out.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF,
                                            socket.inet_aton(mcast_interface))
        # self.spead_tx.t._udp_out.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP,
        #                                     socket.inet_aton(txip_str) + socket.inet_aton(mcast_interface))
        # and update the meta destination
        self.meta_destination = (txip_str, txport)

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

    def set_eq(self):
        """
        Set the F-engine EQ by writing to BRAM
        :return:
        """
        # how to write the eq values!
        # creal = 4096 * [1]
        # cimag = 4096 * [0]
        # coeffs = 8192 * [0]
        # coeffs[0::2] = creal
        # coeffs[1::2] = cimag
        # import struct
        # ss = struct.pack('<8192h', *coeffs)
        # fpgas[0].write('eq1', ss, 0)


    def get_baseline_order(self):
        """
        Return the order of baseline data output by a CASPER correlator X engine.
        :return:
        """
        # TODO
        n_ants = 4
        assert(len(self.sources)/2 == n_ants)
        order1 = []
        order2 = []
        for ctr1 in range(n_ants):
            # print 'ctr1(%d)' % ctr1
            for ctr2 in range(int(n_ants/2), -1, -1):
                temp = (ctr1 - ctr2) % n_ants
                # print '\tctr2(%d) temp(%d)' % (ctr2, temp)
                if ctr1 >= temp:
                    order1.append((temp, ctr1))
                else:
                    order2.append((ctr1, temp))
        order2 = [order_ for order_ in order2 if order_ not in order1]
        baseline_order = order1 + order2
        source_names = []
        for source_ in self.sources:
            source_names.append(source_.name)
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
        # bail if we haven't set meta destination yet
        if self.spead_tx is None:
            self.logger.warning('Called spead_issue_meta but no transmitter instantiated. '
                                'Your metadata has NOT gone out!')
            return
        if self.meta_destination is None:
            self.logger.warning('Called spead_issue_meta but no meta destination set. '
                                'Your metadata has NOT gone out!')
            return

        # make a new Item group
        spead_ig = spead.ItemGroup()

        sample_rate = int(self.configd['FxCorrelator']['sample_rate_hz'])
        spead_ig.add_item(name='adc_sample_rate', id=0x1007,
                          description='The ADC sample rate (samples per second) ',
                          shape=[], fmt=spead.mkfmt(('u', 64)),
                          init_val=sample_rate)

        #n_ants = int(self.configd['fengine']['n_ants'])
        # TODO
        n_ants = 4
        n_bls = (n_ants * (n_ants + 1) / 2) * 4
        spead_ig.add_item(name='n_bls', id=0x1008,
                          description='Number of baselines in the cross correlation product.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=n_bls)

        spead_ig.add_item(name='n_chans', id=0x1009,
                          description='Number of frequency channels in an integration.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.n_chans)

        # TODO - the number of inputs, cos antennas can be single or multiple pol?
        # f-engines now have only got inputs, they don't know what or from where.
        spead_ig.add_item(name='n_ants', id=0x100A,
                          description='The number of antennas in the system.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=n_ants)

        spead_ig.add_item(name='n_xengs', id=0x100B,
                          description='The number of x-engines in the system.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=(len(self.xhosts) * self.x_per_fpga))

        spead_ig.add_item(name='bls_ordering', id=0x100C,
                          description='The baseline ordering in the output data product.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=numpy.array([baseline for baseline in self.get_baseline_order()]))

        # spead_ig.add_item(name='crosspol_ordering', id=0x100D,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='input_labelling', id=0x100E,
        #                        description='',
        #                        init_val=self.configd['fengine']['source_names'])

        # spead_ig.add_item(name='n_bengs', id=0x100F,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        spead_ig.add_item(name='center_freq', id=0x1011,
                          description='The on-sky centre-frequency.',
                          shape=[], fmt=spead.mkfmt(('f', 64)),
                          init_val=int(self.configd['fengine']['true_cf']))

        spead_ig.add_item(name='bandwidth', id=0x1013,
                          description='The input bandwidth of the system.',
                          shape=[], fmt=spead.mkfmt(('f', 64)),
                          init_val=int(self.configd['fengine']['bandwidth']))

        number_accs = self.accumulation_len * self.xeng_accumulation_len
        spead_ig.add_item(name='n_accs', id=0x1015,
                          description='The number of accumulations done in the x-engine.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=number_accs)

        int_time = (number_accs * self.n_chans) / self.xeng_clk
        spead_ig.add_item(name='int_time', id=0x1016,
                          description='The time per integration.',
                          shape=[], fmt=spead.mkfmt(('f', 64)),
                          init_val=int_time)

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

        spead_ig.add_item(name='fft_shift', id=0x101E,
                          description='The FFT bitshift pattern. F-engine correlator internals.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=int(self.configd['fengine']['fft_shift']))

        spead_ig.add_item(name='xeng_acc_len', id=0x101F,
                          description='Number of spectra accumulated inside X engine. Determines minimum '
                                      'integration time and user-configurable integration time stepsize. '
                                      'X-engine correlator internals.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.xeng_accumulation_len)

        quant_format = self.configd['fengine']['quant_format']
        quant_bits = int(quant_format.split('.')[0])
        spead_ig.add_item(name='requant_bits', id=0x1020,
                          description='Number of bits after requantisation in the F engines (post FFT and any '
                                      'phasing stages).',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=quant_bits)

        pkt_len = int(self.configd['fengine']['10gbe_pkt_len'])
        spead_ig.add_item(name='feng_pkt_len', id=0x1021,
                          description='Payload size of 10GbE packet exchange between F and X engines '
                                      'in 64 bit words. Usually equal to the number of spectra accumulated '
                                      'inside X engine. F-engine correlator internals.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=pkt_len)

        port = int(self.configd['xengine']['output_destination_port'])
        spead_ig.add_item(name='rx_udp_port', id=0x1022,
                          description='Destination UDP port for X engine output.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=port)

        port = int(self.configd['fengine']['10gbe_start_port'])
        spead_ig.add_item(name='feng_udp_port', id=0x1023,
                          description='Port for F-engines 10Gbe links in the system.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=port)

        ip = self.configd['xengine']['output_destination_ip']
        spead_ig.add_item(name='rx_udp_ip_str', id=0x1024,
                          description='Destination UDP IP for X engine output.',
                          shape=[-1], fmt=spead.STR_FMT,
                          init_val=ip)

        ip = struct.unpack('>I', socket.inet_aton(self.configd['fengine']['10gbe_start_ip']))[0]
        spead_ig.add_item(name='feng_start_ip', id=0x1025,
                          description='Start IP address for F-engines in the system.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=ip)

        spead_ig.add_item(name='xeng_rate', id=0x1026,
                          description='Target clock rate of processing engines (xeng).',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.xeng_clk)

        spead_ig.add_item(name='sync_time', id=0x1027,
                          description='The time at which the digitiser\'s were synchronised.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.synchronisation_epoch)

        # spead_ig.add_item(name='n_stokes', id=0x1040,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        x_per_fpga = int(self.configd['xengine']['x_per_fpga'])
        spead_ig.add_item(name='x_per_fpga', id=0x1041,
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
        spead_ig.add_item(name='adc_bits', id=0x1045,
                          description='How many bits per ADC sample.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=sample_bits)

        # TODO - what is the scale factor going to be?
        scale_factor = self.accumulation_len * self.xeng_accumulation_len * self.n_chans * 2
        spead_ig.add_item(name='scale_factor_timestamp', id=0x1046,
                               description='Timestamp scaling factor. Divide the SPEAD data packet timestamp by '
                                           'this number to get back to seconds since last sync.',
                               shape=[],fmt=spead.mkfmt(('f', 64)),
                               init_val=scale_factor)

        # spead_ig.add_item(name='b_per_fpga', id=0x1047,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        xeng_sample_bits = 32
        spead_ig.add_item(name='xeng_out_bits_per_sample', id=0x1048,
                          description='The number of bits per value of the xeng accumulator output. '
                                      'Note this is for a single value, not the combined complex size.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=xeng_sample_bits)

        f_per_fpga = int(self.configd['fengine']['f_per_fpga'])
        spead_ig.add_item(name='f_per_fpga', id=0x1049,
                          description='Number of X engines per FPGA host.',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=f_per_fpga)

        # spead_ig.add_item(name='beng_out_bits_per_sample', id=0x1050,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='rf_gain_MyAntStr ', id=0x1200+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('f', 64)),
        #                        init_val=)

        # spead_ig.add_item(name='eq_coef_MyAntStr', id=0x1400+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', 32)),
        #                        init_val=)

        spead_ig.add_item(name='timestamp', id=0x1600,
                          description='Timestamp',
                          shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=0)

        #ndarray = numpy.dtype(numpy.int64), (4096 * 40 * 1, 1, 1)
        ndarray = numpy.dtype(numpy.int32), (4096, 40, 2)
        spead_ig.add_item(name='xeng_raw', id=0x1800,
                          description='X-engine vector accumulator output data.',
                          ndarray=ndarray)

        # spead_ig.add_item(name='timestamp', id=0x1600,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # spead_ig.add_item(name='xeng_raw', id=0x1800,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

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

        # and send everything
        self.spead_tx.send_heap(spead_ig.get_heap())

# end
