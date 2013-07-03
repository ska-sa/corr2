import logging
logger = logging.getLogger(__name__)

def log_runtime_error(logger, error_string):
    logger.error(error_string)
    raise RuntimeError(error_string)

def bin2fp(bits, m=8, e=7, signed=False):
    from numpy import int32 as numpy_signed, uint32 as numpy_unsigned
    if m > 32:
        raise RuntimeError('Unsupported fixed format: %i.%i' % (m,e))
    shift = 32 - m
    bits = bits << shift
    m = m + shift
    e = e + shift
    if signed: return float(numpy_signed(bits)) / (2**e)
    return float(numpy_unsigned(bits)) / (2**e)

class Bitfield(object):
    '''Wraps contruct's BitStruct class.
    '''
    def __init__(self, name, width, fields):
        self.name = name
        self.width = width
        self.bitstruct = None
        self.fields = {}
        if len(fields) > 0:
            self.add_fields(fields)

    def add_fields(self, fields):
        if not isinstance(fields, dict):
            log_runtime_error(logger, 'fields should be a dictionary of Field objects.')
        if len(fields) == 0:
            log_runtime_error(logger, 'Empty dictionary?')
        for f in fields.itervalues():
            self.add_field(f)

    def add_field(self, field):
        if not isinstance(field, Field):
            log_runtime_error(logger, 'Expecting Field object.')
        self.fields[field.name] = field
        self._update_bitstruct()

    def _update_bitstruct(self):
        from construct import BitStruct, Flag, BitField, Padding
        # need it msb -> lsb
        fields = sorted(self.fields.itervalues(), key=lambda x: x.offset, reverse=True)
        field_width_sum = sum(f.width for f in self.fields.itervalues())
        bs = BitStruct(self.name, Padding(self.width - field_width_sum))
        for f in fields:
            if f.width == 1:
                newfield = Flag(f.name)
            else:
                newfield = BitField(f.name, f.width)
            bs.subcon.subcons = bs.subcon.subcons + (newfield,)
        self.bitstruct = bs

    def __str__(self):
        rv = self.name + '(' + str(self.width) + ',['
        for v in self.fields.itervalues():
            rv = rv + ('%s, ' % v)
        return rv.rstrip(' ').rstrip(',') +'])'

class Field(object):
    def __init__(self, name, numtype, width, binary_pt, lsb_offset, value):
        self.name = name
        self.numtype = numtype
        self.width = width
        self.binary_pt = binary_pt
        self.offset = lsb_offset
        self.value = value
    def __str__(self):
        return '%s(%i,%i,%i,%s)' % (self.name, self.offset, self.width, self.binary_pt, self.numtype)