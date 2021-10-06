from logging import INFO
from casperfpga import utils as fpgautils
from beam import Beam
import delay as delayops
import time
import numpy

# from corr2LogHandlers import getLogger

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


class BEngineOperations(object):
    def __init__(self, corr_obj, **kwargs):
        """
        :param corr_obj: the FxCorrelator object with which we interact
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.xhosts
        self.beams = {}
        self.beng_per_host = corr_obj.x_per_fpga

        # Now creating separate instances of loggers as needed
        logger_name = '{}_BengOps'.format(corr_obj.descriptor)
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)

        # All 'Instrument-level' objects will log at level INFO
        result, self.logger = corr_obj.getLogger(logger_name=logger_name,
                                                 log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        self.logger.debug('Successfully created logger for {}'.format(logger_name))

    def initialise(self, *args, **kwargs):
        """
        Initialises the b-engines and checks for errors. This is run after
        programming devices in the instrument.

        :return:
        """
        if not self.beams:
            raise RuntimeError('Called beamformer initialise without beams? '
                               'Have you run configure?')
        # set up the beams
        for beam in self.beams.values():
            beam.initialise()
        # disable all beams (this is done in beam.py)
        #self.tx_disable()
        # initialise beam weights, delays and quantiser gains to something sensible

        init_delay = 0.0
        init_phase = 0.0
        delays = ((init_delay, init_phase),) * self.corr.n_antennas
        if self.corr.n_chans != 32768:
            for beam_name in self.beams:
                self.set_beam_delays(beam_name, delays)

        init_weight = 1.0
        weights = [init_weight] * self.corr.n_antennas
        for beam_name in self.beams:
            beam = self.get_beam_by_name(beam_name)
            self.set_beam_quant_gain(float(beam.config['quant_gain']), beam_name)
            self.set_beam_weights(weights, beam_name)
        self.logger.info('Beamformer initialised.')

    def configure(self, *args, **kwargs):
        """
        Configure the beams from the config source. This is done whenever
        an instrument is instantiated.
        :return:
        """
        if self.beams:
            raise RuntimeError('Beamformer ops already configured.')

        # get beam names from config
        beam_names = []
        self.beams = {}
        max_pkt_size = self.corr.b_stream_payload_len
        for section_name in self.corr.configd:
            if section_name.startswith('beam'):
                beam = Beam.from_config(section_name, self.hosts,
                                        self.corr.configd,
                                        self.corr.fops,
                                        self.corr.speadops,
                                        max_pkt_size=max_pkt_size,
                                        *args, **kwargs)
                if beam.name in beam_names:
                    raise ValueError('Cannot have more than one beam with '
                                     'the name %s. Please check the '
                                     'config file.' % beam.name)
                self.beams[beam.name] = beam
                beam_names.append(beam.name)
        self.logger.info('Found {} beams: {}'.format(len(beam_names),
                                                     beam_names))

        # add the beam data streams to the instrument list
        for beam in self.beams.values():
            self.corr.add_data_stream(beam)

    def tx_enable(self, beam_names=None):
        """
        Start transmission on beams
        :param beam_names - list of beam names; if not specified, start all.
        :return:
        """
        if not beam_names:
            beam_names = self.beams.keys()
        for beam_name in beam_names:
            beam = self.get_beam_by_name(beam_name)
            beam.tx_enable()

    def tx_disable(self, beam_names=None):
        """
        Stop transmission on beams
        :param beam_names - list of beam names; if not specified, stop all.
        :return:
        """
        if not beam_names:
            beam_names = self.beams.keys()
        for beam_name in beam_names:
            beam = self.get_beam_by_name(beam_name)
            beam.tx_disable()

    def get_beam_by_name(self, beam_name):
        """
        Given a string beam_name, return the corresponding Beam
        :param beam_name:
        :return:
        """
        if beam_name not in self.beams:
            raise KeyError('No such beam: %s, available beams: %s' % (
                beam_name, self.beams))
        return self.beams[beam_name]

    def get_beam_inputs(self, beam_name):
        """
        Return a list of the input stream names used for this beam.
        """
        inputs = self.corr.get_input_labels()
        pol = self.get_beam_by_name(beam_name).polarisation
        return inputs[pol::2]

    def set_beam_quant_gain(self, new_gain, beam_name=None):
        """
        Set the beam (output) gain for a given beam.
        :param new_gain: the new gain to apply to this beam
        :param beam_name: the beam name
        :return:
        """
        if beam_name is None:
            for beam in self.beams:
                self.set_beam_quant_gain(new_gain, beam_name=beam.name)
            return
        beam = self.get_beam_by_name(beam_name)
        # set the quantiser gains for this beam
        THREADED_FPGA_FUNC(self.hosts, 5, ('beam_quant_gains_set',
                                           [beam.index, new_gain], {}))
        self.logger.info('%s quant gain set to %f.' % (beam_name, new_gain))
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_beng_gains()

    def get_beam_quant_gain(self, beam_name):
        """
        Get the current beam weights for a given beam and input.
        :param beam_name: the beam name
        :return: the output beam gain for this combination
        """
        beam = self.get_beam_by_name(beam_name)
        vals = THREADED_FPGA_FUNC(self.hosts, 5, ('beam_quant_gains_get',
                                           [beam.index], {}))
        if min(vals.values()) == max(vals.values()):
            return vals.values()[0]
        else:
            raise RuntimeError('Boards dont all have the same gain! {}'.format(vals))

    def set_beam_weights(self, weights, beam_name=None):
        """
        Set the beam weights for a given beam and input.
        :param weights: a list of weights, one per input, to apply to this beam & input. Give a single value to use for all inputs.
        :param beam_name: the beam name; if not specified, apply to all.
        :return:
        """
        if beam_name is None:
            for beam_name in self.beams:
                self.set_beam_weights(weights, beam_name=beam_name)
            return
        if type(weights) == int or type(weights) == float:
            new_weights = [weights for a in range(self.corr.n_antennas)]
        else:
            new_weights = weights

        self.logger.debug('Received weights for beam %s: %s' % (str(beam_name), str(weights)))

        assert len(new_weights) == self.corr.n_antennas, 'Need to specify %i values; you offered %i.' % (self.corr.n_antennas, len(new_weights))
        beam_index = self.get_beam_by_name(beam_name).index
        THREADED_FPGA_FUNC(self.hosts, 5, ('beam_weights_set',
                                           [beam_index, new_weights], {}))
        self.logger.info('{} weights set to {}.'.format(beam_name, new_weights))
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_beng_weights()

    def get_beam_weights(self, beam_name):
        """
        Get the current beam weights for a given beam and input.
        :param beam_name: the beam name
        :return: a list of the beam weights, one per input.
        """
        beam = self.get_beam_by_name(beam_name)
        vals = THREADED_FPGA_FUNC(self.hosts, 10, ('beam_weights_get',
                                           [beam.index], {}))
        import numpy
        na = numpy.array(vals.values())
        for ant in range(self.corr.n_antennas):
            if na[:, ant].max() != na[:, ant].min():
                self.logger.warning('Boards dont all have the same gain! {}'.format(vals))
        return vals.values()[0]

    def get_version_info(self):
        """
        Get the version information for the hosts
        :return: a dict of {file: version_info, }
        """
        try:
            return self.hosts[0].get_version_info()
        except AttributeError:
            return {}

    def get_pack_status(self):
        """
        Get the status of all the pack blocks in the beamformer system.
        Returns a dictionary, indexed by beam name, of all the engines' states
        """
        #TODO This function doesn't really add value. Remove?
        rv = {}
        for beam in self.beams.itervalues():
            rv[beam.name] = THREADED_FPGA_FUNC(self.hosts, 5, ('get_bpack_status',
                                           [beam.index], {}))
        return rv

    def set_beam_delays(self, beam_name, delays):
        """
        Set the beam steering delay coefficients for specified input
        :param beam_name: the target beam
        :param delays: list of tuples (delay(seconds),phase(radians),...),
                        or strings delay:phase... one per input
        """
        if self.corr.n_chans == 32768:
            self.logger.info('Preventing setting delays on 32k system')
            return

        #process delays passed as string
        def process_string(delaystr):
            bits = delaystr.strip().split(':')
            if len(bits) != 2:
                return -1
            return float(bits[0]), float(bits[1])

        if len(delays) != self.corr.n_antennas:
            self.logger.error('Need to specify %i delay values, %i provided.'
                % (self.corr.n_antennas, len(delays)))
            return

        ant_coeffs = []
        last_delays = []
        load_mcnt = self.corr.mcnt_from_time(time.time())
        #generate delay and phase values for all antennas
        for ant_index, ant_delay in enumerate(delays):
            #if passed in as string, split and convert
            if isinstance(ant_delay, str):
                ant_delay_tup = process_string(ant_delay)
            else:
                ant_delay_tup = ant_delay

            if len(ant_delay_tup) != 2:
                self.logger.error('Beam delay values must consist of 2 values, %i given for antenna %i' % (
                    len(ant_delay_tup), ant_index))
                return

            new_delay = delayops.prepare_delay_vals([[ant_delay_tup[0], 0.0], [ant_delay_tup[1], 0.0]],
                self.corr.sample_rate_hz)
            new_delay.load_mcnt = load_mcnt

            #for a noise-like signal it makes little sense to delay by more than our FFT length
            if new_delay.delay > self.corr.n_chans:
                self.logger.info('Request to delay antenna input %i by %i samples in a %i channel system.' % (
                    ant_index, new_delay.delay, self.corr.n_chans))

            #phase change across the band for the delay specified (radians)
            #negative slope for positive delay
            delay = -new_delay.delay * numpy.pi
            #phase offset (radians)
            phase = new_delay.phase_offset * numpy.pi

            #phase change per frequency as pre-calculated complex value
            phase_per_freq = numpy.exp(1.0j * (delay / self.corr.n_chans))
            #phase change per bengine as pre-calculated complex value
            phase_per_beng = numpy.exp(1.0j * (delay / (len(self.hosts) * self.beng_per_host)))

            ant_coeffs.append((delay, phase, phase_per_beng, phase_per_freq))

            #record delay settings for sensor update
            last_delays.append(new_delay)

        #change coefficients on all hosts
        beam = self.get_beam_by_name(beam_name)
        THREADED_FPGA_FUNC(self.hosts, 10, ('beam_delays_set', [len(self.hosts), beam.index, ant_coeffs], {}))
        self.logger.info('{} delays set to {}.'.format(beam_name, delays))
        beam.last_delays = last_delays
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_beng_delays(beam)

    def get_beam_delays(self, beam_name):
        """
        Get the beam steering delay coefficients for specified input
        :param beam_name: the target beam
        :param delays: list of tuples (delay(seconds), phase(radians),...),
                        or strings delay:phase... one per input
        """
        beam = self.get_beam_by_name(beam_name)
        last_delays = beam.last_delays
        delay_vals = ''
        if (last_delays is not None):
            import numpy
            for delay_coeffs in last_delays:
                delay = delay_coeffs.delay / self.corr.sample_rate_hz
                phase_offset = delay_coeffs.phase_offset * numpy.pi
                delay_vals += '{:.10e}:{:.10e} '.format(delay, phase_offset)

        return delay_vals
