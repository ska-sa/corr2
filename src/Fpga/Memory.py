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
        self.direction = direction;
        self.length = length;
        self.blockpath = blockpath;
        Bitfield.__init__(self, name=name, width=width, fields={})
        logger.debug('New CASPER memory block - %s' % self.name)

    def _parse_xml(self, xml_node):
        '''Parse the XML node describing a register. Versions?
        '''
        if not isinstance(xml_node, ET.Element):
            log_runtime_error(logger, 'XML design_info file %s not in correct format?' % xml_node)
        self.name = xml_node.attrib['name']
        self.width = int(xml_node.attrib['width'])
        self.direction = Types.TO_PROCESSOR if xml_node.attrib['name'] == 'To Processor' else Types.FROM_PROCESSOR
        self.length = int(xml_node.attrib['length'])
        self.blockpath = xml_node.attrib['path']
        self.fields = {}
        for fnode in list(xml_node):
            if fnode.tag == 'field':
                d = fnode.attrib
                self.add_field(Field(name=d['name'], numtype=d['type'], width=int(d['width']), binary_pt=int(d['binpt']), lsb_offset=int(d['lsb_offset']), value=None))

    def _update_from_new_coreinfo_xml(self, xml_root_node):
        if not isinstance(xml_root_node, ET.Element):
            print type(xml_root_node)
            log_runtime_error(logger, 'Supplied xml node is not an xml node Element')
        for node in list(xml_root_node):
            if node.tag == 'design_info':
                for infonode in list(node):
                    if infonode.attrib['owner'].replace('/', '_') == self.name:
                        try:
                            val = int(infonode.attrib['value']);
                        except ValueError:
                            if infonode.attrib['value'] == 'on':
                                val = True
                            elif infonode.attrib['value'] == 'off':
                                val = False
                            else:
                                val = infonode.attrib['value'];
                        self.options[infonode.attrib['param']] = val;
            elif node.tag == 'memory':
                memnodes = []
                for memnode in list(node):
                    if memnode.attrib['owner'].replace('/', '_') == self.name:
                        memnodes.append(memnode)
                if len(memnodes) <= 0:
                    raise RuntimeError('%s %s must have at least one memory node?' % (type(self), self.name))
                self.direction = memnodes[0].attrib['direction']
                self.address = memnodes[0].attrib['address']
                self.length = int(memnodes[0].attrib['length'])
                self.width = int(memnodes[0].attrib['owner_width'])
                self.stride_bytes = self.width / 8;
                for memnode in memnodes:
                    if memnode.attrib['owner'].replace('/', '_') == self.name:
                        f = Field(memnode.attrib['name'], memnode.attrib['type'], int(memnode.attrib['width']), int(memnode.attrib['bin_pt']), int(memnode.attrib['offset']), None)
                        self.add_field(f)

    def __str__(self):
        rv = '%s, %i * %i, %s, fields[%s]' % (self.name, self.width, self.length, 'TO_PROCESSOR' if self.direction == Types.TO_PROCESSOR else 'FROM_PROCESSOR', self.fields)
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