# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2 import instrument, configuration_katcp_client
from casperfpga import host

from casperfpga.katcp_client_fpga import KatcpClientFpga
from casperfpga.misc import log_runtime_error, log_not_implemented_error

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
        ''' COnfiguration info needed by all processing engines
        '''
        #TODO check for descriptor section in config
        if not self.ping():
            log_runtime_error(LOGGER, 'Host not pingable')

        if not self.host.is_running():
            log_runtime_error(LOGGER, 'Need running host')

        # check firmware running on host same as specified in configuration
        host_config_file = self.config_portal.get_string(['%s'%self.descriptor, 'host_config_file']) 
        file_info = self.host.get_config_file_info()
        if (host_config_file.find(file_info['name']) == -1):
            #TODO check date too
            log_runtime_error(LOGGER, 'Need to be running on host with configuration file matching the one specified in config')

        # get types of data it produces
        # each engine produces a single data product, other data products must be produced
        # by other engines
        product = self.config_portal.get_string(['%s'%self.descriptor, 'produces']) 
        self.config['data_product'] = {}        

        if product != 'Nothing':
            # find the default destination for the data it produces
            txport = self.config_portal.get_int(['%s'%product, 'txport']) 
            txip_str = self.config_portal.get_string(['%s'%product, 'txip']) 

            self.config['data_product']['name'] = '%s'%product
            self.config['data_product']['txport'] = txport
            self.config['data_product']['txip_str'] = txip_str

    def ping(self):
        '''Test connection to Engine Host
        '''
        return self.host.ping()

    def __str__(self):
        return '%s component of %s @ offset %i in %s' % (self.descriptor, self.instrument, self.id, self.host)

    ###########
    # status  #
    ###########

    def clear_status(self):
        ''' Clear status related to this engine
        '''
        log_not_implemented_error(LOGGER, '%s.clear_status not implemented'%self.descriptor)
    
    def get_status(self):
        ''' Get status related to this engine
        '''
        log_not_implemented_error(LOGGER, '%s.get_status not implemented'%self.descriptor)

    ###############
    #  Data input #
    ###############

    def is_receiving_valid_data(self):
        ''' Is receiving valid data
        '''
        log_not_implemented_error(LOGGER, '%s.is_receiving_valid_data not implemented'%self.descriptor)

    #####################
    # SPEAD data output #
    #####################

    def set_txip(self, txip_str=None, issue_spead=True):
        ''' Set base transmission IP for SPEAD output
        @param txip_str: IP address in string form
        '''
        log_not_implemented_error(LOGGER, '%s.set_txip not implemented'%self.descriptor)
    
    def get_txip(self):
        log_not_implemented_error(LOGGER, '%s.get_txip not implemented'%self.descriptor)
 
    def set_txport(self, txport=None, issue_meta=True):
        ''' Set transmission port for SPEAD output
        @param txport: transmission port as integer
        '''
        log_not_implemented_error(LOGGER, '%s.set_txport not implemented'%self.descriptor)
    
    def get_txport(self):
        log_not_implemented_error(LOGGER, '%s.get_txport not implemented'%self.descriptor)

    def is_producing_valid_data(self):
        ''' Is producing valid data ready for SPEAD output
        '''
        log_not_implemented_error(LOGGER, '%s.is_producing_valid_data not implemented'%self.descriptor)
    
    def start_tx(self):
        ''' Start SPEAD data transmission
        '''
        log_not_implemented_error(LOGGER, '%s.start_tx not implemented'%self.descriptor)
    
    def stop_tx(self, issue_meta=True):
        ''' Stop SPEAD data transmission
        @param issue_meta: Issue SPEAD meta data informing receivers of stopped stream
        '''
        log_not_implemented_error(LOGGER, '%s.stop_tx not implemented'%self.descriptor)

    #########################
    # SPEAD meta-data output #
    #########################

    def update_meta_destination(self, destination, txip_str, txport):
        ''' Update a destination for SPEAD meta data output. Create a new one if not yet existing
        @param destination: unique descriptor string describing destination 
        @param txip_str: IP address in string form (takes preference)
        @param txport: transmission port as integer
        '''
        log_not_implemented_error(LOGGER, '%s.update_meta_destination not implemented'%self.descriptor)

    def delete_meta_destination(self, destination=all):
        ''' Clears destination from SPEAD meta data destination list
        @param desination: unique descriptor string describing destination to be cleared from list
        '''
        log_not_implemented_error(LOGGER, '%s.delete_meta_destination not implemented'%self.descriptor)

    def issue_meta(self):
        ''' Issue SPEAD meta data to all destinations in desination list
        '''

# end
