"""
@author: andrew
"""

import logging
LOGGER = logging.getLogger(__name__)

from corr2.fengine_fpga import FengineFpga

import numpy

class WbRtsFengine(FengineFpga):
    """ A FPGA F-engine implemented for RTS
    """

    def __init__(self, ant_id, fpga, engine_id=0, host_instrument=None, config_file=None, descriptor='wb_rts_fengine'):
        """ Constructor
            @param ant_id:
            @param parent: fpga host for engine (already programed)
            @param engine_id: index within FPGA
            @param instrument: instrument it is part of
            @param descriptor: description of fengine
        """
        FengineFpga.__init__(self, ant_id, fpga, engine_id, host_instrument, config_file, descriptor)
        
        self._get_wb_rts_fengine_config()

    def _get_wb_rts_fengine_config(self):
        """
        """

    def __getattribute__(self, name):
        """Overload __getattribute__ to make shortcuts for getting object data.
        """
        if name == 'trigger_level':
            return self.host.device_by_name('trigger_level')
        if name == 'debug_status':
            return self.host.device_by_name('debug_status')
        #default
        return FengineFpga.__getattribute__(self, name)

    ########
    # TVGs #
    ########
   
    def set_tvg(self, dvalid=False, adc=False, pfb=False, corner_turner=False):
        """ turn on/off specified (default is none) tvg/s
                dvalid          : simulate enable signal from unpack block
                adc             : simulate impulse data from unpack block
                pfb             : simulate constant from PFB
                corner_turner   : simulate frequency channel label in each channel after corner turner
        """
        
        self.control.write(tvg_dvalid = dvalid, tvg_adc = adc, tvg_pfb = pfb, tvg_ct = ct)

    ##################
    # Data snapshots #
    ##################

    def get_input_data_snapshot(self, pol_index):
        """ Get snapshot of data entering this fengine
        """
        #TODO check pol_index   

        #get raw data 
        data = getattr(self, 'snap_adc%s'%pol_index).read(man_trig=True, man_valid=False)['data']   
 
        streams = len(data.values())
        length = len(data.values[0])
    
        # extract data in order and stack into rows
        # data is not ordered so can''t blindly stack
        data_stacked = numpy.vstack(data['data%i' %count] for count in range(streams))
    
        repacked = numpy.reshape(data_stacked, streams*length, 1)

        return repacked

    def get_output_data_snapshot(self, pol_index):
        """ Get snapshot of data after channelisation
        """

        #get raw data 
        data = getattr(self, 'snap_quant%s'%pol_index).read(man_trig=False, man_valid=False)['data']   
        
        streams = len(data.values())
        length = len(data.values[0])

        #extract data in order and stack into columns
        data_stacked = numpy.column_stack((numpy.array(data['real%i' %count])+1j*numpy.array(data['imag%i' %count])) for count in range(streams/2))
    
        repacked = numpy.reshape(data_stacked, (streams/2)*length, 1)

        return repacked

    ##################################################
    # Status monitoring of various system components #
    ##################################################

    # timestamp
    def get_timestamp(self):
        """ Get timestamp of data currently being processed
        """
        lsw = self.parent.device_by_name('timestamp_lsw').read()['data']['timestamp_lsw']
        msw = self.parent.device_by_name('timestamp_msw').read()['data']['timestamp_msw']
        return numpy.uint64(msw << 32) + numpy.uint64(lsw) 

    # flashy leds on front panel
    def enable_leds(self):
        """ Turn on the Knightrider effect
        """
        self.control.write(leds_en=1)
    
    def disable_leds(self):
        """ Turn off the Knightrider effect
        """
        self.control.write(leds_en=0)

    # trigger level
    def set_trigger_level(self, trigger_level):    
        """ Set the level at which data capture to snapshot is stopped
        """
        self.trigger_level.write(trigger_level=trigger_level)

    def get_trigger_level(self):    
        """ Get the level at which data capture to snapshot is stopped
        """
        return self.trigger_level.read()['data']['trigger_level']

