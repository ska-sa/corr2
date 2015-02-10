"""
@author: andrew
"""

import logging
import numpy
from casperfpga import tengbe
from engine import Engine

LOGGER = logging.getLogger(__name__)


class EngineCasperFpga(Engine):
    """
    An Engine, resident on a CASPER FPGA.
    """
    def __init__(self, fpga_host, engine_id, config_source):
        """
        :param fpga_host: the Casperfpga object that hosts this engine
        :param engine_id: engine number on this fpga
        :return:
        """
        """Constructor
        @param fpga_host: the link to the fpga that hosts this engine
        @param engine_id:
        @param host_instrument: the Instrument it is part of
        @param config_file: configuration if engine is to be used not as part of Instrument
        @param descriptor: section in config to locate engine specific info at
        """
        Engine.__init__(self, fpga_host, engine_id, config_source)

        assert hasattr(self, 'control_reg'), 'Engine on an fpga must have a control register.'
        assert hasattr(self, 'status_reg'), 'Engine on an fpga must have a status register'

        LOGGER.info('Casper FPGA engine created: host %s, engine_id %s', self.host, str(self.engine_id))

    def __str__(self):
        return '%s id %d @ %s' % (self.__class__.__name__, self.engine_id, self.host)

    # def _get_engine_fpga_config(self):
    #     """ Configuration needed by Engines resident on FPGAs
    #     """
    #     # if located with other engines on fpga use register prefix to differentiate between engine types
    #     self.tag = ''
    #     located_with = self.config_portal.get_string(['%s'%self.descriptor, 'located_with'])
    #     tag = self.config_portal.get_string(['%s'%self.descriptor, 'tag'])
    #     if located_with != 'Nothing':
    #         self.tag = tag
    #
    #     #if multiple of same engine on fpga, use index to discriminate between engines of same type
    #     self.offset = ''
    #     engines_per_host = self.config_portal.get_int(['%s'%self.descriptor, 'engines_per_host'])
    #     if engines_per_host > 1:
    #         self.offset = '%s'%(str(self.id))

    ################
    # Status stuff #
    ################

    def clear_status(self):
        """
        Clear status registers and counters related to this engine.
        """
        self.control_reg.write(status_clr='pulse')
    
    def get_status(self):
        """ Returns status register associated with this engine
        """
        return self.status_reg.read()['data']

    def clear_comms_status(self):
        """ Clear comms status and counters related to this engine
            NOTE: may affect engines connected to the same comms medium
        """
        self.control_reg.write(comms_status_clr='pulse')

    ###############
    #  Data input #
    ###############

    def is_receiving_valid_data(self):
        """ Is receiving valid data
        """
        return self.status_reg.read()['data']['rxing_data']

    ################
    # Comms stuff  #
    ################

    def reset_comms(self):
        """ Resets the communications devices related to this engine
            NOTE: may affect engines connected to the same comms medium
        """
        self.control_reg.write(comms_rst='pulse')

    def set_txip(self, txip_str=None, issue_meta=True):
        """ Set base transmission IP for SPEAD output
        @param txip_str: IP address in string form
        """
        if txip_str is None:
            txip = tengbe.str2ip(self.config['data_product']['txip_str'])
        else:
            txip = tengbe.str2ip(txip_str)
        self.txip.write(txip=txip)
   
    def get_txip(self):
        """
        Get current data transmission IP base in string form
        """
        txip = self.txip.read()['data']['txip']
        txip_str = tengbe.ip2str(txip)
        return txip_str

    def set_txport(self, txport=None, issue_meta=True):
        """
        Set transmission port for SPEAD output
        @param txport: transmission port as integer
        """
        if txport is None:
            txport = self.config['data_product']['txport']
        self.txport.write(txport=txport)

    def get_txport(self):
        """
        Get transmission port for SPEAD output
        """
        return self.txport.read()['data']['txport']

    def is_producing_valid_data(self):
        """
        Is producing valid data ready for SPEAD output
        """
        return self.status.read()['data']['txing_data']

    def start_tx(self):
        """
        Start SPEAD data transmission
        """
        self.control.write(comms_en=1, comms_rst=0)
 
    def stop_tx(self):
        """
        Stop SPEAD data transmission
        """
        self.control.write(comms_en=0)

    ##########################################
    # Timed latch stuff                      #
    # TODO to be integrated as an fpgadevice #
    ##########################################

    def arm_timed_latch(self, latch_name, time=None, force=False):
        """ Arm a timed latch. Use force=True to force even if already armed
        @param fpga host
        @param latch_name: base name for latch
        @param time: time in adc samples since epoch
        @param force: force arm of latch that is already armed
        """
        status = self.host.device_by_name('%s_status' %(latch_name)).read()['data']

        # get armed, arm and load counts
        armed_before = status['armed']
        arm_count_before = status['arm_count']
        load_count_before = status['load_count']

        # if not forcing it, check for already armed first
        if armed_before:
            if not force:
                LOGGER.info('forcing arm of already armed timed latch %s' %latch_name)
            else:
                LOGGER.error('timed latch %s already armed, use force=True' %latch_name)
                return

        # we load immediate if not given time
        if time is None:
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
            if time is None:
                if load_count_after != (load_count_before+1):
                    LOGGER.error('Timed latch %s load count at %i instead of %i' %(latch_name, load_count_after, (load_count_before+1)))
            else:
                LOGGER.info('Timed latch %s successfully armed' %(latch_name))
    
    def get_timed_latch_status(self, latch_name):
        """ Get current state of timed latch device
        @param fpga: fpga host latch is on
        @param device: base device name
        """
        tl_control_reg = self.host.device_by_name('%s_control'%latch_name).read()['data']
        tl_control0_reg = self.host.device_by_name('%s_control0'%latch_name).read()['data']
        tl_status_reg = self.host.device_by_name('%s_status'%latch_name).read()['data']

        status = {'armed': (tl_status_reg['armed'] == 1), 'arm_count': tl_status_reg['arm_count'],
                  'load_count': tl_status_reg['load_count'],
                  'load_time': (tl_control0_reg['load_time_msw'] << 32) | (tl_control_reg['load_time_lsw'])}
        return status


