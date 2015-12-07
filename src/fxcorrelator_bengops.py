import logging
from casperfpga import utils as fpgautils

from beam import Beam

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

LOGGER = logging.getLogger(__name__)


class BEngineOperations(object):
    def __init__(self, corr_obj):
        """
        :param corr_obj: the FxCorrelator object with which we interact
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.xhosts
        self.logger = corr_obj.logger
        self.beams = {}

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
        self.partitions_deactivate()
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
        for k in self.corr.configd:
            if k.startswith('beam_'):
                beam_names.append(k.strip().replace('beam_', ''))
        self.logger.info('Found beams: %s' % beam_names)

        # make the beams
        self.beams = {}
        for beam_idx, beam_name in enumerate(beam_names):
            newbeam = Beam.from_config(beam_name, self.hosts,
                                       self.corr.configd,
                                       self.corr.speadops)
            self.beams[newbeam.name] = newbeam

        # configure the beams
        for beam in self.beams.values():
            beam.configure()

        # add the beam data products to the instrument list
        for beam in self.beams.values():
            self.corr.register_data_product(beam.data_product)

    def tx_control_update(self, beams=None):
        """
        Start transmission of active partitions on all beams
        :param beams - list of beam names
        :return:
        """
        if not beams:
            beams = self.beams.keys()
        for beam_name in beams:
            beam = self.beams[beam_name]
            beam.tx_control_update()

    def partitions_current(self):
        """
        Get the currently active partitions for each beam, directly from
        the host.
        :return:
        """
        return {beam.name: beam.partitions_current()
                for beam in self.beams.values()}

    def partitions_activate(self, partitions_to_activate=None):
        """
        Activate partitions for all beams
        """
        for beam in self.beams.values():
            beam.partitions_activate(partitions_to_activate)

    def partitions_deactivate(self, partitions_to_deactivate=None):
        """
        Deactivate partitions for all beams
        """
        for beam in self.beams.values():
            beam.partitions_deactivate(partitions_to_deactivate)

    def set_beam_bandwidth(self, beam_name, bandwidth, centerfreq):
        """
        Set the partitions for a given beam based on a provided bandwidth
        and center frequency.
        :param beam_name: the name of the beam to set
        :param bandwidth: the bandwidth, in hz
        :param centerfreq: the center freq of this band, in hz
        :return: tuple, the set (bw, cf) for that beam
        """
        if beam_name not in self.beams:
            raise RuntimeError('No such beam: %s, available beams: %s' % (
                beam_name, self.beams))
        beam = self.beams[beam_name]
        return beam.set_beam_bandwidth(bandwidth, centerfreq)

    def get_beam_bandwidth(self, beam_name):
        """
        Get the partitions for a given beam i.t.o. bandwidth
        and center frequency.
        :param beam_name: the name of the beam to set
        :return: (beam bandwidth, beam_cf)
        """
        if beam_name not in self.beams:
            raise RuntimeError('No such beam: %s, available beams: %s' % (
                beam_name, self.beams))
        beam = self.beams[beam_name]
        return beam.get_beam_bandwidth()

    def set_beam_weights(self, beam_name, input_name, new_weight):
        """
        Set the beam weights for a given beam and input.
        :param beam_name str: the beam name
        :param input_name str: the input name
        :return:
        """
        if beam_name not in self.beams:
            raise RuntimeError('No such beam: %s, available beams: %s' % (
                beam_name, self.beams))
        self.beams[beam_name].set_weights(input_name, new_weight)

    def get_beam_weights(self, beam_name, input_name):
        """
        Get the current beam weights for a given beam and input.
        :param beam_name str: the beam name
        :param input_name str: the input name
        :return: the beam weight(s) for this combination
        """
        beam = self.beams[beam_name]
        return beam.get_weights(input_name)

    def update_labels(self, oldnames, newnames):
        """
        Update the input labels
        :return:
        """
        for beam in self.beams.values():
            beam.update_labels(oldnames, newnames)

    # def spead_meta_update_dataheap(self):
    #     """
    #
    #     :return:
    #     """
    #     for beam in self.beams.values():
    #         beam.spead_meta_update_dataheap()
    #
    # def spead_meta_update_beamformer(self):
    #     """
    #     Issues the SPEAD metadata packets containing the payload
    #     and options descriptors and unpack sequences.
    #     :return:
    #     """
    #     for beam in self.beams.values():
    #         beam.spead_meta_update_beamformer()
    #
    # def spead_meta_update_destination(self):
    #     """
    #     Update the SPEAD IGs to notify the receiver of changes to destination
    #     :return:
    #     """
    #     for beam in self.beams.values():
    #         beam.spead_meta_update_destination()
    #
    # def spead_meta_update_weights(self):
    #     """
    #     Update the weights in the BEAM SPEAD ItemGroups.
    #     :return:
    #     """
    #     for beam in self.beams.values():
    #         beam.spead_meta_update_weights()
    #
    # def spead_meta_update_labels(self):
    #     """
    #     Update the labels in the BEAM SPEAD ItemGroups.
    #     :return:
    #     """
    #     for beam in self.beams.values():
    #         beam.spead_meta_update_labels()
    #
    # def spead_meta_update_all(self):
    #     """
    #     Update the IGs for all beams for all beamformer info
    #     :return:
    #     """
    #     self.spead_meta_update_beamformer()
    #     self.spead_meta_update_dataheap()
    #     self.spead_meta_update_destination()
    #     self.spead_meta_update_weights()
    #     self.spead_meta_update_labels()
    #
    # def spead_meta_transmit_all(self):
    #     """
    #     Transmit SPEAD metadata for all beams
    #     :return:
    #     """
    #     for beam_name, beam in self.beams.items():
    #         beam.spead_meta_transmit_all()
    #
    # def spead_meta_issue_all(self):
    #     """
    #     Issue = update + transmit
    #     """
    #     if not self.beams:
    #         self.logger.info('Cannot issue metadata without beams!')
    #         raise RuntimeError
    #     self.spead_meta_update_all()
    #     self.spead_meta_transmit_all()

    # BFSTAGE_DUPLICATE = 0
    # BFSTAGE_CALIBRATE = 1
    # BFSTAGE_STEER = 2
    # BFSTAGE_COMBINE = 3
    # BFSTAGE_VISIBILITY = 4
    # BFSTAGE_ACCUMULATE = 5
    # BFSTAGE_REQUANTISE = 6
    # BFSTAGE_FILTER = 7
    #
    # def bf_control_shift(id_control):
    #     return 0x1 << id_control
    #
    # def find_beng_index(self, freq=None, sky_freq=None, channel=None):
    #     """
    #     Given a frequency (sky or bb) or channel number, work out where
    #     that can be found
    #     :param freq - the baseband frequency to search
    #     :param freq - the sky frequency to search
    #     :param channel - the channel to search
    #     :return: tuple - (bhost index in self.hosts, bengine index total, bengine index within host)
    #     """
    #     if (freq is None) and (sky_freq is None) and (channel is None):
    #         raise RuntimeError('Must provide something for which to search.')
    #     if channel is None:
    #         if freq is not None:
    #             channel = self.corr.fops.freq_to_chan(freq)
    #         else:
    #             channel = self.corr.fops.sky_freq_to_chan(freq)
    #     _host_index = numpy.floor(channel / self.corr.xops.channels_per_xhost)
    #     _beng_index_absolute = numpy.floor(channel / self.corr.xops.channels_per_xengine)
    #     _beng_index = _beng_index_absolute % self.corr.xops.xengines_per_xhost
    #     return _host_index, _beng_index_absolute, _beng_index

    # def tx_stop(self, beams=None, spead_stop=True):
    #     """
    #     Stops outputting SPEAD data over 10GbE links for specified beams.
    #     Sends SPEAD packets indicating end of stream if required
    #     :param beams: ['i', 'q']
    #     :param spead_stop: boolean
    #     :return:
    #     """
    #     self.logger.info('Stopping beamformers')
    #
    #     # stop the bengines at the filter stage
    #     THREADED_FPGA_FUNC(self.hosts, timeout=5,
    #                        target_function=('value_filter_set',
    #                                         [], {'value': 0, 'beng_indices': None}))
    #
    #     # update spead
    #     spead_stop = False
    #     if spead_stop:
    #         raise NotImplementedError
    #         # TODO
    #
    #     self.logger.info('Stopped all beam transmission')

    # def write_value(self, bf_stage, data, beams=None, antennas=None):
    #     """
    #     write to various destinations in the bf block for a particular beam
    #     :param bf_stage: the stage to which to write the value: 'calibrate',
    #     'filter', 'requantise', 'duplicate'
    #     :param data: the single value to write
    #     :param beams: strings, to which beams should we apply the value
    #     :param antennas: strings, to which antennas should we apply the value
    #     :return:
    #     """
    #     # check for a valid stage selection
    #     if bf_stage == BFSTAGE_CALIBRATE:
    #         if antennas is None:
    #             self.corr.logger.error('Need to specify an antenna when writing to calibrate block')
    #             raise RuntimeError('Need to specify an antenna when writing to calibrate block')
    #     elif bf_stage == BFSTAGE_REQUANTISE:
    #         if antennas is not None:
    #             self.corr.logger.error('Cannot specify antenna for requantise block')
    #             raise RuntimeError('Cannot specify antenna for requantise block')
    #     elif bf_stage == BFSTAGE_DUPLICATE or bf_stage == BFSTAGE_FILTER:
    #         pass
    #     else:
    #         raise self.corr.logger.error('write_value does not process BF stage %s' % bf_stage)
    #
    #     # set the stream and destination in the control register on all the boards
    #
    #
    #     # loop over fpgas and set the registers
    #     location = int(beam2location(corr, beams=beams)[0])
    #     # set beam (stream) based on location
    #     THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_stream', [int(location)]))
    #
    #     # set read/write destination
    #     id_control = BF_CONTROL_LOOKUP[destination]
    #     control = bf_control_shift(id_control)
    #     THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_write_destination', [control]))
    #
    #     # set antenna if needed
    #     if bf_stage == 'calibrate':
    #         # check if ant string is correct
    #         if ants2ants(corr, beam=beams, antennas=antennas):
    #             ant_n = input2ants(corr, beams, antennas=[antennas])
    #             THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_antenna', [ant_n[0]]))
    #             THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_value_in', [data]))
    #         else:
    #             raise corr.logger.error('Need to specify a single antenna. Got many.')
    #     elif destination == 'duplicate' or destination == 'filter' or destination == 'requantise':
    #         THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_value_in', [data]))
    # #
    # # def _get_ant_mapping_list(corr):
    # #     """
    # #     assign index to each antenna and each beam for that antenna
    # #     there's no current mapping or the mapping is bad... set default:
    # #     :return:
    # #     """
    # #     raise RuntimeError('isn\'t this in fxcorrelator already?')
    # #     # hardcoded for now self.config['pols']
    # #     n_pols = 2
    # #     n_inputs = corr.n_antennas * n_pols
    # #     ant_list = []
    # #     for a in range(corr.n_antennas):
    # #         for p in range(n_pols):
    # #             ant_list.append('%i%c' % (a, p))
    # #     return ant_list[0:n_inputs]
    # #
    # #
    # def get_bfs(corr):
    #     """
    #     get bf blocks per fpga
    #     :return: all_bfs
    #     """
    #     all_bfs = range(corr.bf_beams_per_fpga)
    #     return all_bfs
    #
    #
    # def get_beams(corr):
    #     """
    #     get a list of beam names in system (same for all antennas)
    #     :return: all_beams
    #     """
    #     all_beams = []
    #     # number of beams per beamformer
    #     for beam_index in range(corr.bf_num_beams):
    #         _valfromcorrconfig = corr.configd['bengine']['bf_name_beam%i' % beam_index]
    #         all_beams.append(_valfromcorrconfig)
    #     return all_beams
    #
    #
    # def fft_bin2frequency(corr, fft_bins):
    #     """
    #     returns a list of center frequencies associated with the fft bins supplied
    #     :param fft_bins:
    #     :return: frequencies
    #     """
    #     n_chans = int(corr.configd['fengine']['n_chans'])
    #     if fft_bins == range(n_chans):
    #         fft_bins = range(n_chans)
    #     if (max(fft_bins) > n_chans) or (min(fft_bins) < 0):
    #         raise corr.logger.error('fft_bins out of range 0 -> %d' % (n_chans-1))
    #     bandwidth = int(corr.configd['fengine']['bandwidth'])
    #     frequencies = []
    #     for fft_bin in fft_bins:
    #         frequencies.append((float(fft_bin)/n_chans)*bandwidth)
    #     return frequencies
    #
    #
    # def frequency2fft_bin(corr, frequencies=None):
    #     """
    #     returns fft bin associated with specified frequencies
    #     :param frequencies:
    #     :return: fft_bins
    #     """
    #     n_chans = int(corr.configd['fengine']['n_chans'])
    #     if frequencies is None:
    #         return []
    #     elif frequencies == range(n_chans):
    #         return range(n_chans)
    #     else:
    #         fft_bins = []
    #         bandwidth = float(corr.configd['fengine']['bandwidth'])
    #         start_freq = 0
    #         channel_width = bandwidth/n_chans
    #         for frequency in frequencies:
    #             frequency_normalised = numpy.mod((frequency-start_freq)+channel_width/2, bandwidth)
    #             # conversion to int with truncation
    #             fft_bins.append(numpy.int(frequency_normalised/channel_width))
    #         return fft_bins
    #
    #
    # def map_ant_to_input(corr, beam, antennas):
    #     """
    #     maps antenna strings specified to input to beamformer
    #     gives index of antennas in the list of all_antennas
    #     :param beam: 'i' or 'q'
    #     :param ant_strs: ['0\x00', '0\x01', '1\x00', '1\x01', '2\x00', '2\x01', '3\x00', '3\x01']
    #     :return: inputs
    #     """
    #     beam_ants = ants2ants(corr, beam=beam, antennas=antennas)
    #     ant_strs = _get_ant_mapping_list(corr)
    #     inputs = []
    #     for ant_str in beam_ants:
    #         inputs.append(ant_strs.index(ant_str))
    #     return inputs
    #
    #
    # def ants2ants(corr, beam, antennas):
    #     """
    #     From antenna+polarisation list extract only the str for the beam
    #     (expands all, None etc into valid antenna strings. Checks for valid antenna strings)
    #     :param beam: string
    #     :param ant_strs:
    #     :return: ants
    #     """
    #     if antennas is None:
    #         return []
    #     beam_ants = []
    #     beam_idx = beam2index(corr, beam)[0]
    #     for ant_str in antennas:
    #         if ord(ant_str[-1]) == beam_idx:
    #             beam_ants.append(ant_str)
    #     return beam_ants
    #
    #
    # def beam2index(corr, beams):
    #     """
    #     returns index of beam with specified name
    #     :param beams: 'i' or 'q' or all
    #     :return: indices
    #     """
    #     # expand all etc, check for valid names etc
    #     all_beams = get_beams(corr)
    #     indices = []
    #     for beam in beams:
    #         indices.append(all_beams.index(beam))
    #     return indices
    #
    #
    # def input2ants(corr, beam, antennas=None):
    #     """
    #     :param beam:
    #     :param antennas:
    #     :return:
    #     """
    #     if antennas is None:
    #         return []
    #     beam = beams2beams(corr, beams=beam)[0]
    #     beam_idx = beam2index(corr, beam)[0]
    #     beam_ants = []
    #     for ant_str in antennas:
    #         if ord(ant_str[-1]) == beam_idx:
    #             beam_ants.append(int(ant_str[0]))
    #     return beam_ants
    #
    #
    # def get_bf_bandwidth(corr):
    #     """
    #     Returns the bandwidth for one bf engine
    #     :return: bf_bandwidth
    #     """
    #     bandwidth = corr.configd['fengine']['bandwidth']
    #     bf_be_per_fpga = len(get_bfs(corr))
    #     n_fpgas = len(corr.xhosts)
    #     bf_bandwidth = float(bandwidth)/(bf_be_per_fpga*n_fpgas)
    #     return bf_bandwidth
    #
    #
    # def get_bf_fft_bins(corr):
    #     """
    #     Returns the number of fft bins for one bf engine
    #     :return: bf_fft_bins
    #     """
    #     n_chans = int(corr.configd['fengine']['n_chans'])
    #     bf_be_per_fpga = len(get_bfs(corr))
    #     n_fpgas = len(corr.xhosts)
    #     bf_fft_bins = n_chans/(bf_be_per_fpga*n_fpgas)
    #     return bf_fft_bins
    #
    #
    # def get_fft_bin_bandwidth(corr):
    #     """
    #     get bandwidth of single fft bin
    #     :return: fft_bin_bandwidth
    #     """
    #     n_chans = int(corr.configd['fengine']['n_chans'])
    #     bandwidth = int(corr.configd['fengine']['bandwidth'])
    #     fft_bin_bandwidth = bandwidth/n_chans
    #     return fft_bin_bandwidth
    #
    #
    # def beam2location(corr, beams):
    #     """
    #     returns location of beam with associated name or index
    #     :param beams:
    #     :return: locations
    #     """
    #     beams = beams2beams(corr, beams)
    #     locations = []
    #     for beam in beams:
    #         beam_location = get_beam_param(corr, beam, 'location')
    #         locations.append(beam_location)
    #     return locations
    #
    #
    # def get_beam_param(corr, beams, param):
    #     """
    #     Read beam parameter (same for all antennas)
    #     :param beams: string
    #     :param param: location, name, center_frequency, bandwidth,
    #                   rx_meta_ip_str, rx_udp_ip_str, rx_udp_port
    #     :return: values
    #     """
    #     beams = beams2beams(corr, beams)
    #     beam_indices = beam2index(corr, beams)
    #     if not beam_indices:
    #         raise corr.logger.error('Error locating beams function')
    #     return [corr.configd['bengine']['bf_%s_beam%d' % (param, beam_index)]
    #             for beam_index in beam_indices]
    #
    #
    # def set_beam_param(corr, beams, param):
    #     """
    #     Set some beam parameter
    #     :param corr:
    #     :param beams:
    #     :param param:
    #     :return:
    #     """
    #     raise NotImplementedError
    #
    #
    # def antenna2antenna_indices(corr, beam, antennas):
    #     """
    #     map antenna strings to inputs
    #     :param beam:
    #     :param ant_strs:
    #     :return: antenna_indices
    #     """
    #     n_ants = int(corr.configd['fengine']['n_antennas'])
    #     # hardcoded for now self.config['pols']
    #     n_pols = 2
    #     antenna_indices = []
    #     if len(antennas) == n_ants*n_pols:
    #         antenna_indices.extend(range(n_ants))
    #     else:
    #         antenna_indices = map_ant_to_input(corr, beam, antennas=antennas)
    #     return antenna_indices
    #
    #
    # def bf_read_int(corr, beam, destination, antennas=None):
    #     """
    #     read from destination in the bf block for a particular beam
    #     :param beam:
    #     :param destination: 'calibrate' 'requantise' 'duplicate' 'filter'
    #     :param antennas:
    #     :return: single value
    #     """
    #     if destination == 'calibrate':
    #         if antennas is None:
    #             raise corr.logger.error('Need to specify an antenna when writing to calibrate block function')
    #     elif destination == 'requantise':
    #         if antennas is not None:
    #             raise corr.logger.error('Can''t specify antenna for requantise block function')
    #     # loop over fpgas and set the registers
    #     # get beam location
    #     location = int(beam2location(corr, beams=beam)[0])
    #     # set beam (stream) based on location
    #     THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_stream', [int(location)]))
    #     # set read/write destination
    #     id_control = BF_CONTROL_LOOKUP[destination]
    #     control = bf_control_shift(id_control)
    #     THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_write_destination', [control]))
    #     # set antenna if needed
    #     if (antennas is not None) and len(antennas) == 1:
    #         # check if ant string is correct
    #         if ants2ants(corr, beam=beam, antennas=antennas):
    #             ant_n = input2ants(corr, beam, antennas=[antennas])
    #             if len(ant_n) == 1:
    #                 THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_antenna', [ant_n[0]]))
    #             else:
    #                 raise corr.logger.error('Need to specify a single antenna. Got many')
    #         else:
    #             raise corr.logger.error('Need to specify a single antenna. Got many')
    #     # loop over b-engs
    #     beng_data = []
    #     for beng in get_bfs(corr):
    #         # set beng
    #         THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beng', [beng]))
    #         # triggering write
    #         THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_read_destination', [id_control]))
    #         # read value out
    #         read_bf = THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('read_value_out', ))
    #         if read_bf.values().count(read_bf.values()[0]) != len(read_bf.values()):  # values are not the same
    #             raise corr.logger.error('Problem: value_out on b-engines %i are not the same.' % beng)
    #         else:
    #             beng_data.append(read_bf.values()[0])
    #     if beng_data.count(beng_data[0]) == len(beng_data):
    #         values = beng_data[0]
    #     else:
    #         raise corr.logger.error('Problem: value_out on b-hosts are not the same.')
    #     # return single integer
    #     return values




    #
    #
    # def cf_bw2fft_bins(corr, center_frequency, bandwidth):
    #     """
    #     returns fft bins associated with provided center_frequency and bandwidth
    #     center_frequency is assumed to be the center of the 2^(N-1) fft bin
    #     :param center_frequency:
    #     :param bandwidth:
    #     :return: bins
    #     """
    #     max_bandwidth = float(corr.configd['fengine']['bandwidth'])
    #     fft_bin_width = get_fft_bin_bandwidth(corr)
    #     center_frequency = float(center_frequency)
    #     bandwidth = float(bandwidth)
    #     # TODO spectral line mode systems??
    #     if (center_frequency-bandwidth/2) < 0 or \
    #             (center_frequency+bandwidth/2) > max_bandwidth or \
    #             (center_frequency-bandwidth/2) >= (center_frequency+bandwidth/2):
    #         raise corr.logger.error('Band specified not valid for our system')
    #     # get fft bin for edge frequencies
    #     edge_bins = frequency2fft_bin(corr, frequencies=[center_frequency-bandwidth/2,
    #                                                      center_frequency+bandwidth/2-fft_bin_width])
    #     bins = range(edge_bins[0], edge_bins[1]+1)
    #     return bins
    #
    #
    # def frequency2bf_index(corr, frequencies, fft_bins, unique=False):
    #     """
    #     returns bf indices associated with the frequencies specified
    #     :param frequencies:
    #     :param fft_bins:
    #     :param unique:
    #     :return: bf_indices
    #     """
    #     bf_indices = []
    #     if len(fft_bins) == 0:
    #         fft_bins = frequency2fft_bin(corr, frequencies=frequencies)
    #     n_fpgas = len(corr.xhosts)  # x-eng
    #     bf_be_per_fpga = len(get_bfs(corr))
    #     n_bfs = n_fpgas*bf_be_per_fpga  # total number of bfs
    #     n_chans = int(corr.configd['fengine']['n_chans'])
    #     n_chans_per_bf = n_chans/n_bfs
    #     if max(fft_bins) > n_chans-1 or min(fft_bins) < 0:
    #         raise corr.logger.error('FFT bin/s out of range')
    #     for fft_bin in fft_bins:
    #         bf_index = fft_bin/n_chans_per_bf
    #         if (not unique) or bf_indices.count(bf_index) == 0:
    #             bf_indices.append(bf_index)
    #     return bf_indices
    #
    #
    # def cf_bw2cf_bw(corr, center_frequency, bandwidth):
    #     """
    #     converts specfied center_frequency, bandwidth to values possible for our system
    #     :param center_frequency:
    #     :param bandwidth:
    #     :return: beam_center_frequency, beam_bandwidth
    #     """
    #     bins = cf_bw2fft_bins(corr, center_frequency, bandwidth)
    #     bfs = frequency2bf_index(corr, fft_bins=bins, unique=True)
    #     # bfs = 1  # for now
    #     bf_bandwidth = get_bf_bandwidth(corr)
    #     # calculate start frequency accounting for frequency specified in center of bin
    #     start_frequency = min(bfs)*bf_bandwidth
    #     beam_center_frequency = start_frequency+bf_bandwidth*(float(len(bfs))/2)
    #     beam_bandwidth = len(bfs) * bf_bandwidth
    #     return beam_center_frequency, beam_bandwidth
    #
    #
    #
    #
    #
    # def tx_start(corr, beams):
    #     """
    #     Start outputting SPEAD products on all boards.
    #     Only works for systems with 10GbE output atm.
    #     :param beams:
    #     :return:
    #     """
    #     # NOTE that the order of the following operations is significant
    #     # output from bfs will be enabled if any component frequencies are required
    #     # loop over fpgas and set the registers
    #     beam_indices = beam2index(corr, beams)
    #     for index in beam_indices:
    #         value = {'beam_id': index, 'n_partitions': 0, 'rst': 1}
    #         THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beam_config', (value, index, True)))
    #         for beng in len(get_bfs(corr)):
    #             THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beam_offset', (0, index, beng)))
    #         bf_write_value(corr, destination='filter', data=1, beams=beams[index], antennas=None)  # enables output
    #         corr.logger.info('Output for beam %i started' % index)



    #
    #
    # def bf_tx_status_get(corr, beam):
    #     """
    #     Returns boolean true/false if the beamformer is currently outputting data.
    #     :param beam:
    #     :return: True/False
    #     """
    #     rv = True
    #     mask = [bf_read_int(corr, beam=beam, destination='filter', antennas=None)]
    #     # look to see if any portion in enabled
    #     if mask.count(1) != 0:
    #         rv = rv
    #     else:
    #         rv = False
    #     return rv
    #
    #
    # # TODO no registers
    # def config_meta_output(corr, beams, dest_ip_str=None,
    #                        dest_port=None, issue_spead=True):
    #     """
    #     Configures the destination IP and port for SPEAD
    #     meta-data outputs. dest_port and dest_ip are
    #     optional parameters to override the config file
    #     defaults.
    #     :param beams:
    #     :param dest_ip_str:
    #     :param dest_port:
    #     :param issue_spead:
    #     :return:
    #     """
    #     for beam in beams:
    #         if dest_ip_str is None:
    #             rx_meta_ip_str = get_beam_param(beam, 'rx_meta_ip_str')
    #         else:
    #             rx_meta_ip_str = dest_ip_str
    #             set_beam_param(beam, 'rx_meta_ip_str', dest_ip_str)
    #             # set_beam_param(beam, 'rx_meta_ip', struct.unpack('>L', socket.inet_aton(dest_ip_str))[0])
    #         if dest_port is None:
    #             rx_meta_port = int(get_beam_param(beam, 'rx_udp_port'))
    #         else:
    #             rx_meta_port = dest_port
    #         corr.logger.info("Destination for SPEAD meta data transmitter "
    #                          "for beam %s changed. New destination "
    #                          "IP = %s, port = %d"
    #                          % (beam, rx_meta_ip_str, int(rx_meta_port)))
    #         # reissue all SPEAD meta-data to new receiver
    #         if issue_spead:
    #             spead_bf_issue_all(corr, beam)
    #
    #
    # # TODO no destination register
    # def config_udp_output(corr, beams, frequencies,
    #                       dest_ip_str=None, dest_port=None, issue_spead=True):
    #         """
    #         Configures the destination IP and port for B
    #         engine data outputs. dest_port and dest_ip
    #         are optional parameters to override the config
    #         file defaults.
    #         :param beams: str
    #         :param dest_ip_str:
    #         :param dest_port:
    #         :param issue_spead: bool
    #         :return: <nothing>
    #         """
    #         fft_bins = frequency2fft_bin(corr, frequencies)
    #         for beam in beams:
    #             beam_idx = beam2index(corr, beams=beam)
    #             if dest_ip_str is None:
    #                 rx_udp_ip_str = get_beam_param(corr, beam, 'rx_udp_ip_str')
    #             else:
    #                 rx_udp_ip_str = dest_ip_str
    #             if dest_port is None:
    #                 rx_udp_port = get_beam_param(corr, beam, 'rx_udp_port')
    #             else:
    #                 rx_udp_port = dest_port
    #             dest_ip = tengbe.IpAddress.str2ip(corr.configd['bengine']
    #                                               ['bf_rx_meta_ip_str_beam%i' % beam_idx[0]])
    #
    #             # restart if currently transmitting
    #             restart = bf_tx_status_get(corr, beam)
    #             if restart:
    #                 bf_tx_stop(corr, beam)
    #
    #             # write ip/port
    #             THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beam_port', (rx_udp_port, beam)),)
    #             THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beam_ip', (dest_ip, beam)),)
    #
    #             # each beam output from each beamformer group can be configured differently
    #             corr.logging.info("Beam %s configured to output to %s:%i." % (beam, rx_udp_ip_str, int(rx_udp_port)))
    #             if issue_spead:
    #                 spead_destination_meta_issue(corr, beam)
    #             if restart:
    #                 tx_start(corr, beam)
    #
    #
    # # TODO might be obsolete
    # def set_passband(corr, beams, center_frequency=None,
    #                  bandwidth=None, spead_issue=True):
    #     """
    #     sets the center frequency and/or bandwidth for the specified beams
    #     :param beams:
    #     :param center_frequency:
    #     :param bandwidth:
    #     :param spead_issue:
    #     :return:
    #     """
    #     for beam in beams:
    #         # parameter checking
    #         if center_frequency is None:
    #             cf = float(get_beam_param(corr, beam, 'center_frequency'))
    #         else:
    #             cf = center_frequency
    #         if bandwidth is None:
    #             b = float(get_beam_param(corr, beam, 'bandwidth'))
    #         else:
    #             b = bandwidth
    #         cf_actual, b_actual = cf_bw2cf_bw(corr, cf, b)
    #         if center_frequency is not None:
    #             corr.logger.info('center frequency for beam %s set to %i Hz' % (beam, cf_actual))
    #         if bandwidth is not None:
    #             corr.logger.info('Bandwidth for beam %s set to %i Hz' % (beam, b_actual))
    #         if center_frequency is not None or bandwidth is not None:
    #             # restart if currently transmitting
    #             restart = bf_tx_status_get(corr, beam)
    #             if restart:
    #                 bf_tx_stop(corr, beam)
    #             # issue related spead meta data
    #             if restart:
    #                 corr.logger.info('Restarting beam %s with new passband parameters' % beam)
    #                 tx_start(corr, beam)
    #
    #
    # def get_passband(corr, beam):
    #     """
    #     gets the center frequency and bandwidth for the specified beam
    #     :param beam:
    #     :return:
    #     """
    #     # parameter checking
    #     cf = get_beam_param(corr, beam, 'center_frequency')
    #     b = get_beam_param(corr, beam, 'bandwidth')
    #     cf_actual, b_actual = cf_bw2cf_bw(corr, cf, b)
    #     return cf_actual, b_actual
    #
    #
    # def get_n_chans(corr, beam):
    #     """
    #     gets the number of active channels for the specified beam
    #     :param beam:
    #     :return:
    #     """
    #     fft_bin_bandwidth = get_fft_bin_bandwidth(corr, )
    #     cf, bw = get_passband(corr, beam)
    #     n_chans = int(bw/fft_bin_bandwidth)
    #     return n_chans
    #
    #
    # def weights_default_get(corr, beams, antennas):
    #     """
    #     Fetches the default weights configuration from the config file and returns
    #     a list of the weights for a given beam and antenna.
    #     :param beams: strings
    #     :param antennas:
    #     :return: dictionary with beam%i_ant%i keys
    #     """
    #     weight_default = corr.configd['bengine']['bf_weights_default']
    #     weights = dict()
    #     if weight_default == 'coef':
    #         for beam in beams:
    #             beam_idx = beam2index(corr, beam)[0]
    #             for ant in antennas:
    #                 weight = get_beam_param(corr, beam, 'weight_ant%i' % ant)
    #                 weights.update({'beam%i_ant%i' % (beam_idx, ant): int(weight)})
    #     else:
    #         raise corr.logger.error('Your default beamformer calibration '
    #                                 'type, %s, is not understood.'
    #                                 % weight_default)
    #     return weights
    #
    #
    # def weights_default_set(corr, beam, antenna=0):
    #     """
    #     Set the default weights configuration from the config file
    #     :param beam: for single beam in str form
    #     :param ant_str: for single antenna in int form
    #     :return:
    #     """
    #     beam_idx = beam2index(corr, beam)[0]
    #     weights = weights_default_get(corr, beams=[beam],
    #                                   antennas=[antenna])
    #     # set the antenna
    #     THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
    #                        target_function=('write_antenna', [antenna]))
    #     THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
    #                        target_function=('write_value_in',
    #                                         [weights['beam%i_ant%i'
    #                                                  % (beam_idx, antenna)]]))
    #
    #
    # def weights_get(corr, beams, antennas, default=True):
    #     """
    #     Retrieves the calibration settings currently programmed
    #     in all b-engines for the given beam and antenna or
    #     retrieves from config file.
    #     :param beam: for single beam in str form
    #     :param antenna: for single antenna in int form
    #     :param default: True for default False for
    #                    current weights
    #     :return:
    #     """
    #     if default:
    #         weights = weights_default_get(corr, beams=[beams], antennas=antennas)
    #     else:
    #         weights = dict()
    #         for beam in beams:
    #             for ant in antennas:
    #                 beam_char = beam2index(corr, beams=beam)[0]
    #                 beam_idx = beam2index(corr, beam)[0]
    #                 ant_char = '%i%c' % (ant, beam_char)
    #                 weight = bf_read_int(corr, beam,
    #                                      destination='calibrate',
    #                                      antennas=ant_char)
    #                 weights.update({'beam%i_ant%i'
    #                                 % (beam_idx, ant): int(weight)})
    #     return weights
    #
    #
    # def weights_set(corr, beam, antenna=0, coeffs=None,
    #                 spead_issue=True):
    #     """
    #     Set given beam and antenna calibration settings
    #     to given co-efficients.
    #     :param corr:
    #     :param beam:
    #     :param antennas:
    #     :param coeffs:
    #     :param spead_issue:
    #     :return:
    #     """
    #     if coeffs is None:
    #         weights_default_set(corr, beam, antenna=antenna)
    #     elif len(coeffs) == 1:  # we set a single value
    #         # write final vector to calibrate block
    #         # set the antenna
    #         beam_char = beam2index(corr, beams=beam)[0]
    #         ant = '%i%c' % (antenna, beam_char)
    #         bf_write_value(corr, 'calibrate', coeffs[0], beams=beam, antennas=ant)
    #     else:
    #         corr.logger.error('Your coefficient %s is not recognised.' % coeffs)
    #     if spead_issue:
    #         spead_weights_meta_issue(corr, beam)
    #
    # # def spead_issue_meta(self):
    # #         """
    # #         All FxCorrelators issued SPEAD in the same way, with tweakings that are implemented by the child class.
    # #         :return: <nothing>
    # #         """
    # #         if self.meta_destination is None:
    # #             logging.info('SPEAD meta destination is still unset, NOT sending metadata at this time.')
    # #             return
    # #         # make a new SPEAD transmitter
    # #         del self.spead_tx, self.spead_meta_ig
    # #         self.spead_tx = spead.Transmitter(spead.TransportUDPtx(*self.meta_destination))
    # #         # update the multicast socket option to use a TTL of 2,
    # #         # in order to traverse the L3 network on site.
    # #         ttl_bin = struct.pack('@i', 2)
    # #         self.spead_tx.t._udp_out.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl_bin)
    # #         #mcast_interface = self.configd['xengine']['multicast_interface_address']
    # #         #self.spead_tx.t._udp_out.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF,
    # #         #                                    socket.inet_aton(mcast_interface))
    # #         # self.spead_tx.t._udp_out.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP,
    # #         #                                     socket.inet_aton(txip_str) + socket.inet_aton(mcast_interface))
    # #         # make the item group we're going to use
    # #         self.spead_meta_ig = spead.ItemGroup()
    # #
    # #         # TODO hard-coded !!!!!!! :(
    #
    # #         # spead_ig.add_item(name='beamweight_MyAntStr', id=0x2000+inputN,
    # #         #                        description='',
    # #         #                        shape=[], fmt=spead.mkfmt(('u', 32)),
    # #         #                        init_val=)
    # #
    # #         # spead_ig.add_item(name='incoherent_sum', id=0x3000,
    # #         #                        description='',
    # #         #                        shape=[], fmt=spead.mkfmt(('u', 32)),
    # #         #                        init_val=)
    # #
    # #         # spead_ig.add_item(name='bf_MyBeamName', id=0xb000+beamN,
    # #         #                        description='',
    # #         #                        shape=[], format=[('u', SPEAD_ADDRSIZE)],
    # #         #                        init_val=)
    # #
    # #         self.spead_tx.send_heap(self.spead_meta_ig.get_heap())
    # #         self.logger.info('Issued SPEAD data descriptor to %s:%i.' % (self.meta_destination[0],
    # #                                                                      self.meta_destination[1]))
