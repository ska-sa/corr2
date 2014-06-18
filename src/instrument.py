# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2 import host, configuration_katcp_client
from misc import log_runtime_error, log_not_implemented_error

# we know about FPGAs
from corr2.katcp_client_fpga import KatcpClientFpga

import numpy

class Instrument(object):
    '''
    An abstract base class for instruments.
    Instruments are made of Hosts.
    These Hosts host processing Engines that do work.
    '''
    def __init__(self, descriptor='instrument', config_host=None, katcp_port=None, config_file=None):
        '''Constructor for the base Instrument class.
        @param description: The name this instrument is identified by in configuration information
        @param config_file: The location of the file that will be used to configure this instrument (overrides daemon)
        @param config_host: hostname for server of config, resource allocation etc
        @param katcp_port: port number configuration daemon is listening on
        '''
        self.descriptor = descriptor
        self.config_file = config_file

        # open a configuration portal
        self.config_portal = configuration_katcp_client.ConfigurationKatcpClient(config_file=config_file)

        self.config = {}
        self.config['engines'] = {}
        self.config['host_links'] = {}
        
        self._get_instrument_config()
    
        self.host_links = {}
        self.engines = {}    

        LOGGER.info('Instrument %s of type %s'%(self.descriptor, self.config['instrument_type']))
    
    def _get_instrument_config(self):
        '''Get generic instrument related stuff
        
        '''

        self.config['instrument_type'] = self.config_portal.get_string(['%s'%self.descriptor, 'instrument_type']) 

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
            host_type = self.config_portal.get_string(['%s' %engine_type, 'host_type'])
            engines_per_host = self.config_portal.get_int(['%s' %engine_type, 'engines_per_host'])
            host_config_file = self.config_portal.get_string(['%s' %engine_type, 'host_config_file'])
            
            host_location = host_locations[engine_index]
            engine_info = { 'descriptor': engine_type, \
                            'n_engines': n_engines[engine_index], \
                            'host_location': host_location, \
                            'mac_base': mac_bases[engine_index], \
                            'ip_base': ip_bases[engine_index], \
                            'port': ports[engine_index], \
                            'host_type': host_type, \
                            'katcp_port': katcp_port, \
                            'engines_per_host': engines_per_host, \
                            'host_config_file': host_config_file}
            if host_location == 'specific':
                string = '%s_hosts'%engines[host_index]
                engine_info['%s'%string] = self.config_portal.get_str_list(['%s'%self.descriptor, '%s'%string])

            self.config['engines']['%s'%engine_type] = engine_info

        # get info on different host types for when batch configuring
        host_types = self.config_portal.read_str_list(['hosts', 'types'])
        for host_type in host_types:
            host_info = {}
            #things specific to different kinds of hosts
            if 'roach2':
                host_info['katcp_port'] = self.config_portal.get_int(['%s'%host_type, 'katcp_port'])
                host_info['program_timeout'] = self.config_portal.get_int(['%s'%host_type, 'program_timeout'])

            self.config['hosts']['%s' %host_type] = info

        #TODO SPEAD meta data device/s?

    def initialise_instrument(self, configure_hosts=False):
        ''' Instrument related initialisation
            Includes optional host configuration, hardware calibration etc of hosts
            Engine creation based on configuration
        '''
        self.create_links_to_hosts()

        # need to configure certain hosts before creating engines
        if configure_hosts:
            self.configure_hosts()

        # set up hosts based on type of engines they will contain
        self.setup_hosts()

        self.create_engines()
    
        #TODO SPEAD transmitter?

    ##############################
    # Creation of links to hosts #
    ##############################

    def create_host_links(self):
        ''' Create all the host links we need for our engines
        '''
        # create an empty list of hosts based on type
        for host_type in self.config['hosts']:
            self.host_links['%s'%host_type] = {}

        for engine_type, info in self.config['engines'].items():
            n_engines = info['n_engines']        
            engines_per_host = info['engines_per_host']            
            host_type = info['host_type']            
            
            if numpy.mod(n_engines, engines_per_host) != 0:
                msg = 'Don''t know how to create hosts for %i %ss with %i per host'%(n_engines, engine_type, engines_per_host)
                log_runtime_error(LOGGER, msg)

            #TODO check info, don't request again, but reuse hostnames for colocated hosts    

            n_hosts = n_engines/engines_per_host

            #request host names
            host_names = self.config_portal.get_hosts(host_type, n_hosts)

            if len(host_names) != n_hosts:
                log_runtime_error(LOGGER, 'Requested %i hosts, only got %i'%(n_hosts, len(host_names)))

            hosts = self.init_host_links(host_names, info['host_config_file'], host_type, info['katcp_port'])            

            if len(hosts) != n_hosts:
                log_runtime_error(LOGGER, 'Not enough unique hosts for %ss'%engine_type)
          
            # store a list of host_links based on engine type 
            # NOTE some instruments care about the order of these so not a dictionary
            self.host_links['%s'%engine_type] = hosts.values()

            # update the list of host_links of a certain type
            # will overwrite previous hosts with same host names
            self.host_links['%s'%host_type].update(hosts)

            #TODO specific hostnames
       
        for host_type, host_links in self.host_links.items():
            # NOTE some instruments care about the order of these so not a dictionary
            LOGGER.info('Created %i host links to %ss'%(len(host_links), host_type))    

    def init_host_links(self, host_names, config_file, host_type='roach2', katcp_port=7147):
        ''' Initialise katcp links to type of host
        '''
        hosts = {}
        if host_type == 'roach2':
            katcp_port = self.config['hosts']['roach2']['katcp_port']
            for host_name in host_names:
                host = KatcpClientFpga(host_name, katcp_port)
                host.set_target_bof(config_file)
                hosts.update({host_name: host})
        else:
            log_runtime_error(LOGGER, 'Don''t know how to initialise %s hosts'%host_type)
        return hosts
    
    ######################
    # Host configuration #
    ######################

    def configure_hosts(self):
        ''' Configure hosts 
        '''
        #we don't run through engines here, but collect all hosts of the same
        #type together and configure them together to save time        

        # go through types of hosts we know about
        for host_type, info in self.config['hosts'].items():
            if host_type == 'roach2':
                # host configuration for FPGAs includes
                # 1. programming fpgas
                # 2. calibration

                fpga_links = self.host_links['%s'%host_type]
                timeout = info['timeout']
                self.program_fpga_list(fpga_links, timeout=len(fpga_links)*timeout)
                #TODO hardware calibration of each host 

    def _program_fpga_list(fpgas, deprogram=True, timeout=45):
        ''' @param hosts: hosts to configure
            @param deprogram: deprogram all FPGAs first
            @param timeout: timeout in seconds to complete 
        '''
        ftuples = []
        for fpga in fpgas:
            if deprogram == True:
                fpga.deprogram()
            ftuples.extend([(fpga, fpga.get_bof())])
           
        #TODO return dictionary showing ones that failed
        LOGGER.info('Programming FPGA hosts...')
        stime = time.time()
        program_fpgas(ftuples, timeout=timeout)
        period = time.time() - stime
        LOGGER.info('Programmed %d FPGAs in %i seconds.' %(len(fpgas), period)) 

    ###################
    # Engine creation #
    ###################

    def create_engines(self):
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

    ##############
    # Host setup #    
    ##############

    def setup_instrument_hosts(self):
        ''' Setup hosts according to engine type on them
            Overload for different setup based on instrument
        '''

    def _setup_instrument_fpgas(self, fpgas, mac_base, ip_base, port, board_id_inc):
        ''' Basic setup after programming
            Overload if you want to set up FPGAs differently
        '''
        for fpga_index, fpga in enumerate(fpgas):
            for gbe in fpga.tengbes:
                mac = '%s%02x' %(mac_base, mac_offset)
                ip = '%s%d' %(ip_base, ip_offset)
                gbe.setup(mac=mac, ipaddress=ip, port=port)
                #start tap early, we should be done with everything before hit other fpgas
                gbe.tap_start(True)
                mac_offset += 1
                ip_offset += 1
            fpga.registers.board_id.write_int(fpga_index*board_id_inc)

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
    
    def __str__(self):
        returnstr = '%s: %s\n' % (self.name, self.description)
        for node in self.hosts.itervalues():
            returnstr += '\t%s\n' % node
        return returnstr
    
    def teardown_instrument(self, deconfigure_hosts=False):
        '''
        '''
        #deconfigure and return hosts to pool   
        #TODO 

    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        if name == 'fpgas' or name == 'roach2' or name == 'hosts':
            tmp = []
            for host_type, host_links in self.confighosts_link.items():
                if host_type == 'roach2':
                    tmp.extend(host_links)
            return tmp
        return object.__getattribute__(self, name)
    
# end
