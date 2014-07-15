# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Created on Feb 28, 2013

@author: paulp
"""

import logging
LOGGER = logging.getLogger(__name__)

from engine import Engine


class Host(object):
    """
    A processing host - ROACH board, PC, etc.
    Hosts processing engines and communicates via a TCP/IP network.
    """
    def __init__(self, host, katcp_port):
        """Constructor
        @param host: the unique hostname/identifier for this Host
        @param katcp_port: and its KATCP port.
        """
        self.host = host
        self.katcp_port = katcp_port
        self.engines = []

    def initialise(self):
        """Initialise this host node to its normal running state.
        """
        raise NotImplementedError('%s.initialise() not implemented' % self.host)

    def ping(self):
        """All hosts must supply a ping method that returns true or false.
        @return: True or False
        """
        raise NotImplementedError('%s.ping() not implemented' % self.host)

    def is_running(self):
        """All hosts must supply a is_running method that returns true or false.
        @return: True or False
        """
        raise NotImplementedError('%s.is_running() not implemented' % self.host)

    def add_engine(self, new_engine):
        """Add an engine to this node.
        @param engine: the Engine object to add to this Host.
        """
        if not isinstance(new_engine, Engine):
            raise TypeError('new engine is not an Engine')
        if new_engine in self.engines:
            raise ValueError('engine_id %s already on host %s' % (new_engine.engine_id, self.host))
        new_engine.host = self
        self.engines[new_engine.id] = new_engine

    def get_engine(self, engine_class, engine_id=None):
        """Get an engine based on engine_id and engine_class. If no engine_id is passed, all engines of the given type will be returned.
        @param engine_id: the unique id of the engine to return.
        @param engine_class: the engine class to look for.
        """
        if engine_id is not None:
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
