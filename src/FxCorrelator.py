'''
Created on Feb 28, 2013

@author: paulp
'''

import logging, iniparse

import Instrument, KatcpClientFpga, Fengine, Xengine, Types
from Misc import log_runtime_error

logger = logging.getLogger(__name__)

class FxCorrelator(Instrument.Instrument):
    '''
    An FxCorrelator implemented using FPGAs running BOF files for processing hosts.
    '''
    def __init__(self, name, description, config_file, connect):
        '''
        Constructor
        @param name: The instrument's unique name.
        @param description: A brief description of the correlator.
        @param config_file: An XML/YAML config file describing the correlator.
        @param connect: True/False, should the a connection be established to the instrument after setup.   
        '''
        super(FxCorrelator, self).__init__(name=name, description=description, config_file=config_file)

        # process config - done in Super.__init__
        
        # set up loggers
        
        # spead transmitter
        
        # connect to nodes - check katcp connections

        if connect:
            self.connect()
    
    def initialise(self):
        '''Initialise the FX correlator.
        '''
        raise NotImplementedError
    
    def check_katcp_connections(self):
        '''Ping all the nodes in this correlator to see if katcp connections are functioning.
        '''
        results = self.node_ping()
        for r in results.values():
            if not r:
                return False
        return True
    
    def __getattribute__(self, name):
        if name == 'fengines':
            return self.engine_get(engine_id=None, engine_class=Fengine.Fengine)
        elif name == 'xengines':
            return self.engine_get(engine_id=None, engine_class=Xengine.Xengine)
        return Instrument.Instrument.__getattribute__(self, name)

    def parse_config(self, filename):
        '''Parse an XML/YAML config file for this correlator.
        @param filename: The filename for the config file.
        '''
        if filename == '':
            log_runtime_error('No config file provided.')
            return
        try:
            fptr = open(filename, 'r')
        except:
            raise IOError('Configuration file \'%s\' cannot be opened.' % filename)
        self.config_file = filename
        logger.info('Using config file %s.' % self.config_file)
        config_parser = iniparse.INIConfig(fptr)
        
        # some helper functions
        def cfg_set_string(section, param, overwrite = False):
            if self.config.has_key(param) and (not overwrite):
                log_runtime_error(logger, 'Attempting to overwrite config variable \'%s\'' % param)
            try:
                self.config[param] = config_parser[section][param];
            except:
                log_runtime_error(logger, 'Config asked for unknown param - %s/%s' % (section, param))
            if isinstance(self.config[param], iniparse.config.Undefined):
                log_runtime_error(logger, 'Config asked for unknown param - %s/%s' % (section, param))
        def cfg_set_int(section, param, overwrite = False):
            cfg_set_string(section, param, overwrite)
            self.config[param] = int(self.config[param])
        def cfg_set_float(section, param, overwrite = False):
            cfg_set_string(section, param, overwrite)
            self.config[param] = float(self.config[param])
        
        # check for bof names
        cfg_set_string('files', 'bitstream_f')
        cfg_set_string('files', 'bitstream_x')
        logger.info('Using bof files F(%s) X(%s).' % (self.config['bitstream_f'], self.config['bitstream_x']))
        
        # read f and x host lists and create the basic FPGA hosts
        cfg_set_string('katcp', 'hosts_f')
        cfg_set_string('katcp', 'hosts_x')
        cfg_set_string('katcp', 'katcp_port')
        self.create_hosts()
    
        print self.config
    
    def create_hosts(self):
        '''Create the Hosts that make up this FX correlator.
        '''
        logger.info('Creating hosts.')
        if (self.config['hosts_f'] == None) or (self.config['hosts_x'] == None):
            log_runtime_error(logger, 'Must have string describing F and X nodes.')
        self.config['hosts_f'] = self.config['hosts_f'].split(Types.LISTDELIMIT)
        self.config['hosts_x'] = self.config['hosts_x'].split(Types.LISTDELIMIT)
        for h in self.config['hosts_f']:
            fhost = KatcpClientFpga.KatcpClientFpga(h, h, self.config['katcp_port'])
            self.host_add(fhost)
        
        print self.hosts
        
    def connect(self):
        '''Connect to the correlator and test connections to all the nodes.
        '''
        raise NotImplementedError

# end
