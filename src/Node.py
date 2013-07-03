'''
Created on Feb 28, 2013

@author: paulp
'''

import Engine

import logging
logger = logging.getLogger(__name__)

class Node(object):
    '''
    A processing node - Roach board, PC, etc. Hosts processing engines.
    '''
    def __init__(self, host, ip, katcp_port):
        '''Constructor.
        
        @param host: the unique hostname/identifier for this Node
        @param ip: the IP address for this Node.
        @param port: and its KATCP port.
        '''
        self.host = host
        self.ip = ip
        self.katcp_port = katcp_port
        self._engines = {}
    
    def initialise(self):
        """Initialise this node to its normal running state.
        """
        raise NotImplementedError
    
    def engine_add(self, engine):
        '''Add an engine to this node.
        
        @param engine: the Engine object to add to this Node.
        '''
        if not isinstance(engine, Engine.Engine):
            raise RuntimeError('Object provided is not an Engine instance.')
        if self._engines.has_key(engine.id):
            raise RuntimeError('Engine ID %s already exists on this Node.' % engine.id)
        self._engines[engine.id] = engine        

    def engine_get(self, engine_id):
        '''Get an engine from this node based on the engine id.
        
        @param engine_id: the ID of the Engine instance we want.
        @return: the engine corresponding to that ID.
        '''
        e = None
        try:
            e = self._engines[engine_id]
        except KeyError:
            logger.debug('No such engine, %s' % engine_id)
        return {engine_id: e}

# end
