# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2 import host, instrument, configuration_katcp_client
from corr2.katcp_client_fpga import KatcpClientFpga

from misc import log_runtime_error, log_not_implemented_error

class Engine(object):
    '''
    A compute engine of some kind, hosted on a Host, optionally part of an instrument. 
    Produces SPEAD data products
    '''
    def __init__(self, host_device, engine_id, host_instrument=None, config_file=None, descriptor='engine'):
        '''Constructor
        @param host_device: the device that hosts this engine
        @param engine_id: unique id for this engine type on host 
        @param host_instrument: the Instrument it is part of 
        @param config_file: configuration if engine is to be used not as part of Instrument
        @param descriptor: section in config to locate engine specific info at
        '''
        if not isinstance(descriptor, str):
            log_runtime_error(LOGGER, 'descriptor provided is not a string')

        self.descriptor = descriptor

        self.instrument = None
        if host_instrument != None:
            #if a config file is provided, get config from there, otherwise use host Instrument's
            if not isinstance(host_instrument, instrument.Instrument):
                log_runtime_error(LOGGER, 'instrument provided is not an Instrument')
            else:
                self.instrument = host_instrument

        if not isinstance(host_device, host.Host):
            log_runtime_error(LOGGER, 'host provided is not an Host')
        self.host = host_device

        if not isinstance(engine_id, int):
            log_runtime_error(LOGGER, 'engine_id provided is not an int')
        self.id = engine_id

        self.config_portal = None
        #if no config file given
        if config_file == None:
            if self.instrument == None:
                log_runtime_error(LOGGER, 'No way to get config')
            # get config from instrument it is a part of
            self.config_portal = self.instrument.config_portal
        else:
            # create new configuration portal
            self.config_portal = configuration_katcp_client.ConfigurationKatcpClient(config_file=config_file)

        self.config = {}
        self._get_engine_config()

        #TODO SPEAD
        self.spead_transmitter = None

        LOGGER.info('Initialised %s', str(self))

    def _get_engine_config(self):
        '''
        '''
        #TODO check for descriptor section in config
        if not self.ping():
            log_runtime_error(LOGGER, 'host not pingable')

        if not self.host.is_running():
            log_runtime_error(LOGGER, 'Need running host')

        host_config_file = self.config_portal.get_string(['%s'%self.descriptor, 'host_config_file']) 
        file_info = self.host.get_config_file_info()
        
        if (host_config_file.find(file_info['name']) == -1):
            #TODO check date too
            log_runtime_error(LOGGER, 'Need to be running on host with configuration file that matches config')

        # get types of data it produces
        product = self.config_portal.get_string(['%s'%self.descriptor, 'produces']) 
        self.config['data_product'] = {}        

        if product != 'Nothing':
            # find the default destination for the data it produces
            txport = self.config_portal.get_int(['%s'%product, 'txport']) 
            txip_str = self.config_portal.get_string(['%s'%product, 'txip']) 

            self.config['data_product']['name'] = '%s'%product
            self.config['data_product']['txport'] = txport
            self.config['data_product']['txip'] = txip_str

    def ping(self):
        '''Test connection to Engine Host
        '''
        return self.host.ping()

    def __str__(self):
        return '%s @ %s,%s,%i' % (self.descriptor, self.instrument, self.host, self.id)

    def set_txip(self, txip_str=None, txip=None, issue_spead=True):
        ''' Set base transmission IP for SPEAD output
        @param txip_str: IP address in string form
        @param txip: IP address as integer
        '''
        log_not_implemented_error(LOGGER, '%s.set_txip not implemented'%self.descriptor)
    
    def get_txip(self):
        log_not_implemented_error(LOGGER, '%s.get_txip not implemented'%self.descriptor)
 
    def set_txport(self, txport=None, issue_spead=True):
        ''' Set transmission port for SPEAD output
        @param txport: transmission port as integer
        '''
        log_not_implemented_error(LOGGER, '%s.set_txport not implemented'%self.descriptor)
    
    def get_txport(self):
        log_not_implemented_error(LOGGER, '%s.get_txport not implemented'%self.descriptor)
    
    def start_tx(self, product_name=all):
        ''' Start SPEAD data transmission
        '''
        log_not_implemented_error(LOGGER, '%s.start_tx not implemented'%self.descriptor)
    
    def stop_tx(self, product_name=all, issue_spead=True):
        ''' Stop SPEAD data transmission
        '''
        log_not_implemented_error(LOGGER, '%s.stop_tx not implemented'%self.descriptor)

    def set_meta_destination(self, txip_str, txport, txip=None):
        ''' Set meta destination for transmission of SPEAD meta data output
        @param txip_str: IP address in string form (takes preference)
        @param txip: IP address as integer
        @param txport: transmission port as integer
        '''
        log_not_implemented_error(LOGGER, '%s.set_txip not implemented'%self.descriptor)
    
    def add_meta_destination(self, txip_str, txip, txport):
        ''' Add a desination for SPEAD meta data output
        @param txip_str: IP address in string form (takes preference)
        @param txip: IP address as integer
        @param txport: transmission port as integer
        '''
        log_not_implemented_error(LOGGER, '%s.set_txport not implemented'%self.descriptor)

    def clear_meta_destination(self):
        ''' Clears SPEAD metadata destination list
        '''
        log_not_implemented_error(LOGGER, '%s.set_txport not implemented'%self.descriptor)

# end
