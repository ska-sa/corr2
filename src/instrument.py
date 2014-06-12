# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

import hostdevice

class Instrument(object):
    '''
    An abstract base class for instruments.
    Instruments are made of Hosts.
    These Hosts host processing Engines that do work.
    '''
    def __init__(self, name, descriptor, config_file=None):
        '''Constructor for the base Instrument class.
        @param name: The name by which this instrument is identified. i.e. kat7_beamformer_test_4_ant_13_March_2013
        @param description: More info about this instrument, if needed.
        @param config_file: The location of the file that will be used to configure this instrument
        '''
        self.name = name
        self.descriptor = descriptor
        self.hosts =  {}
        self.config_file = config_file
        self.config = {}
        if config_file != None:
            self.get_config(config_file)
        LOGGER.info('Instrument %s created.', name)

    def get_config(self, config_file):
        '''Stub method - must be implemented in child class.
        '''
        raise NotImplementedError

    def initialise(self):
        """Stub method - must be implemented in child class.
        """
        raise NotImplementedError

    def add_hosts(self, hosts):
        """Add a dictionary of Host objects to the dictionary of hosts that make up this instrument.
        @param hosts: a dictionary of Host objects
        """
        for host in hosts:
            if not isinstance(host, hostdevice.Host):
                raise RuntimeError('Object provided is not a Host.')
            self.hosts.update(host):

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
    
    def get_engine(self, engine_id, engine_class):
        '''Get a specific engine based on id or all instances of an engine class.
        '''
        engines = {}
        for node in self.hosts.values():
            engines.update(node.get_engine(engine_id, engine_class))
        return engines

    def __str__(self):
        returnstr = '%s: %s\n' % (self.name, self.description)
        for node in self.hosts.itervalues():
            returnstr += '\t%s\n' % node
        return returnstr

# end
