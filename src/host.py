'''
Created on Feb 28, 2013

@author: paulp
'''

import engine

import logging
logger = logging.getLogger(__name__)

from misc import log_runtime_error

class Host(object):
    '''
    A processing host - Roach board, PC, etc. Hosts processing engines and communicates via a TCP/IP network.
    '''
    def __init__(self, host, ip, katcp_port):
        '''Constructor
        
        @param host: the unique hostname/identifier for this Host
        @param ip: the IP address for this Host.
        @param katcp_port: and its KATCP port.
        '''
        self.host = host
        self.ip = ip
        self.katcp_port = katcp_port
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
        @param engine: the Engine object to add to this Host.
        '''
        if not isinstance(engine, engine.Engine):
            raise RuntimeError('Object provided is not an Engine.')
        if self.engines.has_key(engine.id):
            raise RuntimeError('Engine ID %s already exists on this Host.' % engine.id)
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
        return '%s@%s:%s' % (self.host, self.ip, self.katcp_port)
# end
