# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

# TODO
# TODO much of the configuration and host creation functionality is generic across different instruments, move to Instrument class
# TODO

import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error, program_fpgas, config_get_string, config_get_list, config_get_int, config_get_float
import instrument, katcp_client_fpga, digitiser, fengine,  xengine, types
from corr2.fengine_fb_fpga import FengineFbFpga
from corr2.xengine_fpga import XengineFpga
from corr2.katcp_client_fpga import KatcpClientFpga

import struct, socket, iniparse, time, numpy

class FxCorrelator(instrument.Instrument):
    '''
    An FxCorrelator containing hosts of various kinds.
    '''
    def __init__(self, name, config_file=None, config_hosts=True, descriptor='FX Correlator'):
        '''
        Constructor
        @param name: The instrument's unique name
        @param config_file: An XML/YAML/ini config file describing the correlator
        @param config_hosts: configure hosts
        @param descriptor: A brief description of the correlator
        '''
        instrument.Instrument.__init__(self, name=name, descriptor=descriptor, config_file=config_file)
    
        # get configuration information
        self.get_config(filename=config_file)

        self.fhosts = {}
        self.xhosts = {} 
        # create host data structures
        self.create_hosts()

        # set up hardware in preparation for engines
        # can be skipped if wanting to operate on existing system
        if config_hosts:
            self.configure_hosts()

        self.get_host_system_information()

        self.fengines = {}
        self.xengines = {}
        self.create_engines()

    ##############################
    ## Configuration information #
    ##############################

    def get_config(self, filename=None):
        '''Get configuration information for our fxcorrelator
        @param filename: An XML/YAML/ini config file describing the correlator.
        '''
        # if we are provided with a config file, initialise using that
        if filename != None:
            # process config file, creating necessary data structures
            LOGGER.info('Parsing config file \'%s\'', filename)
            self.parse_config(filename)
        # TODO otherwise we will get our configuration in some other way 
        else:
            log_runtime_error('Configuration from config file only at the moment')

    def parse_config(self, filename):
        '''Parse an XML/YAML config file and store config in config attribute
        @param filename: The filename for the config file
        '''
        if filename == '':
            log_runtime_error(LOGGER, 'No config file provided.')
            return
        try:
            fptr = open(filename, 'r')
        except:
            raise IOError('Configuration file \'%s\' cannot be opened.' % filename)

        cfg_parser = iniparse.INIConfig(fptr)
        self.config = {}

        # some constants
        self.config['pol_map'] = {'x':0, 'y':1}
        self.config['rev_pol_map'] = {0:'x', 1:'y'}
        self.config['pols'] = ['x', 'y']

        # port to contact roaches on
        self.config['katcp_port']           = config_get_int(cfg_parser, 'katcp', 'katcp_port')

        # read host info 
        self.config['host_allocation']      = config_get_string(cfg_parser, 'hosts', 'host_allocation')
        self.config['roach_host_pool']      = config_get_list(cfg_parser, 'hosts', 'roach_host_pool')

        self.config['f_host_type']          = config_get_string(cfg_parser, 'engines', 'f_host_type')
        self.config['f_per_host']           = config_get_int(cfg_parser, 'engines', 'f_per_host')
        self.config['x_host_type']          = config_get_string(cfg_parser, 'engines', 'x_host_type')
        self.config['x_per_host']           = config_get_int(cfg_parser, 'engines', 'x_per_host')

        self.config['n_ants']               = config_get_int(cfg_parser, 'correlator', 'n_ants')
        f_hosts_required = (self.config['n_ants']*len(self.config['pols']))/self.config['f_per_host']
        LOGGER.info('Requesting %i hosts of type %s for fengines', f_hosts_required, self.config['f_host_type'])
        self.config['hosts_f']              = self.request_host_allocation(self.config['f_host_type'], f_hosts_required)

        self.config['n_chans']              = config_get_int(cfg_parser, 'fengine', 'n_chans')
        self.config['n_chans_per_x']        = config_get_int(cfg_parser, 'xengine', 'n_chans_per_x')
        x_hosts_required = (self.config['n_chans']/self.config['n_chans_per_x'])/self.config['x_per_host']
        LOGGER.info('Requesting %i hosts of type %s for xengines', x_hosts_required, self.config['x_host_type'])
        self.config['hosts_x']              = self.request_host_allocation(self.config['x_host_type'], x_hosts_required)
 
        # check for bof names
        self.config['fpga_program_timeout'] = config_get_int(cfg_parser, 'correlator', 'fpga_program_timeout')
        self.config['bitstream_f']          = config_get_string(cfg_parser, 'files', 'bitstream_f')
        self.config['bitstream_x']          = config_get_string(cfg_parser, 'files', 'bitstream_x')

        LOGGER.info('Using bof file\n\tF(%s)', self.config['bitstream_f'])
        LOGGER.info('Using bof file\n\tX(%s)', self.config['bitstream_x'])

        fptr.close()

    def request_host_allocation(self, host_type, number):
        ''' Request host allocation, result is list of host_names 
        '''
    
        hosts = list()
        if self.config['host_allocation'] == 'file':
            if host_type == 'roach':
                avail_hosts = self.config['roach_host_pool']
                if len(avail_hosts) < number:    
                    log_runtime_error(LOGGER, 'Requested %d hosts but only %d available' %(number, len(avail_hosts)))
                else:
                    hosts.extend(avail_hosts[0:number])
                    avail_hosts = avail_hosts[number:len(avail_hosts)]
                self.config['roach_host_pool'] = avail_hosts

            else:
                log_runtime_error(LOGGER, 'Don''t know about host type %s' %host_type)
                
            temp = self.config['roach_host_pool'] 
        else:
            log_runtime_error(LOGGER, 'Don''t know how to request hosts by means of %s' %self.config['host_allocation'])

        return hosts

    ###################################
    # Host creation and configuration #
    ###################################

    def create_hosts(self):
        '''Create the hosts that make up this FX correlator.
        '''
        # fhosts 
        if self.config.has_key('hosts_f') == True:
            self.fhosts.update(self.init_fpga_hosts(self.config['hosts_f'], self.config['bitstream_f']))
            LOGGER.info('Created %i fhosts' %len(self.fhosts))

        # xhosts
        if self.config.has_key('hosts_x') == True:
            self.xhosts.update(self.init_fpga_hosts(self.config['hosts_x'], self.config['bitstream_x']))
            LOGGER.info('Created %i xhosts' %len(self.xhosts))

    def init_fpga_hosts(self, hostnames, bof_file):
        '''Create a dictionary of fpga hosts of the same type
        '''   
        hosts = {}
        for hostname in hostnames:
            # we have an FPGA based host
            if hostname.startswith('roach'):
                host = KatcpClientFpga(hostname, self.config['katcp_port'])
                host.set_bof(bof_file)
                hosts.update({host.host: host})
        return hosts
    
    def configure_hosts(self):
        '''Do any configuration of hosts required before adding engines
        '''        
        self.program_fpga_hosts(timeout=len(self.fpga_hosts)*self.config['fpga_program_timeout'])
 
    def program_fpga_hosts(self, hosts=all, deprogram=True, timeout=45):
        ''' Program fpga hosts to prepare for engines
            @param hosts: hosts to configure
            @param deprogram: deprogram all FPGAs first
            @param timeout: timeout in seconds to complete 
        '''
        if hosts==all:
            hosts = self.fpga_hosts.values() 

        ftuples = []
        for host in hosts:
            if deprogram == True:
                host.deprogram()
            ftuples.extend([(host, host.get_bof())])
           
        #TODO return dictionary showing ones that failed
        LOGGER.info('Programming FPGA hosts...')
        stime = time.time()
        program_fpgas(ftuples, timeout=timeout)
        period = time.time() - stime
        LOGGER.info('Programmed %d FPGA hosts in %i seconds.' %(len(hosts), period))
            
    def get_host_system_information(self):
        '''Get information from hosts that we might need during engine creation
        '''
        self.get_fpga_host_system_information()

    def get_fpga_host_system_information(self, hosts=all):
        '''Get system information for all fpga hosts
        '''
        if hosts==all:
            hosts = self.fpga_hosts.values() 
        for host in hosts:
            host.get_system_information()

    #TODO this should be overloaded in higher class
    def create_engines(self):
        ''' Create the engines that make up this FX correlator.
        '''
        # fengines
        self.create_fengine_fb_fpga_engines() 

        # xengines
        self.create_xengine_fpga_engines() 

    def create_fengine_fb_fpga_engines(self):
        '''Create fpga based full band fengines
        '''
        f_per_host = self.config['f_per_host']
        pols = self.config['pols']

        for host_index, host in enumerate(self.fhosts.values()):
            for engine_index in range(f_per_host):
                antenna_index = numpy.floor(((host_index*f_per_host)+engine_index)/len(pols))
                engine_id = '%i%s' %(antenna_index, pols[numpy.mod(engine_index,2)])
                # create fengine, allocating which input data it will service at the same time
                feng = FengineFbFpga(parent=host, engine_id=engine_id, index=engine_index, config_file=self.config_file)
                # add to host
                host.add_engine(feng) 
                self.fengines[engine_id] = feng

    def create_xengine_fpga_engines(self):
        '''
        '''
        x_per_host = self.config['x_per_host']

        for host_index, host in enumerate(self.xhosts.values()):
            for engine_index in range(x_per_host):
                engine_id = host_index*x_per_host+engine_index
                # create xengine, allocating which input data it will service at the same time
                xeng = XengineFpga(parent=host, engine_id=engine_id, index=engine_index, config_file=self.config_file)
                # add to host
                host.add_engine(xeng) 
                self.xengines['%i'%engine_id] = xeng

    ####################
    ## Initialisation ##
    ####################
 
    def initialise(self, set_equalisation=True, send_spead=True):
        '''Perform startup and setup after configuration has been done.
           @param program: program the various hosts before initialisation
           @param set_equalisation: set equalisation values
           @param send_spead: issue spead meta data once done initialising
        '''

        # check connections to all hosts
        if self.check_katcp_connections() != True:
            log_runtime_error(LOGGER, 'Connection to one or more hosts failed')
            return

        # set equalisation values, delay sending SPEAD meta data
        if set_equalisation == True:
            self.set_equalisation_values(send_spead=False)

            #TODO
#        if send_spead == True:

        self.calculate_bandwidth()
        self.calculate_integration_time()

    def check_katcp_connections(self):
        '''Ping hosts to see if katcp connections are functioning.
        '''
        return (False not in self.ping_hosts().values())

    def get_input_mapping_from_string(self, ant_string):
        ''' Map antenna string ant_string (e.g 0x) to correlator input index
        '''
        raise NotImplementedError

    def set_equalisation_values(self, ant_str=all, init_poly=[], init_coeffs=[], send_spead=True):
        ''' Set equalisation values for specified antenna to polynomial or coefficients specified
        '''
        raise NotImplementedError

    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        if name == 'hosts':
            tmp = {}
            tmp.update(self.fhosts)
            tmp.update(self.xhosts)
            return tmp
        elif name == 'fpga_hosts':
            tmp = {}
            for host in self.hosts.values():
                if isinstance(host, KatcpClientFpga):
                    tmp.update({host.host: host})
            return tmp       
 
#        elif name == 'fengines':
#            return self.engine_get(engine_id=None, engine_class=fengine.Fengine)
#        elif name == 'xengines':
#            return self.engine_get(engine_id=None, engine_class=xengine.Xengine)
        return object.__getattribute__(self, name)

    def calculate_integration_time(self):
        '''Calcuate the number of accumulations and integration time for this system.
        '''
        self.config['n_accs'] = self.config['acc_len'] * self.config['xeng_acc_len']
        self.config['int_time'] = float(self.config['n_chans']) * self.config['n_accs'] / self.config['bandwidth']

    def calculate_bandwidth(self):
        '''Determine the bandwidth the system is processing.
        The ADC on the running system must report how much bandwidth it is processing.
        '''
        raise NotImplementedError

    def probe_fhosts(self):
        '''Read information from the F-host hardware.
        '''
        raise NotImplementedError

    def probe_xhosts(self):
        '''Read information from the X-host hardware.
        '''
        raise NotImplementedError

    def connect(self):
        '''Connect to the correlator and test connections to all the nodes.
        '''
        return self.ping_hosts()

# end
