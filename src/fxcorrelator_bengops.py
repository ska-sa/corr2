import logging
from casperfpga import utils as fpgautils

from beam import Beam
from casperfpga.CasperLogHandlers import CasperConsoleHandler

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


class BEngineOperations(object):
    def __init__(self, corr_obj):
        """
        :param corr_obj: the FxCorrelator object with which we interact
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.xhosts
        # self.logger = corr_obj.logger
        self.beams = {}
        self.beng_per_host = corr_obj.x_per_fpga

        # Now creating separate instances of loggers as needed
        self.logger = logging.getLogger(__name__)
        # - Give logger some default config
        console_handler_name = '{}_BEngOps'.format(corr_obj.descriptor)
        console_handler = CasperConsoleHandler(name=console_handler_name)
        self.logger.addHandler(console_handler)
        self.logger.setLevel(logging.DEBUG)
        infomsg = 'Successfully created logger for {}'.format(console_handler_name)
        self.logger.info(infomsg)

    def initialise(self):
        """
        Initialises the b-engines and checks for errors. This is run after
        programming devices in the instrument.

        :return:
        """
        if not self.beams:
            raise RuntimeError('Called beamformer initialise without beams? '
                               'Have you run configure?')
        # Give control register a known state.
        # Set bf_control and bf_config to zero for now
        THREADED_FPGA_OP(self.hosts, timeout=5,
                         target_function=(
                             lambda fpga_:
                             fpga_.registers.bf_control.write_int(0), [], {}))
        # the base data id is shifted down by 8 bits to account for the concat
        # of 8 bits of stream id on the lsb.
        data_id = 0x5000 >> 8
        # time id is 0x1600 immediate
        time_id = 0x1600 | (0x1 << 15)
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(
                lambda fpga_: fpga_.registers.bf_config.write(
                    data_id=data_id, time_id=time_id), [], {}))
        # set up the beams
        for beam in self.beams.values():
            beam.initialise()
        # disable all beams
        # self.partitions_deactivate()
        # done
        self.logger.info('Beamformer initialised.')

    def configure(self):
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
        for section_name in self.corr.configd:
            if section_name.startswith('beam'):
                beam = Beam.from_config(section_name, self.hosts,
                                        self.corr.configd,
                                        self.corr.fops,
                                        self.corr.speadops,)
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

    def tx_enable(self, beams=None):
        """
        Start transmission on beams
        :param beams - list of beam names
        :return:
        """
        #raise DeprecationWarning
        if not beams:
            beams = self.beams.keys()
        for beam_name in beams:
            beam = self.beams[beam_name]
            beam.tx_enable()

    def tx_disable(self, beams=None):
        """
        Stop transmission on beams
        :param beams - list of beam names
        :return:
        """
        #raise DeprecationWarning
        if not beams:
            beams = self.beams.keys()
        for beam_name in beams:
            beam = self.beams[beam_name]
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

    def set_beam_weights(self, new_weight, beam_name=None, input_name=None):
        """
        Set the beam weights for a given beam and input.
        :param new_weight: the new weight to apply to this beam & input
        :param beam_name: the beam name
        :param input_name: the input name
        :return:
        """
        if beam_name is None:
            for bm in self.beams:
                self.set_beam_weights(new_weight, bm, input_name)
            return
        if input_name is None:
            for input_name in self.get_beam_by_name(beam_name).input_names:
                self.set_beam_weights(new_weight, beam_name, input_name)
            return
        beam = self.get_beam_by_name(beam_name)
        self.beams[beam_name].set_weights(input_name, new_weight)
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_beng_weights()

    def get_beam_weights(self, beam_name=None, input_name=None):
        """
        Get the current beam weights for a given beam and input.
        :param beam_name: the beam name
        :param input_name: the input name
        :return: the beam weight(s) for this combination
        """
        if beam_name is None:
            return {bm: self.get_beam_weights(bm, input_name)
                    for bm in self.beams}
        beam = self.get_beam_by_name(beam_name)
        return beam.get_weights(input_name)

    def set_beam_quant_gains(self, new_gain, beam_name=None):
        """
        Set the beam weights for a given beam and input.
        :param new_gain: the new gain to apply to this beam & input
        :param beam_name: the beam name
        :return:
        """
        if beam_name is None:
            for bm in self.beams:
                self.set_beam_quant_gains(new_gain, bm)
            return
        beam = self.get_beam_by_name(beam_name)
        self.beams[beam_name].set_quant_gains(new_gain)
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_beng_gains()

    def get_beam_quant_gains(self, beam_name=None):
        """
        Get the current beam weights for a given beam and input.
        :param beam_name: the beam name
        :return: the beam weight(s) for this combination
        """
        if beam_name is None:
            return {bm: self.get_beam_quant_gains(bm)
                    for bm in self.beams}
        beam = self.get_beam_by_name(beam_name)
        return beam.get_quant_gains()

