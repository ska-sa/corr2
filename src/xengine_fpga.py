'''
@author: andrew
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2.xengine import Xengine

from corr2.fpgadevice import tengbe
from misc import log_runtime_error, config_get_string, config_get_list, config_get_int, config_get_float

import numpy, struct, socket, iniparse

class XengineFpga(Xengine):
    '''
    An X-engine, resident on an FPGA
    '''
    def __init__(self, parent, engine_id, index, config_file=None, descriptor='fpga based x-engine'):
        '''Constructor.
        '''
        Xengine.__init__(self, parent, engine_id, descriptor)
        
        self.index = index

        self.get_config(config_file)
        
        base_channel = self.id*self.config['n_chans_per_x']
        LOGGER.info('Xengine created processing channels %i-%i of %i @ index %i in %s',
            base_channel, base_channel+self.config['n_chans_per_x']-1, self.config['n_chans'], self.index, str(self.parent))

    def get_config(self, filename=None):
        # if we are provided with a config file, initialise using that
        if filename != None:
            self.parse_config(filename)
        # TODO otherwise we will get our configuration in some other way 
        else:
            log_runtime_error(LOGGER, 'Configuration from config file only at the moment')

    def parse_config(self, filename):
        ''' Get configuration info by parsing file
        '''
        if filename == None:
            log_runtime_error(LOGGER, 'No config file provided.')
            return
        try:
            fptr = open(filename, 'r')
        except:
            raise IOError('Configuration file \'%s\' cannot be opened.' % filename)
        cfg_parser = iniparse.INIConfig(fptr)
         
        self.config['n_chans'] =            config_get_int(cfg_parser, 'fengine', 'n_chans')

        self.config['n_chans_per_x'] =      config_get_int(cfg_parser, 'xengine', 'n_chans_per_x')
        self.config['acc_len'] =            config_get_int(cfg_parser, 'xengine', 'acc_len')
        self.config['xeng_acc_len'] =       config_get_int(cfg_parser, 'xengine', 'xeng_acc_len')

        fptr.close()


# end
