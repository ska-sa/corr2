# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

import engine

import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error, log_not_implemented_error 

class Host(object):
    '''
    A processing host - Roach board, PC, etc. Hosts processing engines and communicates via a TCP/IP network.
    '''
    def __init__(self, host, katcp_port):
        '''Constructor
        @param host: the unique hostname/identifier for this Host
        @param katcp_port: and its KATCP port.
        '''
        self.host = host
        self.katcp_port = katcp_port
        self.engines = {}

    def initialise(self):
        """Initialise this node to its normal running state.
        """
        log_not_implemented_error(LOGGER, '%s.initialise() not implemented'%host.host)

    def ping(self):
        '''All nodes must supply a ping method that returns true or false.
        @return: True or False
        '''
        log_not_implemented_error(LOGGER, '%s.ping() not implemented'%host.host)

    def add_engine(self, new_engine):
        '''Add an engine to this node.
        @param engine: the Engine object to add to this Host.
        '''
        if not isinstance(new_engine, engine.Engine):
            log_runtime_error(LOGGER, 'Object provided is not an Engine')
        if self.engines.has_key(new_engine.id):
            log_runtime_error(LOGGER, 'Engine ID %s already exists on this Host.' % new_engine.id)
        new_engine.host = self.host
        self.engines[new_engine.id] = new_engine

    def get_engine(self, engine_class, engine_id=None):
        '''Get an engine based on engine_id and engine_class. If no engine_id is passed, all engines of the given type will be returned.
        @param engine_id: the unique id of the engine to return.
        @param engine_class: the engine class to look for.
        '''
        if engine_id != None:
            engine_obj = self.engines[engine_id]
            if isinstance(engine_obj, engine_class):
                return {engine_id: engine_obj}
            else:
                log_runtime_error(LOGGER, 'Engine %i exists but is type %s not %s' % (engine_id, type(engine_obj), engine_class))
        engines = {}
        for engine_obj in self.engines.values():
            if isinstance(engine_obj, engine_class):
                engines[engine_obj.id] = engine_obj
        return engines

    def __str__(self):
        return '%s@%s' % (self.host, self.katcp_port)
# end
