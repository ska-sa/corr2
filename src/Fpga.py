# Classes associated with an FPGA
import logging
logger = logging.getLogger(__name__)

import xml.etree.ElementTree as ElementTree
import construct, struct, numpy

from Misc import log_runtime_error, bin2fp
from Bitfield import Bitfield, Field
import xml.etree.ElementTree as ET
import Types

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
        if not isinstance(xml_root_node, ElementTree.Element):
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

class Register(Memory):
    '''
    A CASPER register on an FPGA. 
    '''
    def __init__(self, parent, name=None, address=-1, width=32, direction=Types.TO_PROCESSOR, xml_node=None):
        '''Constructor.
        '''
        if (xml_node == None) and (name == None):
            log_runtime_error(logger, 'Cannot make an entirely empty Register.')
        self.parent = parent
        Memory.__init__(self, name=name, address=address, width=width, length=1, direction=direction, blockpath='')
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

class Snap(Memory):
    '''Snap blocks are triggered blocks of RAM on FPGAs.
    '''
    def __init__(self, parent, name=None, address=-1, length=-1, width=-1, circular=False, start_offset=False, use_dsp48s=False,
                 storage='bram', dram_dimm=0, dram_clock=200, fields={}, extra_value=None, xml_node=None):
        if (xml_node == None) and (name == None):
            log_runtime_error(logger, 'Cannot make an entirely empty Snap.')
        self.parent = parent
        self.options = {'circular_capture': circular, 'start_offset': start_offset, 'extra_value': (False if extra_value == None else True),
                        'use_dsp48': use_dsp48s, 'storage': storage, 'dram_dimm': dram_dimm, 'dram_clock': dram_clock,
                        'length': 0 if length <= 0 else numpy.log2(length), 'data_width': width}
        Memory.__init__(self, name=name, address=address, width=width, length=1, direction=Types.FROM_PROCESSOR, blockpath='')
        if xml_node != None:
            self._parse_xml(xml_node)
        self.control_registers = {}
        self.control_registers['control'] = {'register': None, 'name': self.name + '_ctrl'}
        self.control_registers['status'] = {'register': None, 'name': self.name + '_status'}
        self.control_registers['trig_offset'] = {'register': None, 'name': self.name + '_trig_offset'}
        self.control_registers['extra_value'] = {'register': None, 'name': self.name + '_val'}
        self.control_registers['tr_en_cnt'] = {'register': None, 'name': self.name + '_tr_en_cnt'}
        self._update_extra_value_register(extra_register=extra_value)
        logger.info('New snapblock - %s' % self)

    def _arm(self, man_trig=False, man_valid=False, offset=-1, circular_capture=False):
        if offset >= 0:
            self.control_registers['trig_offset']['register'].write_int(offset)
        self.control_registers['control']['register'].write_int((0 + (man_trig << 1) + (man_valid << 2) + (circular_capture << 3)))
        self.control_registers['control']['register'].write_int((1 + (man_trig << 1) + (man_valid << 2) + (circular_capture << 3)))
    
    def _read_raw(self, man_trig=False, man_valid=False, wait_period=1, offset=-1, circular_capture=False, get_extra_val=False, arm=True):
        import time
        # trigger
        if arm: self._arm(man_trig=man_trig, man_valid=man_valid, offset=offset, circular_capture=circular_capture)
        # wait
        done = False
        start_time = time.time()
        while not done and ((time.time() - start_time) < wait_period or (wait_period < 0)): 
            addr = self.control_registers['status']['register'].read_uint()
            done = not bool(addr & 0x80000000)
    
        bram_dmp = {}
        bram_dmp['data'] = []
        bram_dmp['length'] = addr & 0x7fffffff
        bram_dmp['offset'] = 0

        status_val = self.control_registers['status']['register'].read_uint()
        now_status = bool(status_val & 0x80000000)
        now_addr = status_val & 0x7fffffff
        if (bram_dmp['length'] != now_addr) or (bram_dmp['length'] == 0) or (now_status == True):
            # if address is still changing, then the snap block didn't finish capturing. we return empty.  
            log_runtime_error(logger, "A snap block logic error occurred. It reported capture complete but the address is either still changing, or it returned 0 bytes captured after the allotted %2.2f seconds. Addr at stop time: %i. Now: Still running :%s, addr: %i." % 
                              (wait_period, bram_dmp['length'], 'yes' if now_status else 'no', now_addr))
            bram_dmp['length'] = 0
            bram_dmp['offset'] = 0

        if circular_capture:
            val = self.control_registers['tr_en_cnt']['register'].read_uint()
            bram_dmp['offset'] = val - bram_dmp['length']
        else: 
            bram_dmp['offset'] = 0

        if bram_dmp['length'] == 0:
            bram_dmp['data'] = []
        else:
            bram_dmp['data'] = self.parent.read(self.name + '_bram', bram_dmp['length'])
    
        bram_dmp['offset'] += offset
        
        if (bram_dmp['offset'] < 0): 
            bram_dmp['offset'] = 0
    
        if bram_dmp['length'] != self.length * (self.width / 8):
            log_runtime_error(logger, '%s.read_uint() - expected %i bytes, got %i' % (self.name, self.length, bram_dmp['length'] / (self.width / 8)))    
        return bram_dmp

    def __str__(self):
        return '%s: storage(%s) dram_dimm(%i) dram_clock(%i) length(%i) width(%i) support[circular(%s) start_offset(%s) extra_value(%s) use_dsp48s(%s)] fields[%s] extra_fields[%s]' % (
                self.name, self.options['storage'],
                self.options['dram_dimm'], self.options['dram_clock'],
                self.length, self.width,
                str(self.options['circular_capture']), str(self.options['start_offset']),
                str(self.options['extra_value']), str(self.options['use_dsp48']),
                self.get_fields_string(), 'None' if self.options['extra_value'] == None else self.control_registers['extra_value']['name'])

#     def __repr__(self):
#         return '[' + self.__str__() + ']'

    def _update_extra_value_register(self, extra_register):
        if extra_register != None:
            if not isinstance(extra_register, Register.Register):
                log_runtime_error(logger, 'extra_value can only be a Register.Register.')
            if extra_register.name != self.control_registers['extra_value']['name']:
                log_runtime_error(logger, 'extra_value register %s does not use naming etiquette - should be %s' % (extra_register.name, self.control_registers['extra_value']['name']))
            self.control_registers['extra_value']['register'] = extra_register
        else:
            logging.info('Updating snapshot %s extra_value register with None - are you sure that is what you want?' % self.name)

    def _parse_xml(self, xml_node):
        raise NotImplementedError

    def _update_control_registers(self, available_registers):
        # This is based on snap and register names unfortunately.
        # The proper XML description doesn't need this farkelry.
        for reg in available_registers.iterkeys():
            for ctrl_reg in self.control_registers.itervalues():
                if reg == ctrl_reg['name']:
                    ctrl_reg['register'] = available_registers[reg]
                    break
        if (self.control_registers['control']['register'] == None) or (self.control_registers['status']['register'] == None):
            log_runtime_error(logger, 'Snapshot blocks need at least internal control and status registers.')
        if self.options['extra_value'] and (self.control_registers['extra_value']['register'] == None):
            log_runtime_error(logger, 'Extra value option specified for snapshot %s, but no matching register found.' % self.name)


#     def _parse_xml(self, xml_node):
#         '''Parse the XML node describing a snapblock. Versions?
#         '''
#         if not isinstance(xml_node, ET.Element):
#             log_runtime_error(logger, 'XML design_info file %s not in correct format?' % xml_node)
#         self.name = xml_node.attrib['name']
#         self.width = int(xml_node.attrib['data_width'])
#         self.length = pow(2,int(xml_node.attrib['nsamples']))
#         self.options['circular'] = True if xml_node.attrib['circap'] == 'on' else False 
#         self.options['start_offset'] = True if xml_node.attrib['offset'] == 'on' else False
#         self.options['extra_value'] = True if xml_node.attrib['value'] == 'on' else False
#         self.options['use_dsp48s'] = True if xml_node.attrib['use_dsp48'] == 'on' else False
#         self.storage['storage'] = xml_node.attrib['storage']
#         self.storage['dram_dimm'] = int(xml_node.attrib['dram_dimm'])
#         self.storage['dram_clock'] = int(xml_node.attrib['dram_clock'])
#         field_nodes = xml_node.getchildren()
#         self.fields = {}
#         extra_fields = {}
#         for fnode in field_nodes:
#             d = fnode.attrib
#             field = Field(name=d['name'], numtype=d['type'], width=int(d['width']), binary_pt=int(d['binpt']), lsb_offset=int(d['lsb_offset']), value=None)
#             if fnode.tag == 'field':
#                 self.add_field(field)
#             elif fnode.tag == 'extra_field':
#                 extra_fields[field.name] = field
#         # is there an extra value specified?
#         self.extra_value = None
#         if len(extra_fields) > 0:
#             if self.options['extra_value'] == False:
#                 log_runtime_error(logger, 'Extra value register description provided, but not optioned in XML. XML generation in casper_xps broken?')
#             self.extra_value = Register(self.parent, name=self.name + '_val', direction=FROM_PROCESSOR)
#             for f in extra_fields.itervalues(): self.extra_value.add_field(field=f)
#         logging.info('Done parsing XML for snap.')

class Sbram(Memory):
    # General SBRAM memory on the FPGA.
    def __init__(self):
        raise NotImplementedError

# end
