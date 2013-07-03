'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

from Misc import log_runtime_error, Bitfield, Field, bin2fp
from Register import Register, FROM_PROCESSOR
import construct
import xml.etree.ElementTree as ET

class Snap(Bitfield):
    '''Snap blocks are triggered blocks of RAM on FPGAs.
    '''
    def __init__(self, parent, name=None, length=-1, width=-1, circular=False, start_offset=False, extra_value=False, use_dsp48s=False,
                 storage='bram', dram_dimm=0, dram_clock=200, fields={}, extra_val=None,
                 xml_node=None):
        if (xml_node == None) and (name == None):
            log_runtime_error(logger, 'Cannot make an entirely empty Snap.')
        Bitfield.__init__(self, name=name, width=width, fields=fields)
        self.parent = parent
        self.length = length
        self.options = {'circular': circular, 'start_offset': start_offset, 'extra_value': extra_value, 'use_dsp48s': use_dsp48s}
        self.storage = {'storage': storage, 'dram_dimm': dram_dimm, 'dram_clock': dram_clock}
        self.extra_value = extra_val
        if xml_node != None:
            self._parse_xml(xml_node)
        logger.info('New snapblock - %s' % self.__str__())

    def _parse_xml(self, xml_node):
        '''Parse the XML node describing a snapblock. Versions?
        '''
        if not isinstance(xml_node, ET.Element):
            log_runtime_error(logger, 'XML design_info file %s not in correct format?' % xml_node)
        self.name = xml_node.attrib['name']
        self.width = int(xml_node.attrib['data_width'])
        self.length = pow(2,int(xml_node.attrib['nsamples']))
        self.options['circular'] = True if xml_node.attrib['circap'] == 'on' else False 
        self.options['start_offset'] = True if xml_node.attrib['offset'] == 'on' else False
        self.options['extra_value'] = True if xml_node.attrib['value'] == 'on' else False
        self.options['use_dsp48s'] = True if xml_node.attrib['use_dsp48'] == 'on' else False
        self.storage['storage'] = xml_node.attrib['storage']
        self.storage['dram_dimm'] = int(xml_node.attrib['dram_dimm'])
        self.storage['dram_clock'] = int(xml_node.attrib['dram_clock'])
        field_nodes = xml_node.getchildren()
        self.fields = {}
        extra_fields = {}
        for fnode in field_nodes:
            d = fnode.attrib
            field = Field(name=d['name'], numtype=d['type'], width=int(d['width']), binary_pt=int(d['binpt']), lsb_offset=int(d['lsb_offset']), value=None)
            if fnode.tag == 'field':
                self.add_field(field)
            elif fnode.tag == 'extra_field':
                extra_fields[field.name] = field
        # is there an extra value specified?
        self.extra_value = None
        if len(extra_fields) > 0:
            if self.options['extra_value'] == False:
                log_runtime_error(logger, 'Extra value register description provided, but not optioned in XML. XML generation in casper_xps broken?')
            self.extra_value = Register(self.parent, name=self.name + '_val', direction=FROM_PROCESSOR)
            for f in extra_fields.itervalues(): self.extra_value.add_field(field=f)
        logging.info('Done parsing XML for snap.')

    def read(self, man_trig=False, man_valid=False, wait_period=1, offset=-1, circular_capture=False, get_extra_val=False):
        #read the data
        raw = self._read_raw(man_trig, man_valid, wait_period, offset, circular_capture, get_extra_val)
        # and convert using the bitstruct
        unp_rpt = construct.GreedyRange(self.bitstruct)
        data = unp_rpt.parse(raw['data'])
        processed = []
        for d in data:
            d = d.__dict__
            for f in self.fields.itervalues():
                if f.numtype == 0:
                    d[f.name] = bin2fp(d[f.name], f.width, f.binary_pt, False)
                elif f.numtype == 1:
                    d[f.name] = bin2fp(d[f.name], f.width, f.binary_pt, True)
            processed.append(d)
            
        raise RuntimeError('extra val if supported? also compare sbram from corr to corr2 - why the brams in scratchpad regsnap reading zero or 4 values instead of one?')
            
        return processed
    
    def _read_raw(self, man_trig=False, man_valid=False, wait_period=1, offset=-1, circular_capture=False, get_extra_val=False):
        import time
        
        if offset >=0:
            self.parent.write_int(self.name + '_trig_offset', offset)
    
        self.parent.write_int(self.name + '_ctrl',(0 + (man_trig<<1) + (man_valid<<2) + (circular_capture<<3)))
        self.parent.write_int(self.name + '_ctrl',(1 + (man_trig<<1) + (man_valid<<2) + (circular_capture<<3)))

        done=False
        start_time = time.time()
        while not done and ((time.time()-start_time)<wait_period or (wait_period < 0)): 
            addr = self.parent.read_uint(self.name + '_status')
            done = not bool(addr & 0x80000000)
    
        bram_dmp = {}
        bram_dmp['data'] = []
        bram_dmp['length'] = addr & 0x7fffffff
        bram_dmp['offset'] = 0

        now_status = bool(self.parent.read_uint(self.name + '_status') & 0x80000000)
        now_addr = self.parent.read_uint(self.name + '_status') & 0x7fffffff
        if (bram_dmp['length'] != now_addr) or (bram_dmp['length'] == 0) or (now_status==True):
            #if address is still changing, then the snap block didn't finish capturing. we return empty.  
            log_runtime_error(logger, "A snap block logic error occurred. It reported capture complete but the address is either still changing, or it returned 0 bytes captured after the allotted %2.2f seconds. Addr at stop time: %i. Now: Still running :%s, addr: %i." % 
                              (wait_period,bram_dmp['length'], {True:'yes', False:'no'}[now_status], now_addr))
            bram_dmp['length']=0
            bram_dmp['offset']=0

        if circular_capture:
            bram_dmp['offset']=self.parent.read_uint(self.name + '_tr_en_cnt') - bram_dmp['length']
        else: 
            bram_dmp['offset']=0

        if bram_dmp['length'] == 0:
            bram_dmp['data'] = []
        else:
            bram_dmp['data'] = self.parent.read(self.name + '_bram', bram_dmp['length'])
    
        bram_dmp['offset'] += offset
        
        if (bram_dmp['offset']<0): 
            bram_dmp['offset']=0
    
        return bram_dmp

    def __str__(self):
        return '%s: storage(%s) dram_dimm(%i) dram_clock(%i) length(%i) width(%i) support[circular(%s) start_offset(%s) extra_value(%s) use_dsp48s(%s)] fields[%s] extra_fields[%s]' % (
                self.name, self.storage['storage'], 
                self.storage['dram_dimm'], self.storage['dram_clock'],
                self.length, self.width,
                str(self.options['circular']), str(self.options['start_offset']),
                str(self.options['extra_value']), str(self.options['use_dsp48s']),
                self.fields, 'None' if self.extra_value == None else self.extra_value)
# end