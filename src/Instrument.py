'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

class Instrument(object):
    '''
    An instrument.
    '''
    def __init__(self, name, description = "", config_file = ""):
        '''Constructor for the base Instrument class.
        @param name: The name by which this instrument is identified. i.e. kat7_beamformer_test_4_ant_13_March_2013
        @param description: More info about this instrument, if needed.
        @param config_file: The location of the file that will be used to configure this instrument
        '''
        self.name = name
        self.description = description
        self.nodes = {}
        self.parse_config(config_file)
        print 'Instrument %s created.' % name
    
    def _initialise(self):
        """Commands to initialise the instrument.
        """
        raise NotImplementedError
    
    def initialise(self, init_nodes = True):
        """Initialise the instrument and its parts.
        @param init_nodes: initialise instrument nodes if True
        """
        self._initialise()
        if init_nodes:
            for n in self.nodes: n.initialise()
    
    def nodes_add(self, node_dict):
        """Update the node list with a given dictionary of nodes.
        """
        self.nodes.update(node_dict)
    
    def nodes_ping(self):
        rv = {}
        for k, n in self.nodes.items():
            rv[k] = n.ping()
        return rv

# end
