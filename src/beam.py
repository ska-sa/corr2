import numpy
import logging
from casperfpga import utils as fpgautils

import fxcorrelator_speadops as speadops
from data_stream import SPEADStream, BEAMFORMER_FREQUENCY_DOMAIN
from utils import parse_output_products

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

LOGGER = logging.getLogger(__name__)


class Beam(SPEADStream):
    def __init__(self, name, index, destination):
        """
        A frequency-domain tied-array beam
        :param name - a string for the beam name
        :param index - the numerical beam index on the bhosts
        :param destination - where should the beam data go?
        :return:
        """
        self.index = index
        self.hosts = []

        #self.partitions_total = -1
        #self.partitions_per_host = -1
        #self.partitions = []
        #self.partitions_active = []
        #self.partitions_by_host = []

        self.center_freq = None
        self.bandwidth = None

        self.xeng_acc_len = None
        self.chans_total = None
        self.beng_per_host = None
        self.chans_per_partition = None

        self.source_streams = None
        self.quant_gain = None
        self.source_poly = None

        self.speadops = None

        super(Beam, self).__init__(
            name, BEAMFORMER_FREQUENCY_DOMAIN, destination)

        LOGGER.info('Beam %i:%s created okay' % (
            self.index, self.name))

    @classmethod
    def from_config(cls, beam_key, bhosts, config, fengops, speadops):
        """

        :param beam_key:
        :param bhosts:
        :param config:
        :param fengops:
        :param speadops:
        :return:
        """
        # number of b-engines in the system
        num_beng = int(config['xengine']['x_per_fpga']) * len(bhosts)

        # look for the section matching the name
        beam_dict = config[beam_key]

        beam_product, beam_stream_address = parse_output_products(beam_dict)
        assert len(beam_product) == 1, 'Currently only single beam products ' \
                                       'supported.'
        beam_name = beam_product[0]
        beam_address = beam_stream_address[0]
        if beam_address.ip_range != 1:
            raise RuntimeError(
                'The beam\'s given address range (%s) must be one, a starting'
                'base address.' % beam_address)
        beam_address.ip_range = num_beng

        obj = cls(beam_name, int(beam_dict['stream_index']), beam_address)
        obj.hosts = bhosts
        obj.speadops = speadops
        #obj.partitions_per_host = int(config['xengine']['x_per_fpga'])
        #obj.partitions_total = obj.partitions_per_host * len(obj.hosts)
        #obj.partitions = range(0, obj.partitions_total)
        #obj.partitions_active = []
        #obj.partitions_by_host = [
        #    obj.partitions[b:b+obj.partitions_per_host]
        #    for b in range(0, obj.partitions_total, obj.partitions_per_host)
        #]

        obj.center_freq = float(beam_dict['center_freq'])
        obj.bandwidth = float(beam_dict['bandwidth'])

        obj.xeng_acc_len = int(config['xengine']['xeng_accumulation_len'])
        obj.chans_total = int(config['fengine']['n_chans'])
        obj.beng_per_host = int(config['xengine']['x_per_fpga'])
        chans_per_host = obj.chans_total / len(obj.hosts)
        obj.chans_per_partition = chans_per_host / obj.beng_per_host

        # link source streams to weights
        weights = {}
        if 'source_weights' in beam_dict:
            # OLD STYLE
            for weight in beam_dict['source_weights'].strip().split(','):
                _split = weight.strip().split(':')
                input_name = _split[0]
                input_weight = float(_split[1])
                weights[input_name] = input_weight
        else:
            # NEW STYLE - same as eqs for F-engines
            for key in beam_dict:
                if key.startswith('weight_'):
                    input_name = key.replace('weight_', '')
                    input_weight = float(beam_dict[key])
                    weights[input_name] = input_weight
        obj.source_streams = {}
        source_index = 0
        for input_name, input_weight in weights.items():
            match = None
            for fengine in fengops.fengines:
                if fengine.name == input_name:
                    match = fengine
                    break
            if match is None:
                raise RuntimeError('beam %s has a weight given for input %s,'
                                   'but no matching F-engine output found'
                                   'with that name.' % (obj.name, input_name))
            obj.source_streams[match] = {'weight': input_weight,
                                         'index': source_index}
            source_index += 1
        obj.set_source(fengops.data_stream.destination)
        obj.quant_gain = 1
        obj.source_poly = []
        obj.descriptors_setup()
        return obj

    def __str__(self):
        return 'Beam %i:%s -> %s' % (self.index, self.name, self.destination)

    def initialise(self):
        """
        Set up the beam for first operation after programming.
        Anything that needs to be done EVERY TIME a new correlator is
        instantiated should go in self.configure
        :return:
        """

        # # DEBUG
        # THREADED_FPGA_OP(
        #     self.hosts, timeout=5,
        #     target_function=(
        #         lambda fpga_:
        #         fpga_.registers.bf_config.write(tvg_sel=True), [], {}))

        # set the beam destination registers
        self.write_destination()

        # set the weights for this beam
        THREADED_FPGA_FUNC(self.hosts, 60, ('beam_weights_set', [self], {}))

        # set the quantiser gains for this beam
        THREADED_FPGA_FUNC(self.hosts, 60, ('beam_quant_gains_set',
                                           [self, self.quant_gain], {}))

        LOGGER.info('Beam %i:%s: initialised okay' % (
            self.index, self.name))

    def configure(self):
        """
        Configure the beam when starting a correlator instance
        :return:
        """
        # set the active partitions to the partitions set in hardware
        #self.partitions_active = self.partitions_current()

        # set the default gain to one
        self.set_quant_gains(1.0)

    def tx_enable(self):
        """
        Start transmission of data streams from the b-engines
        :return:
        """
        #if len(self.partitions_active) <= 0:
        #    LOGGER.info('Beam %i:%s: no partitions to enable.' %
        #                (self.index, self.name))
        #    return
        self.descriptors_issue()
        reg_name = 'bf%i_config' % self.index
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(
                lambda fpga_:
                fpga_.registers[reg_name].write(txen=True), [], {}))
        self.tx_enabled = True
        LOGGER.info('Beam %i:%s output enabled.' % (self.index, self.name))

    def tx_disable(self):
        """
        Stop transmission of data streams from the b-engines
        :return:
        """
        #if len(self.partitions_active) == 0:
        #    LOGGER.info('Beam %i:%s: no partitions to disable.' %
        #                (self.index, self.name))
        #    return
        reg_name = 'bf%i_config' % self.index
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(
                lambda fpga_:
                fpga_.registers[reg_name].write(txen=False), [], {}))
        self.tx_enabled = False
        LOGGER.info('Beam %i:%s output disabled.' % (self.index, self.name))

    def descriptors_setup(self):
        """
        Set up the data descriptors for an B-engine stream.
        :return:
        """
        if not self.xeng_acc_len:
            # wait until it's been set up
            return
        speadops.item_0x1600(self.descr_ig)
        # id is 0x5 + 12 least sig bits id of each beam
        beam_data_id = 0x5000
        speadops.add_item(
            self.descr_ig,
            name='bf_raw', id=beam_data_id,
            description='Channelised complex data. Real comes before imaginary.'
                        'A number of consecutive samples from each channel are '
                        'in the same packet. The heap offset and frequency '
                        'SPEAD items can be used to calculate the exact '
                        'frequency in relation to the spectrum',
            dtype=numpy.int8,
            shape=[self.chans_per_partition, self.xeng_acc_len, 2])

        speadops.add_item(
            self.descr_ig, name='frequency', id=0x4103,
            description=
            'Identifies the first channel in the band of frequency channels '
            'in the SPEAD heap',
            shape=[], format=[('u', speadops.SPEAD_ADDRSIZE)])

    def write_destination(self):
        """
        Write the destination to the hardware.
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, 5, ('beam_destination_set', [self], {}))

#    def _check_partitions(self, partitions):
#        """
#        Does a given list of partitions make sense against this beam's
#        partitions?
#        :param partitions:
#        :return:
#        """
#        # check to see whether the partitions to be activated are contiguous
#        for ctr in range(0, len(partitions)-1):
#            if partitions[ctr] != partitions[ctr+1] - 1:
#                raise ValueError('Currently only contiguous partition '
#                                 'ranges are supported.')
#        # does the list of partitions make sense?
#        if max(partitions) > max(self.partitions):
#            raise ValueError('Partitions > max(partitions) make no sense')
#        if min(partitions) < min(self.partitions):
#            raise ValueError('Partitions < 0 make no sense')

#    def active_channels(self):
#        """
#        How many channels are active in this beam?
#        :return:
#        """
#        return self.chans_per_partition * len(self.partitions_active)

#    def partitions_deactivate(self, partitions=None):
#        """
#        Deactive one or more partitions
#        :param partitions: a list of partitions to deactivate
#        :return: True is partitions were changed
#        """
#        if not self.partitions_active:
#            LOGGER.info('Beam %i:%s - all partitions already deactive' % (
#                self.index, self.name))
#            return False
#        if not partitions:
#            LOGGER.info('Beam %i:%s - deactivating all active partitions' % (
#                self.index, self.name))
#            self.partitions_active = []
#            self._partitions_control_update()
#            return True
#        # make the new active selection
#        partitions = set(partitions)
#        currently_active = set(self.partitions_active)
#        new_active = list(currently_active.difference(partitions))
#        if new_active != list(currently_active):
#            LOGGER.info('Beam %i:%s - applying new active partitions' % (
#                self.index, self.name))
#            return self.partitions_activate(new_active)
#        else:
#            LOGGER.info('Beam %i:%s - no changes to active partitions' % (
#                self.index, self.name))
#            return False
#
#    def partitions_activate(self, partitions=None):
#        """
#        Activate one or more partitions.
#        :param partitions: a list of partitions to activate
#        :return: True if active partitions changed
#        """
#        if not partitions:
#            LOGGER.info('Beam %i:%s - activating all partitions' % (
#                self.index, self.name))
#            partitions = self.partitions[:]
#        if partitions == self.partitions_active:
#            LOGGER.info('Beam %i:%s - specd partitions already active' % (
#                self.index, self.name))
#            return False
#        self._check_partitions(partitions)
#        self.partitions_active = partitions[:]
#        self._partitions_control_update()
#        LOGGER.info('Beam %i:%s - active partitions: %s' % (
#                self.index, self.name, self.partitions_active))
#        return True
#
#    def _partitions_control_update(self):
#        """
#        Start transmission of active partitions on this beam
#        :return:
#        """
#        THREADED_FPGA_FUNC(self.hosts, 5,
#                           ('beam_partitions_control', [self], {}))
#
#    def partitions_current(self):
#        results = THREADED_FPGA_FUNC(self.hosts, 5,
#                                     ('beam_partitions_read', [self], {}))
#        curr = []
#        for host in self.hosts:
#            curr.extend(results[host.host])
#        rv = []
#        for ctr, cval in enumerate(curr):
#            if cval == 1:
#                rv.append(ctr)
#        return rv

    @property
    def source_names(self):
        tmp = [source.name for source in self.source_streams.keys()]
        tmp.sort()
        return tmp

    def get_source(self, source_name):
        """
        Get an input source for this beam, given a name.
        :param source_name:
        :return:
        """
        for source in self.source_streams.keys():
            if source.name == source_name:
                return source
        raise ValueError('No such input: %s. Available inputs to this beam: '
                         '%s' % (source_name, self.source_names))

    def set_weights(self, input_name, new_weight, force=False):
        """
        Set the weight for this beam for a given input
        :param input_name: which source/input we're looking for
        :param new_weight: the new weight to apply to this input/source
        :param force: force the write, even if the stored value is the same
        :return:
        """
        input_source = self.get_source(input_name)
        source_info = self.source_streams[input_source]
        source_weight = source_info['weight']
        if (new_weight == source_weight) and (not force):
            LOGGER.info('Beam %i:%s: %s weight already %.3f' % (
                self.index, self.name, input_name, new_weight))
            return False
        source_info['weight'] = new_weight
        THREADED_FPGA_FUNC(
            self.hosts, 5, ('beam_weights_set',
                            [self, [input_source.name]], {}))
        LOGGER.info('Beam %i:%s: %s weight set to %.3f' % (
            self.index, self.name, input_name, new_weight))
        return True

    def get_weights(self, input_name=None):
        """
        Get the current weight(s) associated with an input on this beam.
        :param input_name: which source/input we're looking for
        :return:
        """
        if input_name is None:
            return {nptnm: self.get_weights(nptnm)
                    for nptnm in self.source_names}
        input_source = self.get_source(input_name)
        d = THREADED_FPGA_FUNC(
            self.hosts, 5, ('beam_weights_get',
                            [self, [input_source.name]], {}))
        ref = d[d.keys()[0]][0]
        for dhost, dval in d.items():
            for vctr, v in enumerate(dval[0]):
                if v != ref[vctr]:
                    raise RuntimeError(
                        'Beamweights for beam %s input %s differ across '
                        'hosts!?' % (self.name, input_name))
        for v in ref:
            if v != ref[0]:
                raise RuntimeError('Beamweights for beam %s input %s differ '
                                   'across b-engs!?' % (self.name, input_name))
        source_info = self.source_streams[input_source]
        source_info['weight'] = ref[0]
        return ref[0]

    def set_quant_gains(self, new_quant_gain, force=False):
        """
        Set the quantiser gain for this beam for a given input
        :param new_quant_gain: the new gain to apply to this input/source
        :param force: force the write, even if the stored value is the same
        :return:
        """
        if (new_quant_gain == self.quant_gain) and (not force):
            LOGGER.info('Beam %i:%s: quantiser gain already %.3f' % (
                self.index, self.name, new_quant_gain))
            return False
        rv = THREADED_FPGA_FUNC(
            self.hosts, 5, ('beam_quant_gains_set', [self, new_quant_gain], {}))
        gain_set = rv.values()[0]
        self.quant_gain = gain_set
        LOGGER.info('Beam %i:%s: quantiser gain: %.3f specified, set to '
                    '%.3f' % (self.index, self.name, new_quant_gain, gain_set))
        return True

    def get_quant_gains(self):
        """
        Get the current quantiser gain(s) associated with an input on this beam.
        :return:
        """
        d = THREADED_FPGA_FUNC(
            self.hosts, 5, ('beam_quant_gains_get', [self], {}))
        ref_gain = d[d.keys()[0]]
        for dhost, dval in d.items():
            if dval != ref_gain:
                raise RuntimeError(
                    'Quantiser gains for beam %s differ across '
                    'hosts!? %.3f != %.3f' % (self.name, dval, ref_gain))
        if self.quant_gain != ref_gain:
            LOGGER.warning(
                'Beam {idx}:{beam} quant gain variable set to {sw}, but '
                'hardware says {hw}'.format(
                    idx=self.index, beam=self.name,
                    sw=self.quant_gain, hw=ref_gain))
        return ref_gain

#    def _bandwidth_to_partitions(self, bandwidth, centerfreq):
#        """
#        Given a bandwidth and center frequency, return the relevant
#        partitions that should be activated.
#        :param bandwidth: in hz
#        :param centerfreq: in hz
#        :return: a list of partition numbers
#        """
#        # configured freq range
#        startbw = self.center_freq - (self.bandwidth / 2.0)
#        endbw = self.center_freq + (self.bandwidth / 2.0)
#        # given freq range
#        startgiven = centerfreq - (bandwidth / 2.0)
#        endgiven = centerfreq + (bandwidth / 2.0)
#        # check
#        if (startgiven < startbw) or (endgiven > endbw):
#            raise ValueError('Given freq range (%.2f, %.2f) falls outside '
#                             'beamformer range (%.2f, %.2f)' %
#                             (startgiven, endgiven, startbw, endbw))
#        # bb and partitions
#        bbstart = startgiven - startbw
#        bbend = endgiven - startbw
#        hz_per_partition = self.bandwidth / self.partitions_total
#        part_start = int(numpy.floor(bbstart / hz_per_partition))
#        part_end = int(numpy.ceil(bbend / hz_per_partition))
#        return range(part_start, part_end)
#
#    def _partitions_to_bandwidth(self, partitions=None):
#        """
#        Given a list of partitions, return the corresponding cf and bw
#        :param partitions: a list of partitions
#        :return: tuple, (bw, cf)
#        """
#        if not partitions:
#            partitions = self.partitions_active
#        if len(partitions) == 0:
#            return 0, 0
#        hz_per_partition = self.bandwidth / self.partitions_total
#        rv_bw = hz_per_partition * len(partitions)
#        first_part = partitions[0]
#        part_start_hz = first_part * hz_per_partition
#        actual_start_hz = self.center_freq - (self.bandwidth / 2.0)
#        rv_cf = actual_start_hz + part_start_hz + (rv_bw / 2.0)
#        return rv_bw, rv_cf

#    def set_beam_bandwidth(self, bandwidth, centerfreq):
#        """
#        Set the partitions for this beam based on a provided bandwidth
#        and center frequency.
#        :param bandwidth: the bandwidth, in hz
#        :param centerfreq: the center freq of this band, in hz
#        :return: tuple, the set (bw, cf) for that beam
#        """
#        currbw, currcf = self.get_beam_bandwidth()
#        if (currbw == bandwidth) and (currcf == centerfreq):
#            LOGGER.info('Beam %s: bw, cf already set to %.3f, %.3f' % (
#                self.name, bandwidth, centerfreq))
#            return currbw, currcf
#        parts = self._bandwidth_to_partitions(bandwidth, centerfreq)
#        LOGGER.info('BW(%.3f) CF(%.3f) translates to partitions: %s' %
#                    (bandwidth, centerfreq, parts))
#        self.partitions_activate(parts)
#        self.descriptors_setup()
#        self.descriptors_issue()
#        return self.get_beam_bandwidth()
#
#    def get_beam_bandwidth(self):
#        """
#        Get the partitions for this beam i.t.o. bandwidth
#        and center frequency.
#        :return: (beam bandwidth, beam_cf)
#        """
#        (bw, cf) = self._partitions_to_bandwidth()
#        LOGGER.info('Partitions %s give BW(%.3f) CF(%.3f)' %
#                    (self.partitions_active, bw, cf))
#        return bw, cf
#
## end
