# pylint: disable-msg=C0301
# pylint: disable-msg=C0103
import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error

import construct

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
        LOGGER.debug('New Bitfield - %s', self.name)

    def add_fields(self, fields):
        '''Add a dictionary of Fields to this bitfield.
        '''
        if not isinstance(fields, dict):
            log_runtime_error(LOGGER, 'fields should be a dictionary of Field objects.')
        if len(fields) == 0:
            log_runtime_error(LOGGER, 'Empty dictionary is not so useful?')
        for f in fields.itervalues():
            self.add_field(f)

    def add_field(self, newfield, auto_offset=False):
        '''Add a Field to this bitfield.
        '''
        if not isinstance(newfield, Field):
            log_runtime_error(LOGGER, 'Expecting Field object.')
        # add it at the end of the current fields
        if auto_offset:
            width = 0
            for field in self.fields.itervalues():
                width += field.width
            newfield.offset = width
        self.fields[newfield.name] = newfield
        self._update_bitstruct()

    def _update_bitstruct(self):
        '''Update this Bitfield's bitstruct after a field has been modified.
        '''
        # need it msb -> lsb
#        print 100 * '#'
        fields = sorted(self.fields.itervalues(), key=lambda x: x.offset, reverse=True)
        field_width_sum = sum(f.width for f in self.fields.itervalues())
#        print fields
#        print field_width_sum
#        print 100 * '#'
        bs = construct.BitStruct(self.name, construct.Padding(self.width - field_width_sum))
        for f in fields:
            if f.width == 1:
                newfield = construct.Flag(f.name)
            else:
                newfield = construct.BitField(f.name, f.width)
            bs.subcon.subcons = bs.subcon.subcons + (newfield,)
        self.bitstruct = bs

    def get_field(self, fieldname):
        try:
            return self.fields[fieldname]
        except KeyError:
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
    def __init__(self, name, numtype, width, binary_pt, lsb_offset):
        '''
        Initialise a field object.
        @param name  The name of the field
        @param numtype  A numerical description of the type - 0 is unsigned,
            1 is signed 2's comp and 2 is boolean
        @param width  The width of the field, in bits
        @param binary_pt  The binary point position, in bits
        @param lsb_offset  The offset in the memory field, in bits - -1 means it hasn't been set yet.
        '''
        if not isinstance(numtype, int):
            log_runtime_error(LOGGER, 'Type must be an integer.')
        self.name = name
        self.numtype = numtype
        self.width = width
        self.binary_pt = binary_pt
        self.offset = lsb_offset
    def __str__(self):
        return '%s(%i,%i,%i,%i)' % (self.name, self.offset, self.width, self.binary_pt, self.numtype)
    def __repr__(self):
        return '%s(%i,%i,%i,%i)' % (self.name, self.offset, self.width, self.binary_pt, self.numtype)
# end
