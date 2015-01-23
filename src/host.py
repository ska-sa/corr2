"""
Created on Feb 28, 2013

@author: paulp
"""
import logging

LOGGER = logging.getLogger(__name__)


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
        self.engines = {}

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
        """
        Add an compute engine to this node.
        :param new_engine:
        :return: <nothing>
        """
        if new_engine.engine_id in self.engines.keys():
            raise ValueError('engine_id %s already on host %s' % (new_engine.engine_id, self.host))
        new_engine.set_host(self)
        self.engines[new_engine.engine_id] = new_engine

    def get_engine(self, engine_id):
        """
        Get an engine based on engine_id. If no engine_id is passed, all engines will be returned.
        :param engine_id: the unique id of the engine to return.
        :return:
        """
        return self.engines[engine_id]

    def __str__(self):
        return '%s@%s' % (self.host, self.katcp_port)
# end
