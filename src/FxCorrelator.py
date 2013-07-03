'''
Created on Feb 28, 2013

@author: paulp
'''

import Instrument

import logging
logger = logging.getLogger(__name__)

class FxCorrelator(Instrument.Instrument):
    '''
    An FxCorrelator.
    '''
    def __init__(self, name, description = "", config_file = "", connect = False):
        '''
        Constructor
        '''
        super(FxCorrelator, self).__init__(name, description)
        
        # dictionaries to hold the nodes that make up this instrument
        self.fnodes = {}
        self.xnodes = {}
        
        # deal with the config file
        self.parse_config(config_file)
        
        # connect to all the hosts
        if connect: self.connect()
    
    
    def parse_config(self, filename):
        '''Parse a config file for this instrument.
        @param file_name: The filename for the config file.
        '''
        if filename == '': return
        try:
            open(filename, 'r')
        except:
            raise IOError('Config file %s cannot be opened.' % filename)
        import ConfigParser
        cfg = ConfigParser.ConfigParser()
        cfg.read(filename)
        self.config = cfg
        raise NotImplementedError
        
    def connect(self):
        '''nothing yet
        '''
        raise NotImplementedError

# end
