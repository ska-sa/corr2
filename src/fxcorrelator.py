"""
Created on Feb 28, 2013

@author: paulp
"""

# things all fxcorrelators Instruments do

import logging
import socket
import time
import sys
import spead
from host_fpga import FpgaHost
from instrument import Instrument
from xengine_fpga import XengineCasperFpga
from fengine_fpga import FengineCasperFpga
import utils
from casperfpga import tengbe

LOGGER = logging.getLogger(__name__)


class FxCorrelator(Instrument):
    """
    A generic FxCorrelator composed of fengines that channelise antenna inputs and xengines that each produce cross products
    from a continuous portion of the channels and accumulate the result. SPEAD data products are produced.
    """
    def __init__(self, descriptor, identifier=-1, config_source=None):
        """
        An abstract base class for instruments.
        :param descriptor: A text description of the instrument. Required.
        :param identifier: An optional integer identifier.
        :param config_source: The instrument configuration source. Can be a text file, hostname, whatever.
        :return: <nothing>
        """
        # we know about f and x hosts and engines, not just engines and hosts
        self.fhosts = []
        self.xhosts = []

        # attributes
        self.katcp_port = None
        self.f_per_fpga = None
        self.x_per_fpga = None
        self.inputs_per_fpga = None
        self.source_names = None
        self.source_mcast = None
        self.spead_tx = None
        self.spead_ig = None

        # parent constructor
        Instrument.__init__(self, descriptor, identifier, config_source)

    def initialise(self, program=True):
        """
        Set up the correlator using the information in the config file
        :return:
        """
        # TODO
        if program:
            logging.info('Programming FPGA hosts.')
            ftups = []
            for f in self.xhosts:
                ftups.append((f, f.boffile))
            for f in self.fhosts:
                ftups.append((f, f.boffile))
            utils.program_fpgas(None, ftups)

        # init the f engines
        self._fengine_initialise()

        # init the x engines
        self._xengine_initialise()

        if program:
            arptime = 200
            stime = time.time()
            print 'Waiting for ARP, %ds   ' % (arptime-(time.time()-stime)),
            while time.time() < stime + arptime:
                sys.stdout.flush()
                time.sleep(1)
            print 'done.'

        return

        # wait for ARP
        if program:
            time.sleep(180)

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

        for ctr, f in enumerate(self.fhosts):
            f.initialise(program=False)
            f.registers.control.write(comms_en=False)

        for ctr, f in enumerate(self.fhosts):
            f.registers.control.write(comms_rst=True)
            f.registers.control.write(status_clr='pulse', comms_status_clr='pulse')
            # comms stuff
            for gbe in f.tengbes:
                gbe.setup(mac='02:02:00:00:01:%02x' % macbase, ipaddress='%s%d' % (feng_ip_prefix, feng_ip_base),
                          port=7777)
                macbase += 1
                feng_ip_base += 1
            f.registers.board_id.write_int(board_id)
            f.registers.txip.write_int(tengbe.str2ip(self.configd['xengine']['10gbe_start_ip']))
            f.registers.txport.write_int(int(self.configd['xengine']['10gbe_start_port']))
            board_id += 1

        # start tap on the f-engines
        for ctr, f in enumerate(self.fhosts):
            for gbe in f.tengbes:
                gbe.tap_start(True)

        # release from reset
        for ctr, f in enumerate(self.fhosts):
            f.registers.control.write(comms_rst=False)

        # subscribe to multicast data
        for ctr, f in enumerate(self.fhosts):
            ctr = 0
            for gbe in f.tengbes:
                gbe.multicast_receive('239.2.0.%2d' % (64 + ctr), 0)
                ctr += 1

        # start f-engine TX
        for f in self.fhosts:
            f.registers.control.write(comms_en=True)

    def _xengine_initialise(self):
        """
        Set up x-engines on this device.
        :return:
        """
        #disable transmission and place cores in reset
        for f in self.xhosts:
            f.initialise(program=False)

        #disable transmission and place cores in reset
        for f in self.xhosts:
            f.registers.ctrl.write(comms_en=False)
            f.registers.ctrl.write(comms_rst=True)
               
        #set up 10gbe cores 
        xipbase = 110
        macbase = 10
        for f in self.xhosts:
           for gbe in f.tengbes:
               gbe.setup(mac='02:02:00:00:02:%02x' % macbase, ipaddress='10.0.0.%d' % xipbase, port=8778)
               macbase += 1
               xipbase += 1

        # tap start
        for f in self.xhosts:
            for gbe in f.tengbes:
                gbe.tap_start(True)
       
        # release cores from reset
        for f in self.xhosts:
            f.registers.ctrl.write(comms_rst = False)

        # set up board id
        board_id = 0
        for f in self.xhosts:
            f.registers.board_id.write(reg=board_id)
            board_id += 1

        # set up accumulation length
        # use default for now
        acc_len = self.accumulation_len
        for f in self.xhosts:
            f.registers.acc_len.write(reg = acc_len)
       
        # start accumulating
        for f in self.xhosts:
            f.registers.vacc_time_msw.write(arm=0, immediate=0)
            f.registers.vacc_time_msw.write(arm=1, immediate=1)
 
        # check accumulations are happening
        vacc_cnts = []
        for f in self.xhosts:
            for eng_index in range(4):
                vacc_cnt = f.registers['vacc_cnt%d' %eng_index].read()['data']['reg']
                vacc_cnts.append(vacc_cnt)

        print 'pausing while data sloshes around a bit' 
        time.sleep(1)

        # check for errors
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
        
        print 'waiting for an accumulation' 
        time.sleep(1)

        vacc_cnts.reverse()
        for f in self.xhosts:
            for eng_index in range(4):
                vacc_cnt = f.registers['vacc_cnt%d' %eng_index].read()['data']['reg']
                vacc_cnt_before = vacc_cnts.pop()                

                if (vacc_cnt_before == vacc_cnt): 
                    print 'no accumulations happening for %s:xeng %d' %(str(f), eng_index)

    ##############################
    ## Configuration information #
    ##############################

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
            LOGGER.error('One or more bitstream files not found.')
            raise IOError('One or more bitstream files not found.')

        # TODO: Load config values from the bitstream meta information

        self.katcp_port = int(self.configd['FxCorrelator']['katcp_port'])
        self.f_per_fpga = int(self.configd['fengine']['f_per_fpga'])
        self.x_per_fpga = int(self.configd['xengine']['x_per_fpga'])
        self.sample_rate_hz = int(self.configd['FxCorrelator']['sample_rate_hz'])
        self.accumulation_len = int(self.configd['xengine']['accumulation_len'])

        # TODO: Work on the logic of sources->engines->hosts

        # 2 pols per FPGA on this initial design, but should be mutable
        self.inputs_per_fengine = int(self.configd['fengine']['inputs_per_fengine'])

        # what antenna ids have we been allocated?
        self.source_names = self.configd['fengine']['source_names'].strip().split(',')
        self.source_mcast = []
        mcast = self.configd['fengine']['source_mcast_ips'].strip().split(',')
        for address in mcast:
            bits = address.split(':')
            port = int(bits[1])
            address, number = bits[0].split('+')
            self.source_mcast.append((address, int(number), int(port)))
        comparo = self.source_mcast[0][1]
        assert comparo == 3, 'F-engines should be receiving from 4 streams.'
        for mcast_addresses in self.source_mcast:
            assert mcast_addresses[1] == comparo, 'All f-engines should be receiving from 4 streams.'

        if len(self.source_names) != len(self.source_mcast):
            raise RuntimeError('We have different numbers of sources and multicast groups. Problem.')

        # set up the hosts and engines based on the config
        self.fhosts = []
        self.xhosts = []
        for hostconfig, hostlist in [(self.configd['fengine'], self.fhosts), (self.configd['xengine'], self.xhosts)]:
            hosts = hostconfig['hosts'].strip().split(',')
            for host in hosts:
                host = host.strip()
                fpgahost = FpgaHost(host, self.katcp_port, hostconfig['bitstream'], connect=True)
                hostlist.append(fpgahost)
        if len(self.source_names) != len(self.fhosts):
            raise RuntimeError('We have different numbers of sources and f-engine hosts. Problem.')
        for fnum, fhost in enumerate(self.fhosts):
            # TODO - logic for inputs vs fengines
            for ctr in range(0, self.inputs_per_fengine):
                engine = FengineCasperFpga(fhost, ctr, self.source_names[fnum], self.configd)
                fhost.add_engine(engine)
        for xnum, xhost in enumerate(self.xhosts):
            for ctr in range(0, self.x_per_fpga):
                engine = XengineCasperFpga(xhost, ctr, self.configd)
                xhost.add_engine(engine)

        # SPEAD receiver
        self.spead_tx = spead.Transmitter(spead.TransportUDPtx(self.configd['xengine']['rx_meta_ip'],
                                                               int(self.configd['xengine']['rx_udp_port'])))
        self.spead_ig = spead.ItemGroup()

        # issue the metadata
        self.spead_issue_meta()

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
            # from an fxcorrelator's view, it is important that these are in order
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

    def set_destination(self, txip_str=None, txport=None, issue_meta=True):
        """Set destination for output of fxcorrelator.
        """
#        if txip_str is None:
#            txip_str = self.configd['txip_str']
#
#        if txport is None:
#            txport = self.configd['txport']

#        #set destinations for all xengines
#        for xengine in self.xengines:
#            xengine.set_txip(txip_str)
#            xengine.set_txport(txport)
#TODO   
#        if issue_meta:
        
        if txip_str is None:
            txip = tengbe.str2ip(self.configd['txip_str'])
        else:
            txip = tengbe.str2ip(txip_str)

        if txport is None:
            txport = self.configd['txport']
        
        for f in self.xhosts: 
            f.registers.txip.write(txip=txip)
            f.registers.txport.write(txport=txport)

    def start_tx(self):
        """ Turns on xengine output pipes needed to start data flow from xengines
        """
        #turn on xengine outputs
#        for xengine in self.xengines:
#            xengine.start_tx()

        for f in self.xhosts:
            f.registers.control.write(comms_en=True)
    
    def stop_tx(self, stop_f=False, issue_meta=True):
        """Turns off output pipes to start data flow from xengines
        @param stop_f: stop output of fengines too
        """
        # does not make sense to stop only certain xengines
        #for xengine in self.xengines:
        #    xengine.stop_tx()

        #if stop_f:
        #    for fengine in self.fengines:
        #        fengine.stop_tx()

        for f in self.xhosts:
            f.registers.control.write(comms_en=False)
    
        if stop_f:
            for f in self.fhosts:
                f.registers.control.write(comms_en=False)

    def spead_issue_meta(self):
        """
        All FxCorrelators issued SPEAD in the same way, with tweakings that are implemented by the child class.
        :return:
        """

        sample_rate = int(self.configd['FxCorrelator']['sample_rate_hz'])
        self.spead_ig.add_item(name='adc_sample_rate', id=0x1007,
                               description='The ADC sample rate (samples per second) ',
                               shape=[],fmt=spead.mkfmt(('u', 64)),
                               init_val=sample_rate)

        n_ants = int(self.configd['fengine']['n_ants'])
        n_bls = (n_ants*(n_ants+1)/2)*4
        self.spead_ig.add_item(name='n_bls', id=0x1008,
                               description='Number of baselines in the cross correlation product.',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=n_bls)

        n_chans = int(self.configd['fengine']['n_chans'])
        self.spead_ig.add_item(name='n_chans', id=0x1009,
                               description='Number of frequency channels in an integration.',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=n_chans)

        # TODO - the number of inputs, cos antennas can be single or multiple pol?
        # f-engines now have only got inputs, they don't know what or from where.
        self.spead_ig.add_item(name='n_ants', id=0x100A,
                               description='The number of antennas.',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=n_ants)

        self.spead_ig.add_item(name='n_xengs', id=0x100B,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=(len(self.xhosts) * self.x_per_fpga))

        # TODO
        # self.spead_ig.add_item(name='bls_ordering', id=0x100C,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=numpy.array([bl for bl in self.get_bl_order()]))

        # self.spead_ig.add_item(name='crosspol_ordering', id=0x100D,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='input_labelling', id=0x100E,
        #                        description='',
        #                        init_val=self.configd['fengine']['source_names'])

        # self.spead_ig.add_item(name='n_bengs', id=0x100F,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        self.spead_ig.add_item(name='center_freq', id=0x1011,
                               description='',
                               shape=[],fmt=spead.mkfmt(('f', 64)),
                               init_val=int(self.configd['fengine']['true_cf']))

        self.spead_ig.add_item(name='bandwidth', id=0x1013,
                               description='',
                               shape=[],fmt=spead.mkfmt(('f', 64)),
                               init_val=int(self.configd['fengine']['bandwidth']))

        acc_len = int(self.configd['xengine']['accumulation_len'])
        xeng_acc_len = int(self.configd['xengine']['xeng_accumulation_len'])
        self.spead_ig.add_item(name='n_accs', id=0x1015,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=(acc_len * xeng_acc_len))

        int_time = ((acc_len * xeng_acc_len) * int(self.configd['fengine']['n_chans'])) / int(self.configd['fengine']['bandwidth'])
        self.spead_ig.add_item(name='int_time', id=0x1016,
                               description='',
                               shape=[],fmt=spead.mkfmt(('f', 64)),
                               init_val=int_time)

        # self.spead_ig.add_item(name='coarse_chans', id=0x1017,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)
        #
        # self.spead_ig.add_item(name='current_coarse_chan', id=0x1018,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)
        #
        # self.spead_ig.add_item(name='fft_shift_fine', id=0x101C,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)
        #
        # self.spead_ig.add_item(name='fft_shift_coarse', id=0x101D,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        self.spead_ig.add_item(name='fft_shift', id=0x101E,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=int(self.configd['fengine']['fft_shift']))

        self.spead_ig.add_item(name='xeng_acc_len', id=0x101F,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=int(self.configd['xengine']['accumulation_len']))

        quant_format = self.configd['fengine']['quant_format']
        quant_bits = int(quant_format.split('.')[0])
        self.spead_ig.add_item(name='requant_bits', id=0x1020,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=quant_bits)

        pkt_len = int(self.configd['fengine']['10gbe_pkt_len'])
        self.spead_ig.add_item(name='feng_pkt_len', id=0x1021,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=pkt_len)

        port = int(self.configd['xengine']['output_destination_port'])
        self.spead_ig.add_item(name='rx_udp_port', id=0x1022,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=port)

        port = int(self.configd['fengine']['10gbe_start_port'])
        self.spead_ig.add_item(name='feng_udp_port', id=0x1023,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=port)

        ip = self.configd['xengine']['output_destination_ip']
        self.spead_ig.add_item(name='rx_udp_ip_str', id=0x1024,
                               description='',
                               shape=[-1],fmt=spead.STR_FMT,
                               init_val=ip)


        import struct
        ip = struct.unpack('>I', socket.inet_aton(self.configd['fengine']['10gbe_start_ip']))[0]
        self.spead_ig.add_item(name='feng_start_ip', id=0x1025,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=ip)

        xeng_clk = 217000000
        self.spead_ig.add_item(name='xeng_rate', id=0x1026,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=xeng_clk)

        self.spead_ig.add_item(name='sync_time', id=0x1027,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=self.synchronisation_epoch)

        # self.spead_ig.add_item(name='n_stokes', id=0x1040,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        x_per_fpga = int(self.configd['xengine']['x_per_fpga'])
        self.spead_ig.add_item(name='x_per_fpga', id=0x1041,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=x_per_fpga)

        n_ants_per_xaui = 1
        self.spead_ig.add_item(name='n_ants_per_xaui', id=0x1042,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=n_ants_per_xaui)

        # self.spead_ig.add_item(name='ddc_mix_freq', id=0x1043,
        #                        description='',
        #                        shape=[],fmt=spead.mkfmt(('f', 64)),
        #                        init_val=)

        # self.spead_ig.add_item(name='ddc_bandwidth', id=0x1044,
        #                        description='',
        #                        shape=[],fmt=spead.mkfmt(('f', 64)),
        #                        init_val=)

        sample_bits = int(self.configd['fengine']['sample_bits'])
        self.spead_ig.add_item(name='adc_bits', id=0x1045,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=sample_bits)

        # self.spead_ig.add_item(name='scale_factor_timestamp', id=0x1046,
        #                        description='',
        #                        shape=[],fmt=spead.mkfmt(('f', 64)),
        #                        init_val=)

        # self.spead_ig.add_item(name='b_per_fpga', id=0x1047,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        xeng_sample_bits = 32
        self.spead_ig.add_item(name='xeng_out_bits_per_sample', id=0x1048,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=xeng_sample_bits)

        f_per_fpga = int(self.configd['fengine']['f_per_fpga'])
        self.spead_ig.add_item(name='f_per_fpga', id=0x1049,
                               description='',
                               shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                               init_val=f_per_fpga)

        # self.spead_ig.add_item(name='beng_out_bits_per_sample', id=0x1050,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='rf_gain_MyAntStr ', id=0x1200+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('f', 64)),
        #                        init_val=)

        # self.spead_ig.add_item(name='eq_coef_MyAntStr', id=0x1400+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', 32)),
        #                        init_val=)

        # self.spead_ig.add_item(name='timestamp', id=0x1600,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='xeng_raw', id=0x1800,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='beamweight_MyAntStr', id=0x2000+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', 32)),
        #                        init_val=)

        # self.spead_ig.add_item(name='incoherent_sum', id=0x3000,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', 32)),
        #                        init_val=)

        # self.spead_ig.add_item(name='n_inputs', id=0x3100,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='digitiser_id', id=0x3101,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='digitiser_status', id=0x3102,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='pld_len', id=0x3103,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='raw_data_MyAntStr', id=0x3300+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='Reserved for SP-CAM meta-data', id=0x7000-0x7fff,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='feng_id', id=0xf101,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='feng_status', id=0xf102,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='frequency', id=0xf103,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='raw_freq_MyAntStr', id=0xf300+inputN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # self.spead_ig.add_item(name='bf_MyBeamName', id=0xb000+beamN,
        #                        description='',
        #                        shape=[], fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
        #                        init_val=)

        # and send everything
        self.spead_tx.send_heap(self.spead_ig.get_heap())

# end
