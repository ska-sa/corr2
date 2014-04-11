# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
@author: paulp
"""

import logging
LOGGER = logging.getLogger(__name__)

from corr2.engine import Engine

class Fengine(Engine):
    """ An F-engine, regardless of where it is located """

    #TODO make part of separate class
    def setup_timed_register(self)
        """ Arm a timed register """
        raise NotImplementedError

    #TODO put in try block/s to detect bad info dictionary
    def init_config(self, info=None):
    """ initialise config dictionary from info """
        #defaults if no info passed
        if info == None:
            #TODO determine n_chans from system info
            self.config = { 'n_chans': 0, 
                            'fft_shift': 0,
                            'sampling_frequency': 1700000000,
                            'feng_id': 0}
            #TODO determine equalisation['decimation'] from system info
                            
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
            
            #TODO
            #equalisation settings
            #self.config['equalisation'] = {}
            #number of channels each value applied to
            #self.config['equalisation']['decimation'] = info['equalisation']['decimation']
            #list of complex values
            #self.config['equalisation']['coeffs'] = info['equalisation']['coeffs']
            #'complex' or 'real'
            #self.config['equalisation']['type'] = info['equalisation']['type']
            #default form, 'poly' or 'coeffs'
            #self.config['equalisation']['default'] = info['equalisation']['default']

    def __init__(self, parent, info=None):
        """ Constructor """
        Engine.__init__(self, parent, 'f-engine')
        
        #set up configuration related to this f-engine
        self.init_config(self, info)
        
        LOGGER.info('%i-channel Fengine created @ %s',
            self.config['n_chans'], str(self.parent))

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
        """ Status of f-engine """
        raise NotImplementedError

    def clear_status(self):
        """ Clear flags and counters of fengine indicating status """
        raise NotImplementedError

    ######################################
    # Control of various system settings #
    ######################################

    def set_fft_shift(self, fft_shift=None):
        """ Set current FFT shift schedule """    
        if fft_shift == None:
            fft_shift = self.config['fft_shift']
        else:
            self.config['fft_shift'] = fft_shift
        self.parent.write_int('fft_shift%i' %(self.config['feng_id']), fft_shift) 

    def get_fft_shift(self):
        """ Get current FFT shift schedule """
        fft_shift = self.parent.read_uint('fft_shift%i' %(self.config['feng_id'])
        self.config['fft_shift'] = fft_shift
        return fft_shift
    
    def get_board_id(self):
        """ Get engine ID """
        board_id = self.parent.registers.board_id.read()['data']['reg']
        self.config['board_id'] = board_id
        return board_id
    
    def set_board_id(self, board_id=None):
        """ Set engine ID """
        if board_id == None:
            board_id = self.config['board_id']
        else:
            self.config['board_id'] = board_id
 
    def reset(self):
        """ Place system in reset """
        self.parent.registers.control.write(sys_rst=1)
    
    def clear_reset(self):
        """ Release system from reset """
        self.parent.registers.control.write(sys_rst=0)

    #TODO change register names
    def get_timestamp(self):
        """ Get timestamp of data currently being processed """
        lsw = self.parent.registers.timestamp_lsw.read()['data']['timestamp']
        msw = self.parent.registers.timestamp_msw.read()['data']['timestamp']
        return (msw << 32) + lsw 

    def enable_kitt(self):
        """ Turn on the Knightrider effect """
        self.parent.registers.control.write(fancy_en=1)

    def disable_kitt(self):
        """ Turn off the Knightrider effect """
        self.parent.registers.control.write(fancy_en=0)

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

    ############
    # TX stuff #
    ############

    def config_tx(self, reset=True, issue_spead=True):
        """ Configure transmission infrastructure """    
        raise NotImplementedError
 
    #TODO SPEAD stuff
    def start_tx(self, issue_spead=True):
        """ Start data transmission """    
        self.parent.registers.control.write(gbe_enable=1, gbe_reset=0)   
 
    def stop_tx(self, reset=False):
        """ Stop data transmission """    
        if reset:
            self.parent.registers.control.write(gbe_reset=1, gbe_enable=0)   
        else:
            self.parent.registers.control.write(gbe_enable=0)   

    ################   
    # SPEAD stuff ##
    ################
 
    #TODO 
    def issue_spead(self):
        """ Issue SPEAD meta data """  
        raise NotImplementedError

# end
