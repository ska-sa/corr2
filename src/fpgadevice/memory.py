# pylint: disable-msg=C0103
# pylint: disable-msg=C0301

'''The base class for all things memory. More or less everything on the
FPGA is accessed by reading and writing memory addresses on the EPB/OPB
busses. Normally via KATCP.
'''

import logging
LOGGER = logging.getLogger(__name__)

import construct

import bitfield
from misc import log_runtime_error, bin2fp

class Memory(bitfield.Bitfield):
    '''
    Memory on an FPGA
    '''
    def __init__(self, name, width, length):
        '''
        @param width  In bits. i.e. a register is 32 bits wide, one long.
        '''
        self.name = name
        self.length = length
        self.block_info = {}
        bitfield.Bitfield.__init__(self, name=name, width=width, fields={})
        LOGGER.debug('New CASPER memory block - %s', self.name)

    def __str__(self):
        rv = '%s, %i * %i, fields[%s]' % (self.name, self.width,
            self.length, self.get_fields_string())
        return rv

    def read_raw(self, **kwargs):
        '''Placeholder for child classes.
        '''
        raise NotImplementedError

    def read(self, **kwargs):
        '''Read raw binary data and convert it using the bitfield description
           for this memory.
        '''
        # read the data raw, passing necessary arguments through
        raw = self.read_raw(**kwargs)
        raw = raw['data']
        if not(isinstance(raw, str) or isinstance(raw, buffer)):
            log_runtime_error(LOGGER, 'self.read_raw returning incorrect datatype. Must be str or buffer.')
        #extra_value = self.control_registers['extra_value']['register'].read() if self.options['extra_value'] else None
        # and convert using the bitstruct
        repeater = construct.GreedyRange(self.bitstruct)
        parsed = repeater.parse(raw)
        processed = {}
        for field in self.fields.itervalues():
            processed[field.name] = []
        large_unsigned_detected = False
        for data in parsed:
            for field in self.fields.itervalues():
                if field.numtype == 0:
#                    if field.width <= 32:
                    val = bin2fp(bits=data[field.name],
                         mantissa=field.width,
                         exponent=field.binary_pt,
                         signed=False)
                elif field.numtype == 1:
                    if field.width <= 32:
                        val = bin2fp(bits=data[field.name],
                             mantissa=field.width,
                             exponent=field.binary_pt,
                             signed=True)
                    else:
                        large_unsigned_detected = True
                        val = data[field.name]
                elif field.numtype == 2:
                    val = int(data[field.name])
                else:
                    log_runtime_error(LOGGER, 'Cannot process unknown field numtype: %s' % field.numtype)
                processed[field.name].append(val)
        if large_unsigned_detected:
            LOGGER.warn('Signed numbers larger than 32-bits detected! Raw values returned.')
        return processed

#==============================================================================
#     def read_raw(self, **kwargs):
#         raise RuntimeError('Must be implemented by subclass.')
#
#     def read(self, **kwargs):
#         raise RuntimeError('Must be implemented by subclass.')
#
#     def write_raw(self, uintvalue):
#         raise RuntimeError('Must be implemented by subclass.')
#
#     def write(self, **kwargs):
#         raise RuntimeError('Must be implemented by subclass.')
#==============================================================================
