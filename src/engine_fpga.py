'''
@author: andrew
'''

import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error
from corr2.engine import Engine

from casperfpga import tengbe

import numpy, struct

class EngineFpga(Engine):
    '''
    An Engine, resident on an FPGA as part of an instrument
    '''
    def __init__(self, fpga, engine_id, host_instrument, config_file=None, descriptor='engine_fpga'):
        '''Constructor
        @param fpga: the link to the fpga that hosts this engine
        @param engine_id: unique id for this engine type on the fpga
        @param host_instrument: the Instrument it is part of 
        @param config_file: configuration if engine is to be used not as part of Instrument
        @param descriptor: section in config to locate engine specific info at
        '''
        Engine.__init__(self, fpga, engine_id, host_instrument, config_file, descriptor)
    
        self._get_engine_fpga_config()

    def _get_engine_fpga_config(self):
        ''' Configuration needed by Engines resident on FPGAs
        '''
        # if located with other engines on fpga use register prefix to differentiate between engine types
        self.tag = ''
        located_with = self.config_portal.get_string(['%s'%self.descriptor, 'located_with']) 
        tag = self.config_portal.get_string(['%s'%self.descriptor, 'tag']) 
        if located_with != 'Nothing':
            self.tag = tag 

        #if multiple of same engine on fpga, use index to discriminate between engines of same type
        self.offset = ''
        engines_per_host = self.config_portal.get_int(['%s'%self.descriptor, 'engines_per_host'])    
        if engines_per_host > 1:
            self.offset = '%s'%(str(self.id))

    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''

        # all engines on FPGAs have associated control and status registers
        # use local __getattribute__ to redefine these if not following this convention
        if name == 'control':
            return self.host.device_by_name('%scontrol%s' %(self.tag, self.offset))
        elif name == 'status':
            return self.host.device_by_name('%sstatus%s' %(self.tag, self.offset))

        # all engines by default have a single output destination (or base) ip and port
        # shared amongst all engines of the same type on a host
        # use local __getattribute__ to redefine these if not following this convention
        elif name == 'txport':
            return self.host.device_by_name('%stxport' %(self.tag))
        elif name == 'txip':
            return self.host.device_by_name('%stxip' %(self.tag))

        #default
        return object.__getattribute__(self, name)

    ################
    # Status stuff #
    ################

    def clear_status(self):
        ''' Clear status registers and counters related to this engine
        '''
        self.control.write(status_clr=True)
        self.control.write(status_clr=False)

    def clear_comms_status(self):
        ''' Clear comms status and counters related to this engine
            NOTE: may affect engines connected to the same comms medium
        '''
        self.control.write(comms_status_clr=True)
        self.control.write(comms_status_clr=False)
    
    def reset_comms(self):
        ''' Resets the communications devices related to this engine
            NOTE: may affect engines connected to the same comms medium
        '''
        self.control.write(comms_rst=True)
        self.control.write(comms_rst=False)
    
    def get_status(self):
        ''' Returns status register associated with this engine
        '''
        return self.status.read()['data']

    ###############
    #  Data input #
    ###############

    def is_receiving_valid_data(self):
        ''' Is receiving valid data
        '''
        return self.status.read()['data']['rxing_data']

    ################
    # Comms stuff  #
    ################

    def set_txip(self, txip_str=None, issue_meta=True):
        ''' Set base transmission IP for SPEAD output
        @param txip_str: IP address in string form
        '''
        if txip_str == None:
            txip = tengbe.str2ip(self.config['data_product']['txip_str'])
        else:
            txip = tengbe.str2ip(txip_str)
        
        self.txip.write(txip=txip)
   
    def get_txip(self):
        ''' Get current data transmission IP base in string form 
        '''
        txip = self.txip.read()['data']['txip']
        txip_str = tengbe.ip2str(txip)
        return txip_str

    def set_txport(self, txport=None, issue_meta=True):
        ''' Set transmission port for SPEAD output
        @param txport: transmission port as integer
        '''
        if txport == None:
            txport = self.config['data_product']['txport']
        
        self.txport.write(txport=txport)
        
        #TODO SPEAD meta data
    
    def get_txport(self):
        ''' Get transmission port for SPEAD output
        '''
        return self.txport.read()['data']['txport']

    def is_producing_valid_data(self):
        ''' Is producing valid data ready for SPEAD output
        '''
        return self.status.read()['data']['txing_data']

    def start_tx(self):
        ''' Start SPEAD data transmission
        '''
        self.control.write(comms_en=1, comms_rst=0)
 
    def stop_tx(self, issue_meta=True):
        ''' Stop SPEAD data transmission
        '''
        self.control.write(comms_en=0)
        
        #TODO SPEAD meta data

    ##########################################
    # Timed latch stuff                      #
    # TODO to be integrated as an fpgadevice #
    ##########################################

    def arm_timed_latch(self, latch_name, time=None, force=False):
        ''' Arm a timed latch. Use force=True to force even if already armed 
        @param fpga host
        @param latch_name: base name for latch
        @param time: time in adc samples since epoch
        @param force: force arm of latch that is already armed
        '''
        status = self.host.device_by_name('%s_status' %(latch_name)).read()['data']

        # get armed, arm and load counts
        armed_before = status['armed']
        arm_count_before = status['arm_count']
        load_count_before = status['load_count']

        # if not forcing it, check for already armed first
        if armed_before == True:
            if force == False:
                LOGGER.info('forcing arm of already armed timed latch %s' %latch_name)
            else:
                LOGGER.error('timed latch %s already armed, use force=True' %latch_name)
                return

        # we load immediate if not given time
        if time == None:
            self.host.device_by_name('%s_control0' %(latch_name)).write(arm=0, load_immediate=1)
            self.host.device_by_name('%s_control0' %(latch_name)).write(arm=1, load_immediate=1)
                
            LOGGER.info('Timed latch %s arm-for-immediate-loading attempt' %latch_name)
            
        else: 
            # TODO check time values
            time_samples = numpy.uint64(time)
            time_msw = numpy.uint32((time_samples & 0x0000FFFFFFFFFFFF) >> 32)
            time_lsw = numpy.uint32((time_samples & 0x00000000FFFFFFFF))
            self.host.device_by_name('%s_control' %(latch_name)).write(load_time_lsw=time_lsw)
            
            self.host.device_by_name('%s_control0' %(latch_name)).write(arm=0, load_immediate=0, load_time_msw=time_msw)
            self.host.device_by_name('%s_control0' %(latch_name)).write(arm=1, load_immediate=0, load_time_msw=time_msw)

            LOGGER.info('Timed latch %s arm-for-loading-at-time attempt' %latch_name)

        # TODO check that arm count increased as expected
        status = self.host.device_by_name('%s_status' %(latch_name)).read()['data']
        
        # get armed, arm and load counts
        armed_after = status['armed']
        arm_count_after = status['arm_count']
        load_count_after = status['load_count']
        
        # armed count did not succeed
        if arm_count_after != (arm_count_before+1):
            # TODO check time
            LOGGER.error('Timed latch %s arm count at %i instead of %i' %(latch_name, arm_count_after, (arm_count_before+1)))
        else:
            # check load count increased as expected
            if time == None: 
                if load_count_after != (load_count_before+1):
                    LOGGER.error('Timed latch %s load count at %i instead of %i' %(latch_name, load_count_after, (load_count_before+1)))
            else:
                LOGGER.info('Timed latch %s successfully armed' %(latch_name))
    
    def get_timed_latch_status(self, latch_name):
        ''' Get current state of timed latch device
        @param fpga: fpga host latch is on
        @param device: base device name
        '''
        tl_control_reg = self.host.device_by_name('%s_control'%latch_name).read()['data']
        tl_control0_reg = self.host.device_by_name('%s_control0'%latch_name).read()['data']
        tl_status_reg = self.host.device_by_name('%s_status'%latch_name).read()['data']

        status = {}
        status['armed'] = (tl_status_reg['armed'] == 1)
        status['arm_count'] = tl_status_reg['arm_count']       
        status['load_count'] = tl_status_reg['load_count']       
        status['load_time'] = (tl_control0_reg['load_time_msw'] << 32) | (tl_control_reg['load_time_lsw'])
        return status

    def _float2str(self, coeffs, n_bits, bin_pt=0, signed=True):
        ''' Convert floating point coeffs into a string with n_bits of resolution and a binary point at bin_pt 
        @param coeffs: floating point coefficients
        @param n_bits: fixed point number of bits
        @param bin_pt: binary point
        @param signed: if data should be signed
        @return: string ready for writing to BRAM
        '''
        
        if len(coeffs) == 0:
            log_runtime_error(LOGGER, 'Passing empty coeffs list')
        if bin_pt < 0:
            log_runtime_error(LOGGER, 'Binary point cannot be less than 0')
        
        step = 1/(2**bin_pt) #coefficient resolution

        if signed == True:
            min_val = -(2**(n_bits-bin_pt-1))
            max_val = -(min_val)-step
        else:
            min_val = 0
            max_val = 2**(n_bits-bin_pt)-step

        if numpy.max(coeffs) > max_val or numpy.min(coeffs) < min_val:
            log_runtime_error(LOGGER, 'Coeffs out of range')
     
        is_complex = numpy.iscomplexobj(coeffs)
        if is_complex == True:
            n_coeffs = len(coeffs)*2
            coeffs = numpy.array(coeffs, dtype = numpy.complex128)
        else:
            n_coeffs = len(coeffs) 
            coeffs = numpy.array(coeffs, dtype = numpy.float64)
     
        #compensate for fractional bits
        coeffs = (coeffs * 2**bin_pt)

        byte_order = '>' #big endian

        if n_bits == 16:
            if signed == True:
                pack_type = 'h'
            else:
                pack_type = 'H'
        else:
            log_runtime_error(LOGGER, 'Don''t know how to pack data type with %i bits' %n_bits)
        
        coeff_str = struct.pack('%s%i%s' %(byte_order, n_coeffs, pack_type), *coeffs.view(dtype=numpy.float64))
        return coeff_str

    def _str2float(self, string, n_bits, bin_pt=0, iscomplex=True, signed=True):
        ''' Unpack string according to format specified. Return array of floats 
        @param string: string as read from BRAM
        @param n_bits: resolution
        @param iscomplex: whether the data is complex
        @param bin_pt: binary point
        @param signed: whether the data is signed
        '''

        byte_order = '>' #big endian for CASPER data

        n_vals = len(string)/(n_bits/8)

        if n_bits == 16:
            if signed == True:
                pack_type = 'h'
            else:
                pack_type = 'H'
        else:
            log_runtime_error(LOGGER, 'Don''t know how to pack data type with %i bits' %n_bits)
        
        coeffs = struct.unpack('%s%i%s'%(byte_order, n_vals, pack_type), string)
        coeffs_na = numpy.array(coeffs, dtype = numpy.float64)

        coeffs = coeffs_na/(2**bin_pt) #scale by binary points 
        
        if iscomplex == True:
            #change view to 64 bit floats packed as complex 128 bit values
            coeffs = coeffs.view(dtype = numpy.complex128) 

        return coeffs 

