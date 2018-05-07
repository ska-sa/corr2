"""
A BHost is an extension of an XHost. It contains memory and registers
to set up and control one or more beamformers.

Author: Jason Manley, Andrew Martens, Ruby van Rooyen, Monika Obrocka
"""

import logging
import time

from xhost_fpga import FpgaXHost
from casperfpga.CasperLogHandlers import CasperConsoleHandler

LOGGER = logging.getLogger(__name__)


class FpgaBHost(FpgaXHost):
    def __init__(self, host, index, katcp_port=7147, bitstream=None,
                 connect=True, config=None, **kwargs):
        # parent constructor
        FpgaXHost.__init__(self, host, index, katcp_port=katcp_port,
                           bitstream=bitstream, connect=connect, config=config, **kwargs)
        try:
            descriptor = kwargs['descriptor']
        except KeyError:
            descriptor = 'InstrumentName'
        logger_name = '{}_bhost-{}-{}'.format(descriptor, str(index), host)
        self.logger = logging.getLogger(logger_name)
        console_handler_name = '{}_stream'.format(logger_name)
        console_handler = CasperConsoleHandler(name=console_handler_name)
        self.logger.addHandler(console_handler)
        self.logger.setLevel(logging.ERROR)
        infomsg = 'Successfully created logger for {}'.format(logger_name)
        self.logger.info(infomsg)

        self.beng_per_host = self.x_per_fpga

    # @classmethod
    # def from_config_source(cls, hostname, index, katcp_port,
    #                        config_source, corr):
    #     bitstream = config_source['bitstream']
    #     return cls(hostname, index, katcp_port=katcp_port,
    #                bitstream=bitstream, connect=True, config=config_source)

    def beam_destination_set(self, beam):
        """
        Set the data destination for this beam.
        :param beam: The Beam() on which to act
        :return
        """
        
        self.registers['bf%i_config' % beam.index].write(port=beam.destination.port)
        self.registers['bf%i_ip' % beam.index].write(ip=int(beam.destination.ip_address))
        LOGGER.debug('%s:%i: Beam %i:%s destination set to %s' % (
            self.host, self.index, beam.index, beam.name,
            beam.destination))

    def beam_weights_set(self, beam_index, weights):
        """
        Set the beam weights for the given beam and given input labels.
        :param beam_index: The integer offset of the beam on this board.
        :param weights: a list of the weights to set on each input.
        """
        assert len(weights) == self.n_ants, ('Incorrect number of weights supplied (%i; need %i)'%(len(weights),self.n_ants))
        for source_index,source_weight in enumerate(weights):
            self.registers.bf_weight.write(weight=source_weight,
                    stream=beam_index, antenna=source_index, load_now='pulse')
            LOGGER.debug(
                    '%s:%i: Beam %i: set antenna(%i) weight(%.5f)'
                    '' % (self.host, self.index, beam_index,
                          source_index, source_weight))

    def beam_weights_get(self, beam_index):
        """
        Get the beam weights for the given beam_index (offset on this board).
        Returns a list of weights.
        """
        rv=[0 for a in range(self.n_ants)]
        for source_index in range(self.n_ants):
            self.registers.bf_weight.write(weight=0,
                    stream=beam_index, antenna=source_index, load_now=0)
            rv[source_index] = self.registers.bf_valout_bw0.read()['data']['bw0']
        return rv

    def beam_quant_gains_set(self, beam_index, new_gain):
        """
        Set the beam quantiser gains for the given beam on the host.
        :param beam_index: The integer offset of the beam on this board.
        :param new_gains: the new gain values to apply; float.
        :return the value actually written to the host
        """
        reg = self.registers['bf{}_config'.format(beam_index)]
        reg.write(quant_gain=new_gain)
        LOGGER.debug(
                    '%s:%i: Beam %i: set quant_gain(%.5f)' % (
                        self.host, self.index,
                        beam_index, new_gain))
        return self.beam_quant_gains_get(beam_index)

    def beam_quant_gains_get(self, beam_index):
        """
        Read the beam quantiser gains for the given beam from the host.
        :param beam: The Beam() on which to act
        :return one value for the quant gain set on all b-engines on this host
        """
        reg = self.registers['bf{}_config'.format(beam_index)]
        return reg.read()['data']['quant_gain']

    def tx_disable(self,beam_index):
        reg = self.registers['bf{}_config'.format(beam_index)]
        reg.write(txen=False)
        LOGGER.debug('%s:%i: Beam %i: Output disabled' % (
                        self.host, self.index, beam_index))

    def tx_enable(self,beam_index):
        reg = self.registers['bf{}_config'.format(beam_index)]
        reg.write(txen=True)
        LOGGER.debug('%s:%i: Beam %i: Output enabled' % (
                        self.host, self.index, beam_index))
