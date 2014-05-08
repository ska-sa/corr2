# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
@author: paulp
"""

import logging
LOGGER = logging.getLogger(__name__)

from corr2.engine import Engine

import numpy, struct

def ip2str(ip):
    """ Returns IP address in human readable string notation """

    ip_uint32 = numpy.uint32(ip)
    txip_str = '%i.%i.%i.%i' %(((ip_uint32&0xff000000)>>24),((ip_uint32&0x00ff0000)>>16),((ip_uint32&0x0000ff00)>>8),(ip_uint32&0x000000ff))
    return txip_str

#TODO make part of separate class
def arm_timed_latch(self, latch_name, time=None, force=False):
    """ Arm a timed register """
    
    # get the current arm and load count
    arm_count = self.parent.device_by_name('%s_status' %(latch_name)).read()['data']['arm_count']
    load_count = self.parent.device_by_name('%s_status' %(latch_name)).read()['data']['load_count']

#    # check for counter weirdness
#    if (arm_count != load_count) and (force == False):
#        # waiting for previous arm to complete
#        if ((arm_count - load_count) == 1):
#            #TODO error
#        # otherwise something bad has happened
#        else:
#            #TODO different error

    # we load immediate if not given time
    if time == None:
        self.parent.device_by_name('%s_control0' %(latch_name)).write(arm=0)
        self.parent.device_by_name('%s_control0' %(latch_name)).write(arm=1, load_immediate=1)
    else: 
        # TODO time conversion
        time_samples = numpy.uint32(0)
        time_msw = (time_samples & 0xFFFF0000) >> 32
        time_lsw = (time_samples & 0x0000FFFF)
        
        self.parent.device_by_name('%s_control' %(latch_name)).write(arm=0)
        self.parent.device_by_name('%s_control' %(latch_name)).write(arm=1, load_immediate=1)

    #TODO check that arm count increased as expected
    #TODO check that load count increased as expected if immediate

class Fengine(Engine):
    """ An F-engine, regardless of where it is located """

    #################
    # fengine setup #
    #################
    
    #TODO put in try block/s to detect bad info dictionary
    def init_config(self, info=None):
        """ initialise config from info """
        #defaults if no info passed
        if info == None:
            #TODO determine n_chans from system info
            self.config = { 'n_chans': 4096, 
                            'fft_shift': 0,
                            'sampling_frequency': 1700000000,
                            'feng_id': 0,
                            'board_id': 0,
                            'txport': 0,
                            'txip_str': '192.168.0.0'}
            
            #TODO determine some equalisation factors from system info
            self.config['equalisation'] = {}
            self.config['equalisation']['decimation'] = 1
            self.config['equalisation']['coeffs'] = []
            self.config['equalisation']['poly'] = [1]
            self.config['equalisation']['type'] = 'complex'
            self.config['equalisation']['n_bytes'] = 2      #number of bytes per coefficient
            self.config['equalisation']['bin_pt'] = 1       #location of binary point/number of fractional bits
            self.config['equalisation']['default'] = 'poly'
                            
        else:
            self.config = {}
            #number of channels post PFB
            self.config['n_chans'] = info['n_chans']         

            #shift factor for every FFT stage
            self.config['fft_shift'] = info['fft_shift'] 
            #scale factor applied to timestamp to get time in ms
            #self.config['mcnt_scale_factor'] = info['mcnt_scale_factor']
            #sampling frequency in Hz
            self.config['sampling_frequency'] = info['sampling_frequency']
            #feng on board 
            self.config['feng_id'] = info['feng_id']
            #board id
            self.config['board_id'] = info['board_id']
            
            self.config['txport'] = info['txport']
            txip_str = info['txip_str']
            self.config['txip_str'] = txip_str
            self.config['txip'] = struct.unpack('>L',socket.inet_aton(txip_str))[0]
            
            #equalisation settings
            self.config['equalisation'] = {}
            #number of channels each value applied to
            self.config['equalisation']['decimation'] = info['equalisation']['decimation']
            #list of complex values
            self.config['equalisation']['coeffs'] = info['equalisation']['coeffs']
            #'complex' or 'real'
            self.config['equalisation']['type'] = info['equalisation']['type']
            #default form, 'poly' or 'coeffs'
            self.config['equalisation']['default'] = info['equalisation']['default']

    def __init__(self, parent, info=None):
        """ Constructor """
        Engine.__init__(self, parent, 'f-engine')
        
        #set up configuration related to this f-engine
        self.init_config(info)
        
        LOGGER.info('%i-channel Fengine created with id %i @ %s',
            self.config['n_chans'], self.config['feng_id'], str(self.parent))

    def setup(self, reset=True, set_eq=True, send_spead=True):
        """ Configure fengine for data processing """

        #check status
        #place in reset
        #clear status bits
        #calibrate qdr sram    
        #set fft shift
        #set engine id used to tag data
        #set equaliser settings pre requantization
        #configure comms settings
        #send SPEAD meta data
        #remove reset
        #check status

        raise NotImplementedError

    def calibrate(self, qdr=True):
        """ Run software calibration """
        raise NotImplementedError

    ##################################################
    # Status monitoring of various system components #
    ##################################################

    def get_status(self):
        """ Status of f-engine return in dictionary """
        raise NotImplementedError

    def clear_status(self):
        """ Clear flags and counters of fengine indicating status """
        raise NotImplementedError

    ######################################
    # Control of various system settings #
    ######################################
    
    #
    # fft shift
    def set_fft_shift(self, fft_shift=None):
        """ Set current FFT shift schedule """    
        if fft_shift == None:
            fft_shift = self.config['fft_shift']
        else:
            self.config['fft_shift'] = fft_shift
        self.parent.device_by_name('fft_shift').write(fft_shift=fft_shift)
    
    #
    def get_fft_shift(self):
        """ Get current FFT shift schedule """
        fft_shift = self.parent.device_by_name('fft_shift').read()['data']['fft_shift']
        self.config['fft_shift'] = fft_shift
        return fft_shift
   
    # 
    # board id
    def get_board_id(self):
        """ Get board ID """
        board_id = self.parent.device_by_name('board_id').read()['data']['board_id']
        self.config['board_id'] = board_id
        return board_id
   
    # 
    def set_board_id(self, board_id=None):
        """ Set board ID """
        if board_id == None:
            board_id = self.config['board_id']
        else:
            self.config['board_id'] = board_id
        self.parent.device_by_name('board_id').write(board_id=board_id)
    
    # 
    # engine id
    def get_engine_id(self):
        """ Get engine ID """
        return self.config['feng_id']
   
    # 
    def set_engine_id(self, engine_id):
        """ Set engine ID """
        self.config['feng_id'] = engine_id

    # 
    # reset
    def enable_reset(self, dsp=True, comms=True):
        """ Place aspects of system in reset """
        if (dsp == True) and (comms == True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(dsp_rst=1, comms_rst=1)
        elif (dsp == True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(dsp_rst=1)
        elif (comms == True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(comms_rst=1)
    
    #
    def disable_reset(self, dsp=True, comms=True):
        """ Remove aspects of system from reset """
        if (dsp == True) and (comms == True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(dsp_rst=0, comms_rst=0)
        elif (dsp == True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(dsp_rst=0)
        elif (comms == True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(comms_rst=0)

    #
    # status
    def clear_status(self, comms=True, fstatus_reg=True):
        """ Clear status registers """
        # needs a positive edge to clear 
        if comms == True and fstatus_reg == True:
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(status_clr=0, comms_status_clr=0)
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(status_clr=1, comms_status_clr=1)
        elif comms == True:
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(comms_status_clr=0)
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(comms_status_clr=1)
        elif fstatus_reg == True:
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(fstatus_reg=0)
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(fstatus_reg=1)
   
    # 
    # timestamp
    def get_timestamp(self):
        """ Get timestamp of data currently being processed """
        lsw = self.parent.device_by_name('timestamp_lsw').read()['data']['timestamp_lsw']
        msw = self.parent.device_by_name('timestamp_msw').read()['data']['timestamp_msw']
        return numpy.uint32(msw << 32) + numpy.uint32(lsw) 

    #
    # flashy leds on front panel
    def enable_kitt(self):
        """ Turn on the Knightrider effect """
        self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(fancy_en=1)
    
    # 
    def disable_kitt(self):
        """ Turn off the Knightrider effect """
        self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(fancy_en=0)

    #
    # trigger level
    def set_trigger_level(self, trigger_level):    
        """ Set the level at which data capture to snapshot is stopped """
        self.parent.device_by_name('trigger_level').write(trigger_level=trigger_level)

    #
    def get_trigger_level(self):    
        """ Get the level at which data capture to snapshot is stopped """
        return self.parent.device_by_name('trigger_level').read()['data']['trigger_level']

    ##############################################
    # Equalisation before re-quantisation stuff  #
    ##############################################

    #
    def pack_eq(self, coeffs, n_bits, bin_pt=0, signed=True):
        """ Convert coeffs into a string with n_bits of resolution and a binary point at bin_pt """
        
        if len(coeffs) == 0:
            raise RuntimeError('Passing empty coeffs list')
        if bin_pt < 0:
            raise RuntimeError('Binary point cannot be less than 0')
        
        step = 1/(2**bin_pt) #coefficient resolution

        if signed == True:
            min_val = -(2**(n_bits-bin_pt-1))
            max_val = -(min_val)-step
        else:
            min_val = 0
            max_val = 2**(n_bits-bin_pt)-step

        if numpy.max(coeffs) > max_val or numpy.min(coeffs) < min_val:
            raise RuntimeError('Coeffs out of range')
     
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
            raise RuntimeError('Don''t know how to pack data type with %i bits' %n_bits)
        
        coeff_str = struct.pack('%s%i%s' %(byte_order, n_coeffs, pack_type), *coeffs.view(dtype=numpy.float64))
        return coeff_str

    #
    def unpack_eq(self, string, n_bits, eq_complex=True, bin_pt=0, signed=True):
        """ Unpack string according to format specified. Return array of floats """

        byte_order = '>' #big endian

        n_vals = len(string)/(n_bits/8)

        if n_bits == 16:
            if signed == True:
                pack_type = 'h'
            else:
                pack_type = 'H'
        else:
            raise RuntimeError('Don''t know how to pack data type with %i bits' %n_bits)
        
        coeffs = struct.unpack('%s%i%s'%(byte_order, n_vals, pack_type), string)
        coeffs_na = numpy.array(coeffs, dtype = numpy.float64)

        coeffs = coeffs_na/(2**bin_pt) #scale by binary points 
        
        if eq_complex == True:
            #change view to 64 bit floats packed as complex 128 bit values
            coeffs = coeffs.view(dtype = numpy.complex128) 

        return coeffs 

    #
    def get_eq(self):
        """ Get current equalisation values applied pre-quantisation """
        
        register_name='eq%i'%(self.config['feng_id'])
        n_chans = self.config['n_chans']
        decimation = self.config['equalisation']['decimation']
        n_coeffs = n_chans/decimation

        eq_type = self.config['equalisation']['type']
        if eq_type == 'complex':
            n_coeffs = n_coeffs*2

        n_bytes = self.config['equalisation']['n_bytes']
        bin_pt = self.config['equalisation']['bin_pt']

        #read raw bytes
        coeffs_raw = self.parent.read(register_name, n_coeffs*n_bytes)

        if eq_type == 'complex':
            eq_complex = True
        else:
            eq_complex = False

        coeffs = self.unpack_eq(coeffs_raw, n_bytes*8, eq_complex, bin_pt, signed=True)        

        #pad coeffs out by decimation factor
        coeffs_padded = numpy.reshape(numpy.tile(coeffs, [decimation, 1]), [1, n_chans], 'F')
    
        return coeffs_padded[0]
    
    # 
    def get_default_eq(self):
        """ Get default equalisation settings """
        
        decimation = self.config['equalisation']['decimation']
        n_chans = self.config['n_chans']       
        n_coeffs = n_chans/decimation
        eq_default = self.config['equalisation']['default']

        if eq_default == 'coeffs':
            equalisation = self.config['equalisation']['coeffs']
        elif eq_default == 'poly':
            poly = self.config['equalisation']['poly']
            equalisation = numpy.polyval(poly, range(n_chans))[decimation/2::decimation]
            if self.config['equalisation']['type'] == 'complex':
                equalisation = [eq+0*1j for eq in equalisation]
        else:
            raise RuntimeError("Your EQ type, %s, is not understood." % eq_default)

        if len(equalisation) != n_coeffs:
            raise RuntimeError("Something's wrong. I have %i eq coefficients when I should have %i." % (len(equalisation), n_coeffs))
        return equalisation

    # 
    def set_eq(self, init_coeffs=[], init_poly=[]):
        """ Set equalisation values to be applied pre-quantisation """

        n_chans = self.config['n_chans']
        decimation = self.config['equalisation']['decimation']
        n_coeffs = n_chans / decimation

        if init_coeffs == [] and init_poly == []:
            coeffs = self.get_default_eq()
        elif len(init_coeffs) == n_coeffs:
            coeffs = init_coeffs
        elif len(init_coeffs) == n_chans:
            coeffs = init_coeffs[0::decimation]
            LOGGER.warn("You specified %i EQ coefficients but your system only supports %i actual values. Only writing every %ith value."%(n_chans ,n_coeffs, decimation))
        elif len(init_coeffs) > 0:
            raise RuntimeError ('You specified %i coefficients, but there are %i EQ coefficients in this design.'%(len(init_coeffs), n_coeffs))
        else:
            coeffs = numpy.polyval(init_poly, range(n_chans))[decimation/2::decimation]

        eq_type = self.config['equalisation']['type'] 
        if eq_type == 'scalar':
            coeffs = numpy.real(coeffs)
        elif eq_type == 'complex':
            coeffs = numpy.complex64(coeffs)
        else:
            raise RuntimeError ('Don''t know what to do with %s equalisation type.'%eq_type)

        n_bytes = self.config['equalisation']['n_bytes'] 
        bin_pt = self.config['equalisation']['bin_pt'] 

        coeffs_str = self.pack_eq(coeffs, n_bits=n_bytes*8, bin_pt=bin_pt, signed=True) 

        # finally write to the bram
        self.parent.write('eq%i'%self.config['feng_id'], coeffs_str)

    #################################
    # Delay and phase compensation  #
    #################################

    #TODO
    def set_delay(self, ant_str, delay=0, delay_delta=0, phase=0, phase_delta=0, load_time=None, load_check=True, extra_wait_time = 0):
        raise NotImplementedError

    ##################
    # TX comms stuff #
    ##################
 
    # 
    # data transmission UDP port 
    def set_txport(self, txport=None, issue_spead=False):
        """ Set data transmission port """    
        if txport == None:
            txport = self.config['txport']
        
        self.config['txport'] = txport
        self.parent.device_by_name('txport').write(port_gbe=txport)

    #
    def get_txport(self):
        """ Get data transmission port """    
        txport = self.parent.device_by_name('txport').read()['data']['port_gbe']
        self.config['txport'] = txport 
        return txport

    #
    # data transmission UDP IP address 
    def set_txip(self, txip_str=None, txip=None, issue_spead=False):
        """ Set data transmission IP base """    
        if txip_str == None and txip == None:
            txip = self.config['txip']
            txip_str = self.config['txip_str']
        elif txip == None:
            self.config['txip_str'] = txip_str
            txip = struct.unpack('>L',socket.inet_aton(txip_str))[0]
            self.config['txip'] = txip
        else:
            self.config['txip_str'] = ip2str(txip)
            self.config['txip'] = txip
        
        #TODO spead stuff

        self.parent.device_by_name('txip').write(ip_gbe=txip)
    
    #
    def get_txip(self):
        """ Get current data transmission IP base """
        txip = self.parent.device_by_name('txip').read()['data']['ip_gbe']
        self.config['txip'] = txip 
        self.config['txip_str'] = ip2str(txip)
        return txip
    
    # 
    def get_txip_str(self):
        """ Get current data transmission IP base in string form """
        txip = self.parent.device_by_name('txip').read()['data']['ip_gbe']
        self.config['txip'] = txip 
        txip_str = ip2str(txip)
        self.config['txip_str'] = txip_str
        return txip_str

    #
    def reset_tx_comms(self):
        """ Place all communications logic in reset """
        self.enable_reset(comms=True)
   
    #
    #TODO SPEAD stuff
    def config_tx_comms(self, reset=True, issue_spead=True):
        """ Configure transmission infrastructure """ 
        if reset == True:
            self.disable_tx_comms()
            self.reset_tx_comms()   
    #
    def enable_tx_comms(self):
        """ Enable communications transmission. Comms for both fengines need to be enabled for data to flow """
        self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(comms_en=1, comms_rst=0)
    
    #
    def disable_tx_comms(self):
        """ Disable communications transmission. Comms for both fengines need to be enabled for data to flow """
        self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(comms_en=1)
 
    #
    #TODO SPEAD stuff
    def start_tx(self, issue_spead=True):
        """ Start data transmission """    
        self.enable_tx_comms()
 
    #
    def stop_tx(self, issue_spead=True):
        """ Stop data transmission """    
        self.disable_tx_comms()

    ################   
    # SPEAD stuff ##
    ################
 
    #TODO 
    def issue_spead(self):
        """ Issue SPEAD meta data """  
        raise NotImplementedError

# end
