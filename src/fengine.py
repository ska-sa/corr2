# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
@author: paulp
"""

import logging
LOGGER = logging.getLogger(__name__)

from corr2.engine import Engine

import numpy

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
#    if (arm_count != load_count) and (force is False):
#        # waiting for previous arm to complete
#        if ((arm_count - load_count) == 1):
#            #TODO error
#        # otherwise something bad has happened
#        else:
#            #TODO different error

    # we load immediate if not given time
    if time is None:
        self.parent.device_by_name('%s_control0' %(latch_name)).write(arm=0)
        self.parent.device_by_name('%s_control0' %(latch_name)).write(arm=1, load_immediate=1)
    else: 
        # TODO time conversion
        time_samples = 0
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
        if info is None:
            #TODO determine n_chans from system info
            self.config = { 'n_chans': 0, 
                            'fft_shift': 0,
                            'sampling_frequency': 1700000000,
                            'feng_id': 0,
                            'board_id': 0,
                            'txport': 0,
                            'txip_str': '192.168.0.0'}
            
            self.config['equalisation'] = {}
            self.config['equalisation']['decimation'] = 1
            #TODO determine some equalisation factors from system info
            self.config['equalisation']['coeffs'] = []
            self.config['equalisation']['poly'] = 1
            self.config['equalisation']['type'] = 'complex'
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
        if (dsp is True) and (comms is True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(dsp_rst=1, comms_rst=1)
        elif (dsp is True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(dsp_rst=1)
        elif (comms is True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(comms_rst=1)
    
    #
    def disable_reset(self, dsp=True, comms=True):
        """ Remove aspects of system from reset """
        if (dsp is True) and (comms is True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(dsp_rst=0, comms_rst=0)
        elif (dsp is True):
            self.parent.device_by_name('control%i'%(self.config['feng_id'])).write(dsp_rst=0)
        elif (comms is True):
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

    def get_eq(self):
        """ Get current equalisation values applied pre-quantisation """
        raise NotImplementedError

    def set_eq(self, init_coeffs=None, init_poly=None):
        """ Set equalisation values to be applied pre-quantisation """
        raise NotImplementedError

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
        if txport is None:
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
        if txip_str is None and txip is None:
            txip = self.config['txip']
            txip_str = self.config['txip_str']
        elif txip is None:
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
        if reset is True:
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
