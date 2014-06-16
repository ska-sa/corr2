'''
@author: andrew
'''

import logging
LOGGER = logging.getLogger(__name__)

from corr2.fengine import Fengine
from corr2.fpgadevice import tengbe
from misc import log_runtime_error

import numpy, struct, socket, iniparse

class FengineFpgaWb(Fengine):
    ''' A wide band F-engine located on an FPGA host. 
        Produces channels covering a contiguous band whose center frequency is fixed
    '''

    def __init__(self, ant_id, host_device, engine_id=0, host_instrument=None, config_file=None, descriptor='fengine_fpga_wb'):
        ''' Constructor
            @param ant_id: 
            @param parent: fpga host for engine (already programed)
            @param engine_id: index within FPGA
            @param instrument: instrument it is part of
            @param descriptor: description of fengine
        '''
        Fengine.__init__(self, ant_id, host_device, engine_id, host_instrument, config_file, descriptor)


    def get_config(self, filename=None):
        # if we are provided with a config file, initialise using that
        if filename != None:
            self.parse_config(filename)
        # TODO otherwise we will get our configuration in some other way 
        else:
            log_runtime_error(LOGGER, 'Configuration from config file only at the moment')
    
    def parse_config(self, filename):
        ''' Get configuration info by parsing file
        '''
        if filename == None:
            log_runtime_error(LOGGER, 'No config file provided.')
            return
        try:
            fptr = open(filename, 'r')
        except:
            raise IOError('Configuration file \'%s\' cannot be opened.' % filename)
        cfg_parser = iniparse.INIConfig(fptr)
         
        self.config['sampling_frequency'] =         config_get_int(cfg_parser, 'dengine', 'sampling_frequency')

        # shift factor for every FFT stage
        self.config['fft_shift'] =                  config_get_int(cfg_parser, 'fengine', 'fft_shift')
        self.config['n_chans'] =                    config_get_int(cfg_parser, 'fengine', 'n_chans')
        
        # equalisation
        self.config['eq_decimation'] =              config_get_int(cfg_parser, 'equalisation', 'eq_decimation')
#        self.config['eq_coeff'] =                   config_get_list(cfg_parser, 'equalisation', 'eq_coeffs')
        self.config['eq_type'] =                    config_get_string(cfg_parser, 'equalisation', 'eq_type')
        self.config['eq_default'] =                 config_get_string(cfg_parser, 'equalisation', 'eq_default')

        # delay tracking 
        self.config['min_ld_time'] =                config_get_float(cfg_parser, 'delay_tracking', 'min_ld_time')
        self.config['network_latency_adjust'] =     config_get_float(cfg_parser, 'delay_tracking', 'network_latency_adjust')

        fptr.close()

    def initialise(self, reset=True, set_eq=True):
        ''' Initialise fengine for data processing 
        '''
        #check status
        #place in reset
        self.enable_reset()
        #clear status bits
        self.clear_status()
        #set fft shift
        self.set_fft_shift()
        #set equaliser settings pre requantization
        if set_eq == True:
            self.set_equalisation()
        
        #remove reset
        self.disable_reset()
        #check status
        status = self.get_status(debug=False)
        #TODO what do we expect to have happened at this point?
    
    ########
    # TVGs #
    ########
   
    def enable_tvg(self, dvalid=False, adc=False, pfb=False, corner_turner=False):
        ''' turn on specified (default is none) tvg/s 
                dvalid          : simulate enable signal from unpack block
                adc             : simulate impulse data from unpack block
                pfb             : simulate constant from PFB
                corner_turner   : simulate frequency channel label in each channel after corner turner
        ''' 
        
        #prepare for posedge on enable
        self.control.write(tvg_en = 0)

        if dvalid == True:
            self.control.write(tvg_dvalid = True)
        if adc == True:
            self.control.write(tvg_adc = True)
        if pfb == True:
            self.control.write(tvg_pfb = True)
        if corner_turner == True:
            self.control.write(tvg_ct = True)

        #posedge on enable 
        self.control.write(tvg_en = 1)
    
    def disable_tvg(self, dvalid=True, adc=True, pfb=True, corner_turner=True):
        ''' turn off specified (default is all) tvg/s
        '''
        
        #prepare for posedge on enable
        self.control.write(tvg_en = 0)

        if dvalid == True:
            self.control.write(tvg_dvalid = False)
        if adc == True:
            self.control.write(tvg_adc = False)
        if pfb == True:
            self.control.write(tvg_pfb = False)
        if corner_turner == True:
            self.control.write(tvg_ct = False)

        #posedge on enable 
        self.control.write(tvg_en = 1)


    ##################################################
    # Status monitoring of various system components #
    ##################################################

    def clear_status(self, comms=True, fstatus_reg=True):
        ''' Clear status registers 
        '''
        ctrl = 'control%i'%(self.index)
        
        # needs a positive edge to clear 
        if comms == True and fstatus_reg == True:
            self.parent.device_by_name(ctrl).write(status_clr=0, comms_status_clr=0)
            self.parent.device_by_name(ctrl).write(status_clr=1, comms_status_clr=1)
        elif comms == True:
            self.parent.device_by_name(ctrl).write(comms_status_clr=0)
            self.parent.device_by_name(ctrl).write(comms_status_clr=1)
        elif fstatus_reg == True:
            self.parent.device_by_name(ctrl).write(fstatus_reg=0)
            self.parent.device_by_name(ctrl).write(fstatus_reg=1)
    
    def get_status(self, rx_comms=True, timestamp=True, dsp=True, tx_comms=True, timed_latches=True, debug=True):
        ''' Status of f-engine returned in dictionary. All status returned if specific status not specified 
        '''

        status = {}
 
        if rx_comms == True:
            status['rx_comms'] = self.get_rx_comms_status(debug=debug)
        
        if timestamp == True:
            status['timestamp'] = self.get_timestamp()       
                
        if dsp == True:
            status['dsp'] = self.get_dsp_status()
        
        if tx_comms == True:
            status['tx_comms'] = self.get_tx_comms_status(debug=debug)
            
        if timed_latches == True:
            status['timed_latches'] = self.get_timed_latches_status()

        return status

    ######################################
    # Control of various system settings #
    ######################################
    
    def get_timed_latches_status(self, coarse_delay=True, fine_delay=True, tvg=True):
        ''' Get status of timed latches 
        '''

        status = {}
        if coarse_delay == True:
            status['coarse_delay'] = self.get_timed_latch_status('tl_cd%i'%(self.index))

        #if tvg == True:
        #    status['tvg'] = self.get_timed_latch_status('tl_tvg')
        
        if fine_delay == True:
            status['fine_delay'] = self.get_timed_latch_status('tl_fd%i'%(self.index))

        return status
 
    def get_dsp_status(self):
        ''' Get current state of DSP pipeline 
        '''
        
        #control
        control_reg = self.control.read()['data']
        status_reg = self.dsp_status.read()['data']
        trigger_level_reg = self.trigger_level.read()['data']
        fft_shift_reg = self.fft_shift.read()['data']

        #in reset
        control = {'reset': control_reg['dsp_rst']} 

        #status
        dsp_status = {}
        #adc overflows reported
        dsp_status['adc_over_range'] = status_reg['adc_or']
        #fft over range
        dsp_status['fft_over_range'] = status_reg['fft_or']
        #requantiser overflow
        dsp_status['equalisation_over_range'] = status_reg['quant_or']
        #qdr not ready
        dsp_status['qdr_sram_not_ready'] = status_reg['qdr_not_ready']
        #qdr calibration fail
        dsp_status['qdr_calibration_fail'] = status_reg['qdr_cal_fail']
        #qdr parity error
        dsp_status['qdr_parity_error'] = status_reg['qdr_parity_error']
   
        status = {}
        #trigger level
        status['trigger_level'] = trigger_level_reg['trigger_level']
        #fft shift
        status['fft_shift'] = fft_shift_reg['fft_shift']
        status['status'] = dsp_status
        status['control'] = control

        return status
         
    # reset
    def enable_reset(self, dsp=True, comms=True):
        ''' Place aspects of system in reset 
        '''
        if (dsp == True) and (comms == True):
            self.control.write(dsp_rst=1, comms_rst=1)
        elif (dsp == True):
            self.control.write(dsp_rst=1)
        elif (comms == True):
            self.control.write(comms_rst=1)
    
    def disable_reset(self, dsp=True, comms=True):
        ''' Remove aspects of system from reset 
        '''
        if (dsp == True) and (comms == True):
            self.control.write(dsp_rst=0, comms_rst=0)
        elif (dsp == True):
            self.control.write(dsp_rst=0)
        elif (comms == True):
            self.control.write(comms_rst=0)
   
    # timestamp
    def get_timestamp(self):
        ''' Get timestamp of data currently being processed 
        '''
        lsw = self.parent.device_by_name('timestamp_lsw').read()['data']['timestamp_lsw']
        msw = self.parent.device_by_name('timestamp_msw').read()['data']['timestamp_msw']
        return numpy.uint64(msw << 32) + numpy.uint64(lsw) 

    # flashy leds on front panel
    def enable_kitt(self):
        ''' Turn on the Knightrider effect 
        '''
        self.control.write(fancy_en=1)
    
    def disable_kitt(self):
        ''' Turn off the Knightrider effect 
        '''
        self.control.write(fancy_en=0)

    # trigger level
    def set_trigger_level(self, trigger_level):    
        ''' Set the level at which data capture to snapshot is stopped 
        '''
        self.trigger_level.write(trigger_level=trigger_level)

    def get_trigger_level(self):    
        ''' Get the level at which data capture to snapshot is stopped 
        '''
        return self.trigger_level.read()['data']['trigger_level']

    #################################
    # Delay and phase compensation  #
    #################################

    #TODO
    def set_delay(self, delay=0, delay_delta=0, phase=0, phase_delta=0, load_time=None, load_check=True):
        '''
        @param delay: delay in samples
        @param delay_delta: change in delay in samples per ADC sample 
        @param phase: initial phase offset TODO units
        @param phase_delta: change in phase TODO units
        @param load_time: time to load values in ADC samples since sync epoch. If None load immediately
        @param load_check: check that the value loaded
        '''
        raise NotImplementedError

    ##################
    # RX comms stuff #
    ##################

    def get_rx_comms_status(self, debug=True):
        ''' Get status for rx comms, debug=True gives low level core info 
        '''
        #control
        reg = self.control.read()['data']
        control = {'enabled': (reg['comms_en'] == 1), 'reset': (reg['comms_rst'] == 1)} 

        #status
        reg = self.comms_status.read()['data']

        core_info = {}
        #core info
        for gbe in self.parent.tengbes:
            core_info[gbe.name] = {}
            if debug == True:
                core_info[gbe.name]['core_details'] = gbe.get_10gbe_core_details()
                core_info[gbe.name]['counters'] = gbe.read_tx_counters()

        #TODO check that these names exist
        for index in range(4):
            gbe = {}
            #link down reported by gbe core
            gbe['link_down'] = (((reg['gbe_ldn'] >> index) & 0x1) == 1)
            #spead_unpack reported error
            #1. SPEAD header bad
            #2. SPEAD flags not received or bad
            #3. payload length not expected length
            gbe['spead_error'] = (((reg['spead_error'] >> index) & 0x1) == 1)
            #an overflow happened in the fifo buffer in the unpack/fifo block 
            #this should never happen, packets should be discarded first (see packet_discarded)
            gbe['unpack_fifo_overflow'] = (((reg['unpack_fifo_of'] >> index) & 0x1) == 1)
            #fifo block in unpack discarded packet due to one of the following;
            #1. discard line went high during packet reception
            #2. packet was not the correct multiple of words
            #3. the fifo contained the maximum packets supported and might overflow
            #4. the maximum number of words supported per packet is being exceeded
            gbe['packet_discarded'] = (((reg['packet_of'] >> index) & 0x1) == 1)
            core_info['gbe%i' %index]['status'] = gbe                

        status = {}
        #this polarisation is missing data
        status['missing_data'] = (reg['recvd_error'] == 1)
        #one of the polarisations is missing
        status['data_streams_misaligned'] = (reg['misaligned'] == 1)
        #data count does not align with timestamp changes expected
        status['timestamp_error'] = (reg['timestamp_error'] == 1)
        #timestamp received by unpack/pkt_reorder block not in range allowed
        status['timestamp_unlocked'] = (reg['mcnt_no_lock'] == 1)

        rx_status = {}
        rx_status['core_info'] = core_info
        rx_status['control'] = control
        rx_status['status'] = status
      
        return rx_status

    ##################
    # TX comms stuff #
    ##################

    def get_tx_comms_status(self, debug=True):
        ''' Get status of tx comms, debug=True gives low level core info 
        '''

        #status
        reg = self.comms_status.read()['data']
        status = {} 

        core_info = {}
        #core info
        for gbe in self.parent.tengbes:
            core_info[gbe.name] = {}
            if debug == True:
                core_info[gbe.name]['core_details'] = gbe.get_10gbe_core_details()
                core_info[gbe.name]['counters'] = gbe.read_tx_counters()

        #TODO check that these names exist
        for index in range(4):
            gbe = {}
            #link down reported by gbe core
            gbe['link_down'] = (((reg['gbe_ldn'] >> index) & 0x1) == 1)
            #TX FIFO overflowed (a reset of the gbe core is required)
            gbe['gbe_fifo_overflow'] = (((reg['gbe_of'] >> index) & 0x1) == 1)
            #spead_pack detected error
            #1. payload length is not as expected
            gbe['spead_error'] = (((reg['pack_of'] >> index) & 0x1) == 1)
            core_info['gbe%i' %index]['status'] = gbe

        #control
        reg = self.control.read()['data']
        control = {'enabled': (reg['comms_en'] == 1), 'reset': (reg['comms_rst'] == 1)} 
 
        tx_status = {}        
        #base ip and port
        tx_status['base_port'] = self.get_txport()
        tx_status['base_ip'] = self.get_txip_str()

        tx_status['core_info'] = core_info
        tx_status['control'] = control
        tx_status['status'] = status

        return tx_status
 
    # base data transmission UDP port 
    def set_txport(self, txport=None):
        ''' Set data transmission port 
        '''    
        if txport == None:
            txport = self.config['txport']
        
        self.txport.write(port_gbe=txport)

        #TODO spead stuff

    def get_txport(self):
        ''' Get data transmission port 
        '''    
        txport = self.txport.read()['data']['port_gbe']
        return txport

    # data transmission UDP IP address 
    def set_txip(self, txip_str=None, txip=None):
        ''' Set data transmission IP base 
        '''    
        if txip_str == None and txip == None:
            txip = struct.unpack('>L',socket.inet_aton(self.config['txip_str']))[0]
        elif txip == None:
            txip = struct.unpack('>L',socket.inet_aton(txip_str))[0]
        
        #TODO spead stuff
        self.txip.write(ip_gbe=txip)
    
    def get_txip(self):
        ''' Get current data transmission IP base 
        '''
        txip = self.txip.read()['data']['ip_gbe']
        return txip
    
    def get_txip_str(self):
        ''' Get current data transmission IP base in string form 
        '''
        txip = self.txip.read()['data']['ip_gbe']
        txip_str = tengbe.ip2str(txip)
        return txip_str

    def reset_tx_comms(self):
        ''' Place all communications logic in reset 
        '''
        self.enable_reset(comms=True)
   
    def config_tx_comms(self, reset=True):
        ''' Configure transmission infrastructure 
        ''' 
        if reset == True:
            self.disable_tx_comms()
            self.reset_tx_comms()   
    
    def enable_tx_comms(self):
        ''' Enable communications transmission. Comms for both fengines need to be enabled for data to flow 
        '''
        self.control.write(comms_en=1, comms_rst=0)
    
    def disable_tx_comms(self):
        ''' Disable communications transmission. Comms for both fengines need to be enabled for data to flow 
        '''
        self.control.write(comms_en=1)
 
    def start_tx(self):
        ''' Start data transmission 
        '''
        self.enable_tx_comms()
 
    def stop_tx(self):
        ''' Stop data transmission 
        '''
        self.disable_tx_comms()

    def __getattribute__(self, name):
        '''Overload __getattribute__ to make shortcuts for getting object data.
        '''
        if name == 'control':
            return self.parent.device_by_name('control%i'%(self.index))
        elif name == 'comms_status':
            return self.parent.device_by_name('comms_status%i'%(self.index))
        elif name == 'dsp_status':
            return self.parent.device_by_name('dsp_status%i'%(self.index))
        elif name == 'fft_shift':
            return self.parent.device_by_name('fft_shift')
        elif name == 'txip':
            return self.parent.device_by_name('txip')
        elif name == 'txport':
            return self.parent.device_by_name('txport')
        elif name == 'snap_quant':
            return self.parent.device_by_name('snap_quant%i_ss'%(self.index))
        elif name == 'adc_quant':
            return self.parent.device_by_name('adc_quant%i_ss'%(self.index))
        elif name == 'trigger_level':
            return self.parent.device_by_name('trigger_level')
        #default
        return object.__getattribute__(self, name)


