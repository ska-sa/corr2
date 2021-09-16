"""
A BHost is an extension of an XHost. It contains memory and registers
to set up and control one or more beamformers.

Author: Jason Manley, Andrew Martens, Ruby van Rooyen, Monika Obrocka
"""

from logging import INFO
import numpy as np
import struct

from xhost_fpga import FpgaXHost
# from corr2LogHandlers import getLogger


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

        # This will always be a kwarg
        self.getLogger = kwargs['getLogger']

        logger_name = '{}_bhost-{}-{}'.format(descriptor, str(index), host)
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)
        result, self.logger = self.getLogger(logger_name=logger_name,
                                             log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        self.logger.debug('Successfully created logger for {}'.format(logger_name))

        self.beng_per_host = self.x_per_fpga

        self.host_type = 'bhost'

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
        self.logger.debug('%s:%i: Beam %i:%s destination set to %s' % (
            self.host, self.index, beam.index, beam.name,
            beam.destination))

    def beam_weights_set(self, beam_index, weights):
        """
        Set the beam weights for the given beam and given input labels.
        :param beam_index: The integer offset of the beam on this board.
        :param weights: a list of the weights to set on each input.
        """
        assert len(weights) == self.n_ants, ('Incorrect number of weights supplied (%i; need %i)' % (len(weights), self.n_ants))
        for source_index, source_weight in enumerate(weights):
            self.registers.bf_weight.write(weight=source_weight,
                    stream=beam_index, antenna=source_index, load_now=0)
            self.registers.bf_weight.write(weight=source_weight,
                    stream=beam_index, antenna=source_index, load_now=1)
            #self.registers.bf_weight.write(weight=source_weight,
            #        stream=beam_index, antenna=source_index, load_now=0)
            self.logger.debug(
                '%s:%i: Beam %i: set antenna(%i) weight(%.5f)' % (
                    self.host, self.index, beam_index,
                    source_index, source_weight))
        self.registers.bf_weight.write(weight=source_weight,
                stream=beam_index, antenna=source_index, load_now=0)

    def beam_weights_get(self, beam_index):
        """
        Get the beam weights for the given beam_index (offset on this board).
        Returns a list of weights.
        """
        rv = [0 for a in range(self.n_ants)]
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
        self.logger.debug('%s:%i: Beam %i: set quant_gain(%.5f)' % (
            self.host, self.index, beam_index, new_gain))
        return self.beam_quant_gains_get(beam_index)

    def beam_quant_gains_get(self, beam_index):
        """
        Read the beam quantiser gains for the given beam from the host.
        :param beam: The Beam() on which to act
        :return one value for the quant gain set on all b-engines on this host
        """
        reg = self.registers['bf{}_config'.format(beam_index)]
        return reg.read()['data']['quant_gain']

    def tx_disable(self, beam_index):
        reg = self.registers['bf{}_config'.format(beam_index)]
        reg.write(txen=False)
        self.logger.debug('%s:%i: Beam %i: Output disabled' % (
            self.host, self.index, beam_index))

    def tx_enable(self, beam_index):
        reg = self.registers['bf{}_config'.format(beam_index)]
        reg.write(txen=True)
        self.logger.debug('%s:%i: Beam %i: Output enabled' % (
            self.host, self.index, beam_index))

    def get_bpack_status(self, beam_index):
        """
        Get the status of the beamformer pack blocks.

        :param beam_index: The Beam() on which to act
        :return a list containing a dictionary for each b-engine's pack status register key-value pairs
        """
        rv = []
        for engine_index in range(self.beng_per_host):
            reg = self.registers['sys{}_bf_pack_out{}_status'.format(engine_index, beam_index)]
            rv.append(reg.read()['data'])
        return rv

    def beam_delays_set(self, num_hosts, beam_index, coeffs):
        """
        Set the beam steering coefficients for the given beam and input.
        :param beam_index: The integer offset of the beam on this board.
        :param coeffs: a list of tuples containing the delay settings for all inputs in the form (
            delay (radians), phase (radians), phase base for host (complex value), phase increment per frequency (
            complex value)
        """
        #have used a tuple for coeffs instead of dictionary to save compute resources

        assert len(coeffs) == self.n_ants, \
            'Incorrect number of coeffs supplied (%i supplied; need %i)' % (
                len(coeffs), self.n_ants)

        #create an array of base phase values for every b-engine
        phase_base0 = self.n_ants * [0]
        phase_base1 = self.n_ants * [0]
        phase_base2 = self.n_ants * [0]
        phase_base3 = self.n_ants * [0]

        #create an array of phase increment values (the same for every b-engine)
        phase_inc = self.n_ants * [0]

        #offset of beamformer host fpga in the range [-0.5:0.5) over the band
        #(the delay is calculated for the centre of our band)
        host_offset = (float(self.index) / num_hosts) - 0.5

        #go through coefficients for all antennas
        for ant_index, ant_coeffs in enumerate(coeffs):
            assert len(ant_coeffs) == 4, \
                'Incorrect number of coeffs supplied for beam %i input %i, host %i (%i supplied; need 4' % (
                beam_index, ant_index, self.index, len(ant_coeffs))

            delay = float(ant_coeffs[0])
            phase = float(ant_coeffs[1])

            #the (pre-calculated) phase base change for each b-engine
            phase_base_delta = ant_coeffs[2]

            #the pre-calculated phase rotation increment per frequency within each b-engine
            phase_inc_val = ant_coeffs[3]

            #total phase for base of engine 0
            total_phase = (host_offset * delay) + phase

            phase_base = np.exp(-1.0j * total_phase)
            phase_base0[ant_index] = phase_base

            #update phase base to base of b-engine 1
            phase_base = phase_base * phase_base_delta
            phase_base1[ant_index] = phase_base

            #update phase base to base of b-engine 2
            phase_base = phase_base * phase_base_delta
            phase_base2[ant_index] = phase_base

            #update phase base to base of b-engine 3
            phase_base = phase_base * phase_base_delta
            phase_base3[ant_index] = phase_base

            #the increment is the same for all b-engines
            phase_inc[ant_index] = phase_inc_val

        coeffs0 = (self.n_ants * 4) * [0]
        coeffs1 = (self.n_ants * 4) * [0]
        coeffs2 = (self.n_ants * 4) * [0]
        coeffs3 = (self.n_ants * 4) * [0]

        coeffs0[0::4] = [coeff.real for coeff in phase_base0]
        coeffs0[1::4] = [coeff.imag for coeff in phase_base0]
        coeffs0[2::4] = [coeff.real for coeff in phase_inc]
        coeffs0[3::4] = [coeff.imag for coeff in phase_inc]

        #print 'base: %s' %phase_base0
        #print 'inc: %s' %phase_base0
        #print 'combined: %s' %coeffs0

        coeffs1[0::4] = [coeff.real for coeff in phase_base1]
        coeffs1[1::4] = [coeff.imag for coeff in phase_base1]
        coeffs1[2::4] = [coeff.real for coeff in phase_inc]
        coeffs1[3::4] = [coeff.imag for coeff in phase_inc]

        coeffs2[0::4] = [coeff.real for coeff in phase_base2]
        coeffs2[1::4] = [coeff.imag for coeff in phase_base2]
        coeffs2[2::4] = [coeff.real for coeff in phase_inc]
        coeffs2[3::4] = [coeff.imag for coeff in phase_inc]

        coeffs3[0::4] = [coeff.real for coeff in phase_base3]
        coeffs3[1::4] = [coeff.imag for coeff in phase_base3]
        coeffs3[2::4] = [coeff.real for coeff in phase_inc]
        coeffs3[3::4] = [coeff.imag for coeff in phase_inc]

        #convert to integer values ready for struct.pack
        coeffs0 = [coeff * 2**15 for coeff in coeffs0]
        coeffs1 = [coeff * 2**15 for coeff in coeffs1]
        coeffs2 = [coeff * 2**15 for coeff in coeffs2]
        coeffs3 = [coeff * 2**15 for coeff in coeffs3]

        #ensure that values are not outside of max and minimum values
        for i in range(len(coeffs0)):
            if(coeffs0[i] > 32767):
                coeffs0[i] = 32767
            elif(coeffs0[i] < -32768):
                coeffs0[i] = -32768

        for i in range(len(coeffs1)):
            if(coeffs1[i] > 32767):
                coeffs1[i] = 32767
            elif(coeffs1[i] < -32768):
                coeffs1[i] = -32768

        for i in range(len(coeffs2)):
            if(coeffs2[i] > 32767):
                coeffs2[i] = 32767
            elif(coeffs2[i] < -32768):
                coeffs2[i] = -32768

        for i in range(len(coeffs1)):
            if(coeffs3[i] > 32767):
                coeffs3[i] = 32767
            elif(coeffs3[i] < -32768):
                coeffs3[i] = -32768

        #convert into 16 bit binary values ready for writing to shared BRAM
        ss0 = struct.pack('>%ih' % (self.n_ants * 4), *coeffs0)
        ss1 = struct.pack('>%ih' % (self.n_ants * 4), *coeffs1)
        ss2 = struct.pack('>%ih' % (self.n_ants * 4), *coeffs2)
        ss3 = struct.pack('>%ih' % (self.n_ants * 4), *coeffs3)

        #write values out to brams in b-engines
        bram_name = 'sys0_fbf_beam_steering_coeffs_bram%i' % beam_index
        self.write(bram_name, ss0, 0)
        bram_name = 'sys1_fbf_beam_steering_coeffs_bram%i' % beam_index
        self.write(bram_name, ss1, 0)
        bram_name = 'sys2_fbf_beam_steering_coeffs_bram%i' % beam_index
        self.write(bram_name, ss2, 0)
        bram_name = 'sys3_fbf_beam_steering_coeffs_bram%i' % beam_index
        self.write(bram_name, ss3, 0)

        #self.logger.debug('%s: host id (%i) beam (%i) antenna (%i) beam steering initial phase %.5f degrees (%.5f,%.5f),
        #   delta initial phase %.5f degrees (%.5f,%.5f), phase increment %.5f degrees (%.5f,%.5f)' %(
        #   self.host, self.index, beam_index, ant_index,
        #   total_phase*(180.0/np.pi), phase_base.real, phase_base.imag,
        #   np.arctan(phase_base_delta.imag/phase_base_delta.real)*(180.0/np.pi), phase_base_delta.real, phase_base_delta.imag,
        #   np.arctan(phase_inc.imag/phase_inc.real)*(180.0/np.pi), phase_inc.real, phase_inc.imag)
        #)
