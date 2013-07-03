'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

from Misc import log_runtime_error, Bitfield, Field, bin2fp
import xml.etree.ElementTree as ET
import struct
import construct

TO_PROCESSOR = 1
FROM_PROCESSOR = 0

class Register(Bitfield):
    '''
    A CASPER register on an FPGA. 
    '''
    def __init__(self, parent, name=None, direction=TO_PROCESSOR, width=32, xml_node=None):
        '''Constructor.
        '''
        if (xml_node == None) and (name == None):
            log_runtime_error(logger, 'Cannot make an entirely empty Register.')
        Bitfield.__init__(self, name=name, width=width, fields={})
        self.parent = parent
        self.direction = direction
        if xml_node != None:
            self._parse_xml(xml_node)
        logger.info('New register - %s' % self.__str__())

    def _parse_xml(self, xml_node):
        '''Parse the XML node describing a register. Versions?
        '''
        if not isinstance(xml_node, ET.Element):
            log_runtime_error(logger, 'XML design_info file %s not in correct format?' % xml_node)
        self.name = xml_node.attrib['name']
        self.width = int(xml_node.attrib['width'])
        self.direction = TO_PROCESSOR if xml_node.attrib['name'] == 'To Processor' else FROM_PROCESSOR
        field_nodes = xml_node.getchildren()
        self.fields = {}
        for fnode in field_nodes:
            if fnode.tag == 'field':
                d = fnode.attrib
                self.add_field(Field(name=d['name'], numtype=d['type'], width=int(d['width']), binary_pt=int(d['binpt']), lsb_offset=int(d['lsb_offset']), value=None))

    def __str__(self):
        rv = '%s, %i, %s, fields[%s]' % (self.name, self.width, 'TO_PROCESSOR' if self.direction == TO_PROCESSOR else 'FROM_PROCESSOR', self.fields)
        return rv

    def free_space(self):
        return self.width - self.width_used

    def _read_raw(self):
        return self.parent.read_uint(self.name)
    
    def _write_raw(self, uintvalue):
        self.parent.write_int(self.name, uintvalue)

    def read(self):
        raw = self._read_raw()
        parsed = self.bitstruct.parse(struct.pack('>I', raw))
        p = parsed.__dict__
        for f in self.fields.itervalues():
            if f.numtype == 'ufix':
                p[f.name] = bin2fp(p[f.name], f.width, f.binary_pt, False)
            elif f.numtype == 'fix':
                p[f.name] = bin2fp(p[f.name], f.width, f.binary_pt, True)
        return {'raw': raw, 'values': p}
    
    def write(self, **kwargs):
        current_values = self.read()
        pulse = {}
        for k in kwargs:
            if not current_values['values'].has_key(k):
                log_runtime_error(logger, 'Attempting to write field %s, doesn\'t exist.' % k)
            if kwargs[k] == 'pulse':
                logger.info('Pulsing field %s (%i > %i)' % (k, current_values['values'][k], not current_values['values'][k]))
                pulse[k] = current_values['values'][k]
                current_values['values'][k] = not current_values['values'][k]
            else:
                current_values['values'][k] = kwargs[k]
                logger.info('%s: writing %i to field %s' % (self.name, kwargs[k], k))
        unpacked = struct.unpack('>I', self.bitstruct.build(construct.Container(**current_values['values'])))
        self._write_raw(unpacked[0])
        if len(pulse) > 0:
            self.write(**pulse)
