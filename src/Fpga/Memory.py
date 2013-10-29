import logging
logger = logging.getLogger(__name__)

import xml.etree.ElementTree as ET
import construct

import Types
from Bitfield import Bitfield, Field
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
                d = fnode.attrib
                self.add_field(Field(name=d['name'], numtype=d['type'], width=int(d['width']), binary_pt=int(d['binpt']), lsb_offset=int(d['lsb_offset']), value=None))

    def __str__(self):
        rv = '%s, %i * %i, %s, fields[%s]' % (self.name, self.width, self.length, Types.direction_string(self.direction), self.fields)
        return rv

    def read(self, **kwargs):
        # read the data raw
        raw = self._read_raw(**kwargs)
        if not(isinstance(raw['data'], str) or isinstance(raw['data'], buffer)):
            log_runtime_error(logger, 'self._read_raw returning incorrect datatype. Must be str or buffer.')
        #extra_value = self.control_registers['extra_value']['register'].read() if self.options['extra_value'] else None
        # and convert using the bitstruct
        repeater = construct.GreedyRange(self.bitstruct)
        parsed = repeater.parse(raw['data'])
        processed = {}
        for f in self.fields.itervalues():
            processed[f.name] = []
        for d in parsed:
            d = d.__dict__
            for f in self.fields.itervalues():
                if f.numtype == 'Unsigned':
                    val = bin2fp(d[f.name], f.width, f.binary_pt, False)
                elif f.numtype == 'Signed  (2\'s comp)':
                    val = bin2fp(d[f.name], f.width, f.binary_pt, True)
                elif f.numtype == 'Boolean':
                    val = int(d[f.name])
                else:
                    log_runtime_error(logger, 'Cannot process unknown field numtype: %s' % f.numtype)
                processed[f.name].append(val)
#         return {'data': processed, 'extra_value': extra_value}
        return {'data': processed}

    def _read_raw(self, **kwargs):
        raise RuntimeError('Must be implemented by subclass.')
    
    def write_raw(self, uintvalue):
        raise RuntimeError('Must be implemented by subclass.')
    
    def write(self, **kwargs):
        raise RuntimeError('Must be implemented by subclass.')