import logging
logger = logging.getLogger(__name__)
from Misc import log_runtime_error

class Bitfield(object):
    '''Wraps contruct's BitStruct class.
    '''
    def __init__(self, name, width, fields):
        self.name = name
        self.width = width
        self.fields = {}
        self.bitstruct = None
        if len(fields) > 0:
            self.add_fields(fields)
        logger.debug('New Bitfield - %s' % self.name)

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

    def get_field(self, fieldname):
        try:
            return self.fields[fieldname]
        except:
            return None

    def get_fields_string(self):
        fieldstring = ''
        for v in self.fields.itervalues():
            fieldstring = fieldstring + ('%s, ' % v)
        fieldstring = fieldstring[0:-2]
        return fieldstring

    def __str__(self):
        rv = self.name + '(' + str(self.width) + ',['
        rv = rv + self.get_fields_string() + '])'
        return rv

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