# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from casperfpga import host, tengbe
from casperfpga.misc import log_runtime_error, log_not_implemented_error, program_fpgas
from casperfpga.katcp_client_fpga import KatcpClientFpga

from corr2 import configuration_katcp_client

import time, numpy

class Instrument():
    '''
    An abstract base class for instruments.
    Instruments have links to hosts.
    These Hosts host processing Engines that do work.
    Instruments produce data products.
    '''
    def __init__(self, descriptor='instrument', config_host=None, katcp_port=None, config_file=None):
        ''' Constructor.
        @param descriptor: The name this instrument is identified by in configuration information
        @param config_host: hostname server configuration daemon is resident on
        @param katcp_port: port number configuration daemon is listening on
        @param config_file: The location of the file that will be used to configure this instrument (overrides daemon)
        '''
        #TODO type etc checking

        self.descriptor = descriptor
        self.config_file = config_file

        # open a configuration portal
        self.config_portal = configuration_katcp_client.ConfigurationKatcpClient(config_host, katcp_port, config_file)

        self.config = {}
        self.config['engines'] = {}
        self.config['hosts'] = {}
        
        self._get_instrument_config()
   
        self.host_links = {}
        self.engines = {}    

        LOGGER.info('Instrument %s initialised'%(self.descriptor))
    
    def _get_instrument_config(self):
        ''' Get generic instrument related configuration
        '''

        # get info on different host types we know about
        host_types = self.config_portal.get_str_list(['hosts', 'types'])
        for host_type in host_types:
            host_info = {}
            # things specific to different kinds of hosts
            if 'roach2':
                host_info['katcp_port'] = self.config_portal.get_int(['%s'%host_type, 'katcp_port'])
                host_info['program_timeout'] = self.config_portal.get_int(['%s'%host_type, 'program_timeout'])

            self.config['hosts']['%s' %host_type] = host_info

        # list of engine types required
        engines =           self.config_portal.get_str_list(['%s'%self.descriptor, 'engines']) 
        # whether host location is important
        host_locations =    self.config_portal.get_str_list(['%s'%self.descriptor, 'host_locations']) 
        # for each engine, the numer required
        n_engines =         self.config_portal.get_int_list(['%s'%self.descriptor, 'n_engines']) 
        # for each engine, the base mac address for the group
        mac_bases =         self.config_portal.get_str_list(['%s'%self.descriptor, 'mac_bases']) 
        # ip base for each engine type
        ip_bases =          self.config_portal.get_str_list(['%s'%self.descriptor, 'ip_bases']) 
        # port we receive data on for each engine type
        ports =             self.config_portal.get_int_list(['%s'%self.descriptor, 'ports']) 

        for engine_index, engine_type in enumerate(engines):
            engine_info = {}

            # the host type required for the engine
            host_type           = self.config_portal.get_string(['%s' %engine_type, 'host_type'])
            # the host configuration required for the engine
            host_configuration  = self.config_portal.get_string(['%s' %engine_type, 'host_configuration'])
            # whether we require 'specific' hosts or can take from an 'arbitrary' pool
            host_location = host_locations[engine_index]
            if host_location == 'specific':
                string = '%s_hosts'%engines[host_index]
                engine_info['%s'%string] = self.config_portal.get_str_list(['%s'%self.descriptor, '%s'%string])

            # the number of engines accommodated in each host
            engines_per_host    = self.config_portal.get_int(['%s' %engine_type, 'engines_per_host'])
            # the configuration file for the host
            host_config_file    = self.config_portal.get_string(['%s' %engine_type, 'host_config_file'])
            
            engine_info = { 'descriptor': engine_type, \
                            'n_engines': n_engines[engine_index], \
                            'host_location': host_location, \
                            'mac_base': mac_bases[engine_index], \
                            'ip_base': ip_bases[engine_index], \
                            'port': ports[engine_index], \
                            'host_type': host_type, \
                            'host_configuration': host_configuration, \
                            'engines_per_host': engines_per_host, \
                            'host_config_file': host_config_file}

            self.config['engines']['%s'%engine_type] = engine_info

        #TODO SPEAD meta data device/s?

    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        if name == 'hosts':
            tmp = {} 
            for host_type, host_links in self.host_links.items():
                #update, removing duplicates
                tmp.update(host_links)
            return tmp.values()

        return object.__getattribute__(name)
    
    #############################
    # Instrument initialisation #
    #############################

    def instrument_initialise(self, configure_hosts=True, setup_hosts=True):
        ''' Instrument related initialisation
            Includes optional host configuration, hardware calibration etc of hosts
            Engine creation based on configuration
        '''
        # run through component engines, creating necessary links to hosts
        self._create_links_to_hosts()

        # need to configure certain hosts before creating engines
        if configure_hosts:
            self._configure_hosts()

        # set up hosts based on type of engines they will contain
        if setup_hosts:
            self._setup_hosts()

        # create processing engines
        self._create_engines()
    
        #TODO SPEAD transmitter?

    ##############################
    # Creation of links to hosts #
    ##############################

    def _create_links_to_hosts(self):
        ''' Create all the links to hosts we need for our engines
        '''
        # go through engine types
        for engine_type in self.config['engines']:
            host_links = self.create_host_links_for_engines_of_type(engine_type)
            self.host_links['%s'%engine_type] = host_links

    def create_host_links_for_engines_of_type(self, engine_type):
        log_not_implemented_error(LOGGER, '%s.create_host_links_for_engines_of_type not implemented' %self.descriptor)

    def instrument_create_host_links_for_engines_of_type(self, engine_type):
        ''' Generic instrument version
        '''
        info = self.config['engines']['%s' %engine_type]
        n_engines = info['n_engines']        
        engines_per_host = info['engines_per_host']            
        host_type = info['host_type']            
        host_configuration = info['host_configuration']            
        host_links = {}            

        if numpy.mod(n_engines, engines_per_host) != 0:
            msg = 'Don''t know how to create hosts for %i %ss with %i per host'%(n_engines, engine_type, engines_per_host)
            log_runtime_error(LOGGER, msg)

        #TODO check info and, for colocated engines, don't request again, but reuse hostnames   

        n_hosts = n_engines/engines_per_host

        #request host names
        host_names = self.config_portal.get_hosts(host_type, host_configuration, n_hosts)

        if len(host_names) != n_hosts:
            log_runtime_error(LOGGER, 'Requested %i %s %s hosts, only got %i'%(n_hosts, host_type, host_configuration, len(host_names)))

        host_links = self._init_links_to_hosts_of_type(host_names, host_type)

        #TODO specific hostnames

        LOGGER.info('Created %i host links to %s %ss for %ss'%(len(host_links), host_configuration, host_type, engine_type))

        return host_links    

    def _init_links_to_hosts_of_type(self, host_names, host_type):
        ''' Initialise links to hosts of particular type and configuration 
        '''
        # we call our own method. Overload for other hosts and then call 
        # the generic instrument one for the ones we know about
        return self._instrument_init_links_to_hosts_of_type(host_names, host_type)

    def _instrument_init_links_to_hosts_of_type(self, host_names, host_type='roach2'):
        ''' Initialise links to hosts the Instrument class knows about
        @param host_names: names unique to host used during creation of link
        @param host_type: host type allowing host specific actions to be performed
        '''
        host_links = {}
        if host_type == 'roach2':
            katcp_port = self.config['hosts']['roach2']['katcp_port']
            for host_name in host_names:
                host = KatcpClientFpga(host_name, katcp_port)
                host_links.update({host_name: host})
        else:
            log_runtime_error(LOGGER, 'Don''t know how to initialise ''%s'' host links'%host_type)
        return host_links
    
    ######################
    # Host configuration #
    ######################

    def _configure_hosts(self):
        ''' Configure hosts 
        '''
        #we don't run through engines here, but configure all hosts of the same
        #type together to save time        

        # go through types of hosts we know about
        for host_type in self.config['hosts']:
            self._configure_hosts_of_type(host_type)

    def _configure_hosts_of_type(self, host_type):
        ''' Configure the hosts that make up this Instrument based on their type
        '''
        self.instrument_configure_hosts_of_type(host_type)

    def instrument_configure_hosts_of_type(self, host_type):
        ''' The instrument class knows how to configure some hosts
            Call this method from specific Instrument's configure_hosts_of_type method
        '''
        if host_type == 'roach2':
            # host configuration for FPGAs includes
            # 1. programming fpgas
            # 2. calibration

            # go through engines, creating dictionary of hosts
            timeout = self.config['hosts']['roach2']['program_timeout']
            fpgas = {}
            for engine_type, info in self.config['engines'].items():
                # if this engine type uses roach2 hosts
                if info['host_type'] == host_type:
                    config_file = info['host_config_file']
                    fpga_links = self.host_links['%s' %engine_type]
                    # update our list (overwriting duplicates)
                    for host_name, fpga_link in fpga_links.items():
                        config_tuple = (fpga_link, config_file)
                        fpgas.update({host_name: config_tuple})

            self._program_fpga_list(config_tuples=fpgas.values(), deprogram=True, timeout=len(fpgas.values())*timeout)

        #TODO hardware calibration of each host 

    def _program_fpga_list(self, config_tuples, deprogram=True, timeout=45):
        ''' @param config_tuples: list of (fpga, config file name) tuples
            @param deprogram: deprogram all FPGAs first
            @param timeout: timeout in seconds to complete 
        '''
        for fpga, cfile in config_tuples:
            if deprogram == True:
                fpga.deprogram()
           
        #TODO return dictionary showing ones that failed
        LOGGER.info('Programming FPGA hosts...')
        stime = time.time()
        program_fpgas(config_tuples, timeout=timeout)
        period = time.time() - stime
        LOGGER.info('Programmed %d FPGAs in %i seconds' %(len(config_tuples), period)) 

    ##############
    # Host setup #    
    ##############

    def _setup_hosts(self):
        ''' Setup hosts according to engine type on them
            Overload for different host setup based on instrument
        '''
        # go through each engine type
        for engine_type in self.config['engines']:
            self.setup_hosts_for_engines_of_type(engine_type)
   
    def setup_hosts_for_engines_of_type(self, engine_type):
        ''' Specific host setup depending on engine type
        '''       
        log_not_implemented_error(LOGGER, '%s.setup_hosts_for_engines_of_type not implemented' %self.descriptor)
 
    def instrument_setup_hosts_for_engines_of_type(self, engine_type):
        ''' Basic setup after programming
            Overload if you want to set up FPGAs differently
        '''
        
        fpgas = self.host_links['%s' %engine_type].values()
        mac_base = self.config['engines']['%s'%engine_type]['mac_base']
        mac = tengbe.str2mac(mac_base)
        ip_base = self.config['engines']['%s'%engine_type]['ip_base']
        ip = tengbe.str2ip(ip_base)
        port = self.config['engines']['%s'%engine_type]['port']

        # default is to setup interface mac and ips to monotonically increment from base with fixed port
        for fpga_index, fpga in enumerate(fpgas):
            for gbe in fpga.tengbes:
                gbe.setup(mac=tengbe.mac2str(mac), ipaddress=tengbe.ip2str(ip), port=port)
                #start tap immediately
                gbe.tap_start(True)
                mac += 1
                ip += 1
            # set up board id to increment monotonically as well
            fpga.registers.board_id.write_int(fpga_index)

        LOGGER.info('Setup %d FPGAs used by %ss with; \nbase mac address: %s\nbase ip address: %s\nport %d' %(len(fpgas), engine_type, mac_base, ip_base, port)) 

    ###################
    # Engine creation #
    ###################

    def _create_engines(self):
        ''' Run through engine types
        '''
        for engine_type in self.config['engines']:
            self.engines['%s'%engine_type] = self.create_engines_of_type(engine_type)

    # we don't know about every engine type here as some are setup
    # differently depending on Instrument type so leave to decendant to sort it out
    def create_engines_of_type(self, engine_type):
        ''' Create the engines that make up this Instrument based on their type
        '''
        log_not_implemented_error(LOGGER, '%s.create_engines_of_type not implemented'%self.descriptor)

    ###############################
    # Useful operational commands #
    ###############################

    def ping_hosts(self, hosts_to_ping=all):
        '''Ping hosts, or a single host, if provided.
        @param host_to_ping: If None, all hosts will be pinged.
        @return: dictionary with host ids as key and ping result (True/False) as value.
        '''
        if (hosts_to_ping == all):
            ntp = self.hosts
        else: 
            ntp = hosts_to_ping
        returnval = {}
        for key, node in ntp.items():
            returnval[key] = node.ping()
        return returnval
    
    def instrument_teardown(self, deconfigure_hosts=False):
        '''
        '''
        #deconfigure and return hosts to pool   
        #TODO 
        log_not_implemented_error(LOGGER, '%s.instrument_teardown not implemented'%self.descriptor)

    def __str__(self):
        returnstr = '%s' % (self.descriptor)
        return returnstr
   
# end
