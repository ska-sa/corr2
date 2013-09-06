'''
Created on Feb 28, 2013

@author: paulp
'''

import Engine

import logging
logger = logging.getLogger(__name__)

from Misc import log_runtime_error

class Node(object):
    '''
    A processing node - Roach board, PC, etc. Hosts processing engines and communicates via a TCP/IP network.
    '''
    def __init__(self, host, ip, port):
        '''Constructor
        
        @param host: the unique hostname/identifier for this Node
        @param ip: the IP address for this Node.
        @param port: and its port.
        '''
        self.host = host
        self.ip = ip
        self.port = port
        self.engines = {}
    
    def initialise(self):
        """Initialise this node to its normal running state.
        """
        raise NotImplementedError
    
    def ping(self):
        '''All nodes must supply a ping method that returns true or false.
        @return: True or False
        '''
        raise NotImplementedError
    
    def engine_add(self, engine):
        '''Add an engine to this node.
        @param engine: the Engine object to add to this Node.
        '''
        if not isinstance(engine, Engine.Engine):
            raise RuntimeError('Object provided is not an Engine.')
        if self.engines.has_key(engine.id):
            raise RuntimeError('Engine ID %s already exists on this Node.' % engine.id)
        engine.host = self.host
        self.engines[engine.id] = engine
    
    def engine_get(self, engine_id, engine_class):
        '''Get an engine based on engine_id and engine_class. If no engine_id is passed, all engines of the given type will be returned.
        @param engine_id: the unique id of the engine to return.
        @param engine_class: the engine class to look for.
        ''' 
        if engine_id != None:
            e = self.engines[engine_id]
            if isinstance(e, engine_class):
                return {engine_id: e}
            else:
                log_runtime_error('Engine %i exists but is type %s not %s' % (engine_id, type(e), engine_class))
        engines = {}
        for e in self.engines.values():
            if isinstance(e, engine_class):
                engines[e.id] = e
        return engines
    
    def __str__(self):
        return '%s@%s:%s' % (self.host, self.ip, self.port)
# end
