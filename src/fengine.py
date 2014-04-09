# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2.engine import Engine

class Fengine(Engine):
    '''
    An F-engine, regardless of where it is located.
    '''
    def __init__(self, parent):
        '''Constructor.
        '''
        Engine.__init__(self, parent, 'f-engine')
        self.num_output_channels = -1

#        self.control_tx = (some_reg_object, some_field_name)
#
#
#        self.write_field(self.control_tx, vlaue_ti_write)
#
#        self.register.write(some_field = 1, another-field=2)
#
#
#        self.fft_shift_register = None
#        self.some_other_register = None
#        self.discover_registers()



        LOGGER.info('%i-channel Fengine created @ %s',
            self.num_output_channels, str(self.parent))

#    def discover_registers(self):
#        for registers in self.parent.registers:
#            # look for names we know
#            if(namematch):
#                self.fft_shift = (thisregister, 'reg')

#    def set_fft_shift(self, value):
#        self.fft_shift_register.write_int(value)

    def eq_get(self):
        raise NotImplementedError

    def eq_set(self):
        raise NotImplementedError
# end
