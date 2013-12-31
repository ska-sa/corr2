# pylint: disable-msg=C0103
# pylint: disable-msg=C0301

import logging
logger = logging.getLogger(__name__)

import construct
import struct

from Fpga import Memory
from Bitfield import Field
import Types
from Misc import log_runtime_error

class Register(Memory.Memory):
    '''A CASPER register on an FPGA.
    '''
    def __init__(self, parent, name, address=-1, width=32, direction=Types.TO_PROCESSOR, info=None):
        '''Constructor.
        '''
        Memory.Memory.__init__(self, name=name, address=address, width=width, length=1, direction=direction, blockpath='')
        self.parent = parent
        self.update_info(info)
        logger.info('New register - %s' % self)

    def __str__(self):
        returnval = '%s, %i, %s, fields[%s]' % (self.name, self.width,
            Types.direction_string(self.direction), self.get_fields_string())
        return returnval

#     def __repr__(self):
#         return '[' + self.__str__() + ']'

    def read_raw(self, **kwargs):
        data = self.parent.read(self.name, 4, 0*4)
        return {'data': data}

    def write_raw(self, data):
        self.parent.write_int(self.name, data)

    def read_uint(self, **kwargs):
        data = self.parent.read_uint(self.name)
        return data

    def write_int(self, uintvalue):
        self.parent.write_int(self.name, uintvalue)

    def write(self, **kwargs):
        # Write fields in a register, using keyword arguments
        if len(kwargs) == 0:
            logger.info('%s: no keyword args given, exiting.' % self.name)
            return
        current_values = self.read()
        if len(current_values['data'].values()[0]) > 1:
            log_runtime_error(logger, 'Registers read only one value at a time, but %i given?' % len(current_values['data'].values()[0]))
        for key, value in current_values['data'].iteritems():
            current_values['data'][key] = value[0]
        pulse = {}
        changes = False
        for k in kwargs:
            if not current_values['data'].has_key(k):
                log_runtime_error(logger, 'Attempting to write field %s, doesn\'t exist.' % k)
            if kwargs[k] == 'pulse':
                logger.debug('Pulsing field %s (%i -> %i)' % (k, current_values['data'][k], not current_values['data'][k]))
                pulse[k] = current_values['data'][k]
                current_values['data'][k] = not current_values['data'][k]
                changes = True
            elif kwargs[k] == 'toggle':
                logger.debug('Toggling field %s (%i -> %i)' % (k, current_values['data'][k], not current_values['data'][k]))
                current_values['data'][k] = not current_values['data'][k]
                changes = True
            else:
                if current_values['data'][k] == kwargs[k]:
                    break
                changes = True
                current_values['data'][k] = kwargs[k]
                logger.debug('%s: writing %i to field %s' % (self.name, kwargs[k], k))
        if changes:
            unpacked = struct.unpack('>I', self.bitstruct.build(construct.Container(**current_values['data'])))
            self.write_raw(unpacked[0])
        if len(pulse) > 0:
            self.write(**pulse)

    def update_info(self, info):
        '''Set this Register's extra information.
        '''
        self.options = info
        if self.options.has_key('name'):
            self.add_field(Field('', 'Unsigned', 32, 0, 0, None))
        else:
            numios = int(info['numios'])
            offset = 0
            for ctr in range(numios, 0, -1):
                field = Field(info['name%i'%ctr], info['arith_type%i'%ctr], int(info['bitwidth%i'%ctr]), int(info['bin_pt%i'%ctr]), offset, None)
                offset = offset + int(info['bitwidth%i' % ctr])
                self.add_field(field)

#     def _parse_xml(self, xml_node):
#         '''Parse the XML node describing a register. Versions?
#         '''
#         if not isinstance(xml_node, ET.Element):
#             log_runtime_error(logger, 'XML design_info file %s not in correct format?' % xml_node)
#         self.name = xml_node.attrib['name']
#         self.width = int(xml_node.attrib['width'])
#         self.direction = TO_PROCESSOR if xml_node.attrib['name'] == 'To Processor' else FROM_PROCESSOR
#         field_nodes = xml_node.getchildren()
#         self.fields = {}
#         for fnode in field_nodes:
#             if fnode.tag == 'field':
#                 d = fnode.attrib
#                 self.add_field(Field(name=d['name'], numtype=d['type'], width=int(d['width']), binary_pt=int(d['binpt']), lsb_offset=int(d['lsb_offset']), value=None))
