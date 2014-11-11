"""
@author: paulp
"""

import logging
from engine import Engine

LOGGER = logging.getLogger(__name__)


class Fengine(Engine):
    """
    A Frequency Engine.
    Channelises data from an antenna.
    """

    def __init__(self, host_device, engine_id, ant_id, config_source):
        """
        :param ant_id: antenna input identity of data being processed
        :return: <nothing>
        """

        raise NotImplementedError

        Engine.__init__(self, host_device, engine_id, config_source)
        self.ant_id = ant_id

        # check that we have all the required attributes for an f-engine
        assert hasattr(self, 'sample_bits'), 'f-engine must have the number of bits the ADC data uses'
        assert hasattr(self, 'adc_demux_factor'), 'f-engine must have the ADC demux factor (how many ADC samples' \
                                                  'we receive in parallel)'
        assert hasattr(self, 'bandwidth'), 'f-engine must have a specified bandwidth that is processed (from baseband)'
        assert hasattr(self, 'true_cf'), 'f-engine must have a specified center frequency'
        assert hasattr(self, 'n_chans'), 'f-engine must have a specified number of output channels'
        assert hasattr(self, 'min_load_time'), 'f-engine must have a minimum load time for delay tracking'
        assert hasattr(self, 'network_latency_adjust'), 'f-engine, network_latency_adjust config item missing'

    def set_delay(self, delay=0, delay_delta=0, phase=0, phase_delta=0, load_time=None):
        """ Apply delay correction coefficients to polarisation specified from time specified
        @param delay: delay in samples
        @param delay_delta: change in delay in samples per ADC sample
        @param phase: initial phase offset TODO units
        @param phase_delta: change in phase TODO units
        @param load_time: time to load values in ADC samples since epoch. If None load immediately
        """
        raise NotImplementedError

# end
