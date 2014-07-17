"""
Created on Feb 28, 2013

@author: paulp
"""

# things all fxcorrelators Instruments do

import logging
from host_fpga import FpgaHost
from instrument import Instrument
from xengine_fpga import XengineCasperFpga
from fengine_fpga import FengineCasperFpga
import utils

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
        :param config_source: The instrument configuration source, can be a text file, hostname, whatever.
        :return: <nothing>
        """
        # we know about f and x hosts and engines, not just engines and hosts
        self.fhosts = []
        self.xhosts = []
        self.xengines = []
        self.fengines = []

        # parent constructor
        Instrument.__init__(self, descriptor, identifier, config_source)

    def initialise(self):
        """
        Set up the correlator using the information in the config file
        :return:
        """
        utils.program_fpgas(self.bitstream_x, self.xhosts)
        utils.program_fpgas(self.bitstream_f, self.fhosts)

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
            open(self.config['fengine']['bitstream'], 'r').close()
            open(self.config['xengine']['bitstream'], 'r').close()
        except IOError:
            LOGGER.error('One or more bitstream files not found.')
            raise IOError('One or more bitstream files not found.')

        # TODO: Load config values from the bitstream meta information

        self.katcp_port = int(self.config['FxCorrelator']['katcp_port'])
        self.f_per_fpga = int(self.config['fengine']['f_per_fpga'])
        self.x_per_fpga = int(self.config['xengine']['x_per_fpga'])

        # TODO: Work on the logic of sources->engines->hosts

        self.num_pols = int(self.config['xengine']['x_per_fpga'])
        if self.num_pols != self.f_per_fpga:
            raise RuntimeError('Polarisations != f/fpga is confusing.')

        # what antenna ids have we been allocated?
        self.source_names = self.config['fengine']['source_names'].strip().split(',')
        self.source_mcast = self.config['fengine']['source_mcast_ips'].strip().split(',')
        if len(self.source_names) != len(self.source_mcast):
            raise RuntimeError('We have different numbers of sources and multicast groups. Problem.')

        # set up the hosts and engines based on the config
        self.fhosts = []
        self.xhosts = []
        for hostconfig, hostlist in [(self.config['fengine'], self.fhosts), (self.config['xengine'], self.xhosts)]:
            hosts = hostconfig['hosts'].strip().split(',')
            for host in hosts:
                host = host.strip()
                fpgahost = FpgaHost(host, self.katcp_port, hostconfig['bitstream'], )
                hostlist.append(fpgahost)
        if len(self.source_names) != len(self.fhosts):
            raise RuntimeError('We have different numbers of sources and f-engine hosts. Problem.')
        for fnum, fhost in enumerate(self.fhosts):
            for ctr in range(0, self.f_per_fpga):
                engine = FengineCasperFpga(fhost, ctr, self.source_names[fnum], self.config)
                fhost.add_engine(engine)
        for xnum, xhost in enumerate(self.xhosts):
            for ctr in range(0, self.x_per_fpga):
                engine = XengineCasperFpga(xhost, ctr, self.config)
                xhost.add_engine(engine)

        return True

    def _read_config_file(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if we read the file successfully, False if not
        """
        try:
            self.config = utils.parse_ini_file(self.config_source)
        except IOError:
            return False
        return True

    def _read_config_server(self):
        """
        Get instance-specific setup information from a given server. Via KATCP?
        :return:
        """
        raise NotImplementedError('Still have to do this')

    def _get_fxcorrelator_config(self):
        """
        """
        # attributes we need   
        self.n_ants = None
        self.x_ip_base = None
        self.x_port = None

        self.fengines = []
        self.xengines = []

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
            self.fxcorrelator_issue_meta()

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
        log_not_implemented_error(LOGGER, '%s.create_fengine not implemented'%self.descriptor)

    def create_xengine(self, xengine_index):
        """ Create an xengine.
        """
        log_not_implemented_error(LOGGER, '%s.create_xengine not implemented'%self.descriptor)

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
        log_not_implemented_error(LOGGER, '%s.calculate_integration_time not implemented'%self.descriptor)

    def calculate_bandwidth(self):
        """Determine the bandwidth the system is processing.
        The ADC on the running system must report how much bandwidth it is processing.
        """
        log_not_implemented_error(LOGGER, '%s.calculate_bandwidth not implemented'%self.descriptor)

    def connect(self):
        """Connect to the correlator and test connections to all the nodes.
        """
        return self.ping_hosts()

    def set_destination(self, txip_str=None, txport=None, issue_meta=True):
        """Set destination for output of fxcorrelator.
        """
        if txip_str is None:
            txip_str = self.config['txip_str']

        if txport is None:
            txport = self.config['txport']

        #set destinations for all xengines
        for xengine in self.xengines:
            xengine.set_txip(txip_str)
            xengine.set_txport(txport)
#TODO   
#        if issue_meta:
 
    def start_tx(self):
        """ Turns on xengine output pipes needed to start data flow from xengines
        """
        #turn on xengine outputs
        for xengine in self.xengines:
            xengine.start_tx()
    
    def stop_tx(self, stop_f=False, issue_meta=True):
        """Turns off output pipes to start data flow from xengines
        @param stop_f: stop output of fengines too
        """
        # does not make sense to stop only certain xengines
        for xengine in self.xengines:
            xengine.stop_tx()

        if stop_f:
            for fengine in self.fengines:
                fengine.stop_tx()

    def fxcorrelator_issue_meta(self):
        """All fxcorrelators issued SPEAD in the same way, with tweakings that
           are implemented by the child class
        """
        #TODO

# end
