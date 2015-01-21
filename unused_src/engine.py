"""
Created on Feb 28, 2013

@author: paulp
"""

import logging
LOGGER = logging.getLogger(__name__)


class Engine(object):
    """
    A compute engine of some kind, hosted on a Host, optionally part of an instrument.
    Takes data in, gives data out, via its host.
    Produces SPEAD data products
    """
    def __init__(self, host_device, engine_id, config_source):
        """Constructor
        @param host_device: the network-accessible device that hosts this engine
        @param engine_id: unique id for this engine type on host - number, string, something?
        """
        self.host = None
        self.engine_id = engine_id
        self.set_host(host_device)
        self.update_config(config_source)

    def set_host(self, host):
        """
        Set the parent host for this engine.
        :param host: a Host instance
        :return: <nothing>
        """
        self.host = host

    def update_config(self, config_source):
        """
        Update the configuration for this engine.
        This should be implemented by a child implementation.
        """
        raise NotImplementedError

    '''
    def _get_engine_config(self):
        """ Configuration info needed by all processing engines
        """
        raise NotImplementedError

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
    '''

    ###########
    # Status  #
    ###########

    def clear_status(self):
        """
        Clear status related to this engine.
        """
        raise NotImplementedError

    def get_status(self):
        """
        Get status related to this engine.
        """
        raise NotImplementedError

    ###############
    #  Data input #
    ###############

    def is_receiving_valid_data(self):
        """ Is receiving valid data
        """
        raise NotImplementedError

    #####################
    # SPEAD data output #
    #####################
    def set_txip(self, txip_str=None, issue_spead=True):
        """ Set base transmission IP for SPEAD output
        @param txip_str: IP address in string form
        """
        raise NotImplementedError
    
    def get_txip(self):
        raise NotImplementedError
 
    def set_txport(self, txport=None, issue_meta=True):
        """ Set transmission port for SPEAD output
        @param txport: transmission port as integer
        """
        raise NotImplementedError
    
    def get_txport(self):
        raise NotImplementedError

    def is_producing_valid_data(self):
        """ Is producing valid data ready for SPEAD output
        """
        raise NotImplementedError
    
    def start_tx(self):
        """ Start SPEAD data transmission
        """
        raise NotImplementedError
    
    def stop_tx(self, issue_meta=True):
        """ Stop SPEAD data transmission
        @param issue_meta: Issue SPEAD meta data informing receivers of stopped stream
        """
        raise NotImplementedError

    #########################
    # SPEAD meta-data output #
    #########################

    def update_meta_destination(self, destination, txip_str, txport):
        """ Update a destination for SPEAD meta data output. Create a new one if not yet existing
        @param destination: unique descriptor string describing destination
        @param txip_str: IP address in string form (takes preference)
        @param txport: transmission port as integer
        """
        raise NotImplementedError

    def delete_meta_destination(self, destination=all):
        """ Clears destination from SPEAD meta data destination list
        @param desination: unique descriptor string describing destination to be cleared from list
        """
        raise NotImplementedError

    def issue_meta(self):
        """ Issue SPEAD meta data to all destinations in desination list
        """
        raise NotImplementedError

# end
