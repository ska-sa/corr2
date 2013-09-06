'''
Created on Feb 28, 2013

@author: paulp
'''

import Instrument, Fengine, Xengine

import logging
from Misc import log_runtime_error
logger = logging.getLogger(__name__)

class FxCorrelator(Instrument.Instrument):
    '''
    An FxCorrelator.
    '''
    def __init__(self, name, description, config_file, connect):
        '''
        Constructor
        @param name: The instrument's unique name.
        @param description: A brief description of the correlator.
        @param config_file: An XML/YAML config file describing the correlator.
        @param connect: True/False, should the a connection be established to the instrument after setup.   
        '''
        super(FxCorrelator, self).__init__(name=name, description=description, config_file=config_file)

        # process config
        
        # set up loggers
        
        # spead transmitter
        
        # connect to nodes - check katcp connections

        if connect:
            self.connect()
    
    def initialise(self):
        '''Initialise the FX correlator.
        '''
        raise NotImplementedError
    
    def check_katcp_connections(self):
        '''Ping all the nodes in this correlator to see if katcp connections are functioning.
        '''
        results = self.node_ping()
        for r in results.values():
            if not r:
                return False
        return True
    
    def __getattribute__(self, name):
        if name == 'fengines':
            return self.engine_get(engine_id=None, engine_class=Fengine.Fengine)
        elif name == 'xengines':
            return self.engine_get(engine_id=None, engine_class=Xengine.Xengine)
        return Instrument.Instrument.__getattribute__(self, name)

    def parse_config(self, filename):
        '''Parse an XML/YAML config file for this correlator.
        @param filename: The filename for the config file.
        '''
        raise NotImplementedError
        if filename == '':
            log_runtime_error('No config file provided.')
            return
        try:
            open(filename, 'r')
        except:
            raise IOError('Configuration file \'%s\' cannot be opened.' % filename)
        raise NotImplementedError
        
    def connect(self):
        '''Connect to the correlator and test connections to all the nodes.
        '''
        raise NotImplementedError

# end
