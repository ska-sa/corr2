"""
Created on Feb 28, 2013

@author: paulp
"""

# things all fxcorrelators Instruments do

import logging
LOGGER = logging.getLogger(__name__)

from fpgahost import FpgaHost
from instrument import Instrument
from fengine import Fengine

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
        super(FxCorrelator, self).__init__(descriptor, identifier, config_source)

        # we know about f and x hosts and engines, not just engines and hosts
        self.fhosts = []
        self.xhosts = []
        self.xengines = []
        self.fengines = []

        self.initialise()

    def initialise(self):
        """
        Set up the correlator using the information in the config file
        :return:
        """
        # set up the hosts
        for host in self.config['fengine']['hosts']:
            fpga = FpgaHost(host)
            for neng in range(0, self.config['fengine']['num_f_per_fpga']):
                eng =

            self.fhosts.append(fpga)
            self.hosts.append(fpga)

        for host in self.config['xengine']['hosts']:
            fpga = FpgaHost(host)
            self.xhosts.append(fpga)
            self.hosts.append(fpga)

        # probe a host to find out the configuration
        dummy = FpgaHost('127.0.0.1')
        dummy.get_system_information(self.config['fengine']['bitstream'])
        print dummy.memory_devices

        dummy = FpgaHost('127.0.0.1')
        dummy.get_system_information(self.config['xengine']['bitstream'])
        print dummy.memory_devices

        # set up the engines

        # program_fpgas(self.bitstream_x, self.xfpgas)
        # program_fpgas(self.bitstream_f, self.ffpgas)

    def _read_config_file(self):
        """
        Read the instrument configuration from self.config_source.
        :return: <nothing>
        """
        super(FxCorrelator, self)._read_config_file()
        # check that the bitstream names are present
        try:
            open(self.config['fengine']['bitstream'], 'r').close()
            open(self.config['xengine']['bitstream'], 'r').close()
        except IOError:
            LOGGER.error('One or more bitstream files not found.')
            raise IOError('One or more bitstream files not found.')
        return

    def _read_config_server(self):
        """
        Get instance-specific setup information from a given server. Via KATCP?
        :return:
        """
        raise NotImplementedError('Still have to do this')

    ##############################
    ## Configuration information #
    ##############################

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
