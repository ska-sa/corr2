'''
@author: andrew
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2.xengine import Xengine
from corr2.engine_fpga import EngineFpga

from corr2.fpgadevice import tengbe
from misc import log_runtime_error

class XengineFpga(EngineFpga, Xengine):
    '''
    An X-engine, resident on an FPGA
    Pre accumulation is applied to output products before longer term accumulation in vector accumulators
    '''
    def __init__(self, f_offset, host_device, engine_id, host_instrument, config_file=None, descriptor='xengine_fpga'):
        '''Constructor
        '''
        EngineFpga.__init__(self, host_device, engine_id, host_instrument, config_file, descriptor)
        Xengine.__init__(self, f_offset)
        
        self._get_xengine_fpga_config()

    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        if name == 'control':
            return self.host.device_by_name('ctrl')
        elif name == 'status':
            return self.host.device_by_name('status%i'%(self.id))
        elif name == 'acc_len':
            return self.host.device_by_name('acc_len')
        #default is to get useful stuff from ancestor
        return EngineFpga.__getattribute__(self, name)
        
    def _get_xengine_fpga_config(self):
        
        # pre accumulation length
        self.config['acc_len'] = self.config_portal.get_int(['%s' %self.descriptor, 'acc_len'])
        # default accumulation length for vector accumulator
        self.config['vacc_len'] = self.config_portal.get_int(['%s' %self.descriptor, 'vacc_len'])

    def set_vacc_len(self, vacc_len=None, issue_spead=True):
        ''' Set accumulation length for vector accumulation
        '''   
        #TODO check vacc_len
        self.acc_len.write(reg=vacc_len)

    def get_vacc_len(self):
        ''' Set accumulation length for vector accumulation
        '''   
        return self.acc_len.read()['data']['reg'] 

    def receiving_valid_data(self):
        '''The engine is receiving valid data.
        @return True or False
        '''
        #TODO
        return True

    def producing_data(self):
        ''' The engine is producing data ready for transmission
        '''
        #TODO 
        return True

# end
