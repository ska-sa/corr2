'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

import Node

class Instrument(object):
    '''
    An abstract base class for instruments.
    Instruments are made of Nodes.
    These Nodes host processing Engines that do work.
    '''
    def __init__(self, name, description, config_file):
        '''Constructor for the base Instrument class.
        @param name: The name by which this instrument is identified. i.e. kat7_beamformer_test_4_ant_13_March_2013
        @param description: More info about this instrument, if needed.
        @param config_file: The location of the file that will be used to configure this instrument
        '''
        self.name = name
        self.description = description
        self.nodes = {}
        if config_file != None:
            self.parse_config(config_file)
        print 'Instrument %s created.' % name
    
    def parse_config(self):
        '''Stub method - must be implemented in child class.
        '''
        raise NotImplementedError
    
    def initialise(self):
        """Stub method - must be implemented in child class.
        """
        raise NotImplementedError
    
    def node_add(self, node):
        """Add a Node object to the dictionary of nodes that make up this instrument.
        @param node: a Node object
        """
        if not isinstance(node, Node.Node):
            raise RuntimeError('Object provided is not a Node.')
        if self.nodes.has_key(node.host):
            raise RuntimeError('Node host %s already exists on this Instrument.' % node.host)
        self.nodes[node.host] = node
    
    def node_ping(self, node_to_ping = None):
        '''Ping nodes, or a single node, if provided.
        @param node_to_ping: If None, all nodes will be pinged.
        @return: dictionary with node ids as key and ping result (True/False) as value.
        '''
        ntp = {node_to_ping: self.nodes[node_to_ping]} if (node_to_ping != None) else self.nodes.items() 
        rv = {}
        for k, n in ntp:
            rv[k] = n.ping()
        return rv

    def engine_get(self, engine_id, engine_class):
        '''Get a specific engine based on id or all instances of an engine class.
        ''' 
        engines = {}
        for n in self.nodes.values():
            engines.update(n.engine_get(engine_id, engine_class))
        return engines

    def __str__(self):
        s = '%s: %s\n' % (self.name, self.description)
        for n in self.nodes.itervalues():
            s += '\t%s\n' % n
        return s

# end
