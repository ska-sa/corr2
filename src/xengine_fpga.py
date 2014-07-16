"""
@author: andrew
"""

import logging
import numpy
from xengine import Xengine
from engine_fpga import EngineCasperFpga

LOGGER = logging.getLogger(__name__)


class XengineCasperFpga(Xengine, EngineCasperFpga):
    """
    An X-engine, resident on an FPGA
    Pre accumulation is applied to output products before longer term accumulation in vector accumulators
    """
    def __init__(self, fpga_host, engine_id, config_source):
        """ Constructor
        @param fpga: fpga host the xengine is resident on
        @param engine_id: offset within FPGA xengine resides at
        @param host_instrument: instrument the engine is a part of, used to get configuration info
        @param config_file: name of file if engine not part of instrument
        @param descriptor: name of FPGA xengine type. Used to locate configuration information
        """
        Xengine.__init__(self, fpga_host, engine_id, config_source)
        EngineCasperFpga.__init__(self, fpga_host, engine_id, config_source)

        LOGGER.info('%s %s initialised', self.__class__.__name__, str(self))

    def update_config(self, config_source):
        """
        Update necessary values from a config dictionary/server
        :return:
        """
        self.acc_len = int(config_source['xengine']['accumulation_len'])

    # def __getattribute__(self, name):
    #     """ Overload __getattribute__ to make shortcuts for getting object data.
    #     """
    #     if name == 'control':
    #         return self.host.device_by_name('ctrl')
    #     elif name == 'status':
    #         return self.host.device_by_name('status%i'%(self.id))
    #     elif name == 'vacc_len':
    #         return self.host.device_by_name('acc_len')
    #     #default is to get useful stuff from ancestor
    #     return EngineFpga.__getattribute__(self, name)

    def set_accumulation_length(self, accumulation_length=None, issue_meta=True):
        """ Set the accumulation time for the vector accumulator
        @param accumulation_length: the accumulation time in spectra. If None default used.
        @param issue_meta: issue SPEAD meta data indicating the change in time
        @returns: the actual accumulation time in seconds
        """
        if not isinstance(accumulation_length, int):
            LOGGER.error('accumulation length %d must be an integer number of spectra' %accumulation_length)
            raise ValueError('accumulation length %d must be an integer number of spectra' %accumulation_length)

        if accumulation_length is None:
            accumulation_length=self.config['vacc_len']
        
        acc_len = self.config['acc_len']
        # figure out how many pre-accumulated spectra this is (rounding up)
        vacc_len = numpy.ceil(float(accumulation_length)/float(acc_len))
        self.vacc_len.write(reg=vacc_len)

        return vacc_len*acc_len

    def get_accumulation_length(self):
        """ Get the current accumulation time of the vector accumulator
        @returns: the accumulation time in spectra
        """
        acc_len = self.config['acc_len']
        vacc_len = self.vacc_len.read()['data']['reg'] 
        return vacc_len * acc_len

# end
