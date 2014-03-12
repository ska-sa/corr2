# pylint: disable-msg=C0103
# pylint: disable-msg=C0301

import logging
LOGGER = logging.getLogger(__name__)

import construct, struct

import memory
import corr2.bitfield as bitfield
from corr2.misc import log_runtime_error

class Register(memory.Memory):
    '''A CASPER register on an FPGA.
    '''
    def __init__(self, parent, name, width=32, info=None, auto_update=False):
        '''Constructor.
        '''
        memory.Memory.__init__(self, name=name, width=width, length=1)
        self.parent = parent
        self.process_info(info)
        self.auto_update = auto_update
        self.last_values = {}
        self.block_info = info
        LOGGER.info('New register - %s', self)

    def __str__(self):
        if self.auto_update:
            self.read()
        vstr = ''
        for k, v in self.last_values:
            vstr = vstr + '%s(%d)' % (k, v)
        return '%s, %i, %s' % (self.name, self.width, vstr)

#     def __repr__(self):
#         return '[' + self.__str__() + ']'

    def post_create_update(self, raw_device_info):
        '''Update the Register with information not available at creation.
        '''
        return

    def read(self, **kwargs):
        '''Memory.read returns a list for all bitfields, so just put those
        values into single values.'''
        results = memory.Memory.read(self, **kwargs)
        for k, v in results.iteritems():
            results[k] = v[0]
        self.last_values = results
        return results

    def read_raw(self, **kwargs):
        # size in bytes
        data = self.parent.read(device_name=self.name, size=4, offset=0*4)
        return {'data': data}

    def write_raw(self, data):
        self.parent.write_int(self.name, data)

    def read_uint(self, **kwargs):
        data = self.parent.read_uint(self.name, **kwargs)
        return data

    def write_int(self, uintvalue, blindwrite=False, offset=0):
        '''Write an unsigned integer to this device using the fpga client.
        '''
        self.parent.write_int(device_name=self.name, integer=uintvalue, blindwrite=blindwrite, offset=offset)

    def write(self, **kwargs):
        # Write fields in a register, using keyword arguments
        if len(kwargs) == 0:
            LOGGER.info('%s: no keyword args given, exiting.', self.name)
            return
        current_values = self.read()
#        for key, value in current_values.iteritems():
#            current_values[key] = value
        pulse = {}
        changes = False
        for k in kwargs:
            if not current_values.has_key(k):
                log_runtime_error(LOGGER, 'Attempting to write field %s, doesn\'t exist.' % k)
            if kwargs[k] == 'pulse':
                LOGGER.debug('Pulsing field %s (%i -> %i)', k, current_values[k], not current_values[k])
                pulse[k] = current_values[k]
                current_values[k] = not current_values[k]
                changes = True
            elif kwargs[k] == 'toggle':
                LOGGER.debug('Toggling field %s (%i -> %i)', k, current_values[k], not current_values[k])
                current_values[k] = not current_values[k]
                changes = True
            else:
                if current_values[k] == kwargs[k]:
                    break
                changes = True
                current_values[k] = kwargs[k]
                LOGGER.debug('%s: writing %i to field %s', self.name, kwargs[k], k)
        if changes:
            unpacked = struct.unpack('>I', self.bitstruct.build(construct.Container(**current_values)))[0]
            self.write_raw(unpacked)
        if len(pulse) > 0:
            self.write(**pulse)

    def process_info(self, info):
        '''Set this Register's extra information.
        '''
        self.block_info = info
        self.fields = {}
        if self.block_info.has_key('name'):
            # oldest
            LOGGER.warn('Old registers are deprecated!')
            self.add_field(bitfield.Field('', 0, 32, 0, 0))
        elif self.block_info.has_key('numios'):
            # aborted tabbed one
            LOGGER.warn('Tabbed registers are deprecated!')
            numios = int(info['numios'])
            for ctr in range(numios, 0, -1):
                if info['arith_type%i'%ctr] == 'Boolean':
                    atype = 2
                elif info['arith_type%i'%ctr] == 'Unsigned':
                    atype = 0
                else:
                    atype = 1
                field = bitfield.Field(info['name%i'%ctr], atype,
                    int(info['bitwidth%i'%ctr]), int(info['bin_pt%i'%ctr]), -1)
                self.add_field(field, auto_offset=True)
        elif self.block_info.has_key('mode'):
            # current one
            def clean_fields(fstr):
                return fstr.replace('[', '').replace(']', '').rstrip().lstrip().split(' ')
            field_names = clean_fields(info['names'])
            field_widths = clean_fields(info['bitwidths'])
            field_types = clean_fields(info['arith_types'])
            field_bin_pts = clean_fields(info['bin_pts'])
            field_names.reverse()
            field_widths.reverse()
            field_types.reverse()
            field_bin_pts.reverse()
            if (self.block_info['mode'] == 'fields of equal size') and (len(field_widths) == 1):
                for ctr in range(1, len(field_names)):
                    field_widths.append(field_widths[0])
                    field_types.append(field_types[0])
                    field_bin_pts.append(field_bin_pts[0])
            for ctr, name in enumerate(field_names):
                field = bitfield.Field(name, int(field_types[ctr]), \
                    int(field_widths[ctr]), int(field_bin_pts[ctr]), -1)
                self.add_field(field, auto_offset=True)
        else:
            raise RuntimeError('Unknown Register type.')
