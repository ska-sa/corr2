import logging
logger = logging.getLogger(__name__)

import struct

import Memory, Types
from Misc import log_runtime_error

class Register(Memory.Memory):
    '''
    A CASPER register on an FPGA. 
    '''
    def __init__(self, parent, name=None, address=-1, width=32, direction=Types.TO_PROCESSOR, xml_node=None):
        '''Constructor.
        '''
        if (xml_node == None) and (name == None):
            log_runtime_error(logger, 'Cannot make an entirely empty Register.')
        self.parent = parent
        Memory.Memory.__init__(self, name=name, address=address, width=width, length=1, direction=direction, blockpath='')
        if xml_node != None:
            self._parse_xml(xml_node)
        logger.info('New register - %s' % self.__str__())

    def __str__(self):
        rv = '%s, %i, %s, fields[%s]' % (self.name, self.width, 'TO_PROCESSOR' if self.direction == Types.TO_PROCESSOR else 'FROM_PROCESSOR', self.get_fields_string())
        return rv
    
#     def __repr__(self):
#         return '[' + self.__str__() + ']'

    def free_space(self):
        return self.width - self.width_used

    def _read_raw(self, **kwargs):
        data = self.parent.read(self.name, 4, 0*4)
        #data = self.parent.read_uint(self.name)
        return {'data': data}
    
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
        for k,v in current_values['data'].iteritems():
            current_values['data'][k] = v[0];
        pulse = {}
        changes = False
        for k in kwargs:
            if not current_values['data'].has_key(k):
                log_runtime_error(logger, 'Attempting to write field %s, doesn\'t exist.' % k)
            if kwargs[k] == 'pulse':
                logger.info('Pulsing field %s (%i -> %i)' % (k, current_values['data'][k], not current_values['data'][k]))
                pulse[k] = current_values['data'][k]
                current_values['data'][k] = not current_values['data'][k]
            else:
                if current_values['data'][k] == kwargs[k]:
                    break
                changes = True 
                current_values['data'][k] = kwargs[k]
                logger.info('%s: writing %i to field %s' % (self.name, kwargs[k], k))
        if changes:
            unpacked = struct.unpack('>I', self.bitstruct.build(construct.Container(**current_values['data'])))
            self.write_raw(unpacked[0])
        if len(pulse) > 0:
            self.write(**pulse)

    def _parse_xml(self, xml_node):
        raise NotImplementedError
    
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
