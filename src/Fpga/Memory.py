# pylint: disable-msg=C0103
# pylint: disable-msg=C0301

import logging
logger = logging.getLogger(__name__)

import xml.etree.ElementTree as ET
import construct

import Types
from Bitfield import Bitfield
from Misc import log_runtime_error, bin2fp

class Memory(Bitfield):
    '''
    Memory on an FPGA
    '''
    def __init__(self, name, address, width, length, direction, blockpath):
        '''Constructor.
        '''
        self.name = name
        self.address = address
        if not isinstance(direction, int):
            raise RuntimeError
        self.direction = direction;
        self.length = length;
        self.blockpath = blockpath;
        self.options = {}
        Bitfield.__init__(self, name=name, width=width, fields={})
        logger.debug('New CASPER memory block - %s' % self.name)

    def update_info(self, info):
        '''Set this memory's extra information.
        '''
        log_runtime_error(logger, 'Child must implement this.')

    def update_memory(self, memory):
        '''Add information from a dictionary describing memory fields.
        '''
        self.direction = memory[memory.keys()[0]]['direction']
        if not isinstance(self.direction, int):
            self.direction = Types.direction_from_string(self.direction)
        self.address = memory[memory.keys()[0]]['address']
        self.length = int(memory[memory.keys()[0]]['length'])
        self.width = int(memory[memory.keys()[0]]['owner_width'])
        self.stride_bytes = self.width / 8;
        for field in memory.values():
            f = Field(field['name'], field['type'], int(field['width']), int(field['bin_pt']), int(field['offset']), None)
            self.add_field(f)

    def _parse_xml(self, xml_node):
        '''Parse the XML node describing a register. Versions?
        '''
        if not isinstance(xml_node, ET.Element):
            log_runtime_error(logger, 'XML design_info file %s not in correct format?' % xml_node)
        self.name = xml_node.attrib['name']
        self.width = int(xml_node.attrib['width'])
        self.direction = Types.direction_from_string(xml_node.attrib['direction'])
        self.length = int(xml_node.attrib['length'])
        self.blockpath = xml_node.attrib['path']
        self.fields = {}
        for fnode in list(xml_node):
            if fnode.tag == 'field':
                data = fnode.attrib
                self.add_field(Field(name=data['name'], numtype=data['type'], width=int(data['width']), binary_pt=int(data['binpt']), lsb_offset=int(data['lsb_offset']), value=None))

    def __str__(self):
        rv = '%s, %i * %i, %s, fields[%s]' % (self.name, self.width, self.length, Types.direction_string(self.direction), self.fields)
        return rv

    def read(self, **kwargs):
        # read the data raw
        raw = self.read_raw(**kwargs)
        if not(isinstance(raw['data'], str) or isinstance(raw['data'], buffer)):
            log_runtime_error(logger, 'self.read_raw returning incorrect datatype. Must be str or buffer.')
        #extra_value = self.control_registers['extra_value']['register'].read() if self.options['extra_value'] else None
        # and convert using the bitstruct
        repeater = construct.GreedyRange(self.bitstruct)
        parsed = repeater.parse(raw['data'])
        processed = {}
        for field in self.fields.itervalues():
            processed[field.name] = []
        for data in parsed:
            #print data
            #data = data.__dict__
            for field in self.fields.itervalues():
                if field.numtype == 'Unsigned':
                    val = bin2fp(data[field.name], field.width, field.binary_pt, False)
                elif field.numtype == 'Signed  (2\'s comp)':
                    val = bin2fp(data[field.name], field.width, field.binary_pt, True)
                elif field.numtype == 'Boolean':
                    val = int(data[field.name])
                else:
                    log_runtime_error(logger, 'Cannot process unknown field numtype: %s' % field.numtype)
                processed[field.name].append(val)
        return {'data': processed}

    def read_raw(self, **kwargs):
        raise RuntimeError('Must be implemented by subclass.')

    def write_raw(self, uintvalue):
        raise RuntimeError('Must be implemented by subclass.')

    def write(self, **kwargs):
        raise RuntimeError('Must be implemented by subclass.')
