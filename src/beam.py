import numpy
import logging
from casperfpga import utils as fpgautils

from fxcorrelator_speadops import SPEAD_ADDRSIZE
from data_product import DataProduct, BEAMFORMER_FREQUENCY_DOMAIN
from net_address import NetAddress

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

LOGGER = logging.getLogger(__name__)


class Beam(object):
    def __init__(self, beam_name, beam_index):
        """
        Make a beam from the config file section
        :param beam_name - a string for the beam name
        :param beam_index - the numerical beam index on the bhosts
        :return:
        """
        self.name = beam_name
        self.index = beam_index
        self.hosts = []

        self.data_product = None
        self.speadops = None

        self.partitions_total = -1
        self.partitions_per_host = -1
        self.partitions = []
        self.partitions_active = []
        self.partitions_by_host = []

        self.center_freq = None
        self.bandwidth = None

        self.xeng_acc_len = None
        self.n_chans = None
        self.beng_per_host = None

        self.source_weights = None
        self.source_labels = None
        self.source_poly = None

        LOGGER.info('Beam %i:%s created okay' % (
            self.index, self.name))

    @classmethod
    def from_config(cls, beam_name, bhosts, config, speadops):
        # look for the section matching the name
        beam_dict = config['beam_%s' % beam_name]
        obj = cls(beam_name, int(beam_dict['stream_index']))
        obj.hosts = bhosts
        obj.speadops = speadops

        obj.partitions_per_host = int(config['xengine']['x_per_fpga'])
        obj.partitions_total = obj.partitions_per_host * len(obj.hosts)
        obj.partitions = range(0, obj.partitions_total)
        obj.partitions_active = []
        obj.partitions_by_host = [
            obj.partitions[b:b+obj.partitions_per_host]
            for b in range(0, obj.partitions_total, obj.partitions_per_host)
        ]

        obj.center_freq = float(beam_dict['center_freq'])
        obj.bandwidth = float(beam_dict['bandwidth'])

        obj.xeng_acc_len = int(config['xengine']['xeng_accumulation_len'])
        obj.n_chans = int(config['fengine']['n_chans'])
        obj.beng_per_host = int(config['xengine']['x_per_fpga'])

        data_addr = NetAddress(beam_dict['data_ip'], beam_dict['data_port'])
        meta_addr = NetAddress(beam_dict['meta_ip'], beam_dict['meta_port'])
        obj.data_product = DataProduct(
            name=beam_name,
            category=BEAMFORMER_FREQUENCY_DOMAIN,
            destination=data_addr,
            meta_destination=meta_addr,
            destination_cb=obj.set_beam_destination,
            meta_destination_cb=obj.spead_meta_issue_all,
            tx_enable_method=obj.tx_enable,
            tx_disable_method=obj.tx_disable)

        weight_list = beam_dict['source_weights'].strip().split(',')
        obj.source_weights = []
        obj.source_labels = []
        for weight in weight_list:
            _split = weight.strip().split(':')
            input_name = _split[0]
            input_weight = float(_split[1])
            obj.source_labels.append(input_name)
            obj.source_weights.append(input_weight)
        obj.source_poly = []
        return obj

    def __str__(self):
        return 'Beam %i:%s - %s' % (self.index, self.name, self.data_product)

    def initialise(self):
        """
        Set up the beam for first operation after programming.
        Anything that needs to be done EVERY TIME a new correlator is
        instantiated should go in self.configure
        :return:
        """
        # set the beam index
        THREADED_FPGA_FUNC(self.hosts, 5, ('beam_index_set', [self], {}))

        # set the beam destination registers
        self.set_beam_destination(None)

        # set the weights for this beam
        THREADED_FPGA_FUNC(self.hosts, 5, ('beam_weights_set', [self], {}))

        LOGGER.info('Beam %i:%s: initialised okay' % (
            self.index, self.name))

    def configure(self):
        """
        Configure the beam when starting a correlator instance
        :return:
        """
        # set the active partitions to the partitions set in hardware
        self.partitions_active = self.partitions_current()

    def tx_enable(self, data_product):
        """
        Start transmission of data products from the b-engines
        :return:
        """
        self.tx_control_update()
        LOGGER.info('Beam %i:%s output enabled.' % (self.index, self.name))

    def tx_disable(self, data_product):
        """
        Stop transmission of data products from the b-engines
        :return:
        """
        self.partitions_deactivate()
        self.tx_control_update()
        LOGGER.info('Beam %i:%s output disabled.' % (self.index, self.name))

    def set_beam_destination(self, data_product):
        THREADED_FPGA_FUNC(self.hosts, 5, ('beam_destination_set', [self], {}))
        self.spead_meta_update_destination()
        self.spead_meta_transmit_all()

    def _check_partitions(self, partitions):
        """
        Does a given list of partitions make sense against this beam's
        partitions?
        :param partitions:
        :return:
        """
        # check to see whether the partitions to be activated are contiguous
        for ctr in range(0, len(partitions)-1):
            if partitions[ctr] != partitions[ctr+1] - 1:
                raise ValueError('Currently only contiguous partition '
                                 'ranges are supported.')
        # does the list of partitions make sense?
        if max(partitions) > max(self.partitions):
            raise ValueError('Partitions > max(partitions) make no sense')
        if min(partitions) < min(self.partitions):
            raise ValueError('Partitions < 0 make no sense')

    def partitions_deactivate(self, partitions=None):
        """
        Deactive one or more partitions
        :param partitions: a list of partitions to deactivate
        :return: True is partitions were changed
        """
        if not self.partitions_active:
            LOGGER.info('Beam %i:%s - all partitions already deactive' % (
                self.index, self.name))
            return False
        if not partitions:
            LOGGER.info('Beam %i:%s - deactivating all active partitions' % (
                self.index, self.name))
            self.partitions_active = []
            return True
        # make the new active selection
        partitions = set(partitions)
        currently_active = set(self.partitions_active)
        new_active = list(currently_active.difference(partitions))
        if new_active != list(currently_active):
            LOGGER.info('Beam %i:%s - applying new active partitions' % (
                self.index, self.name))
            return self.partitions_activate(new_active)
        else:
            LOGGER.info('Beam %i:%s - no changes to active partitions' % (
                self.index, self.name))
            return False

    def partitions_activate(self, partitions=None):
        """
        Activate one or more partitions.
        :param partitions: a list of partitions to activate
        :return: True if active partitions changed
        """
        if not partitions:
            LOGGER.info('Beam %i:%s - activating all partitions' % (
                self.index, self.name))
            partitions = self.partitions[:]
        if partitions == self.partitions_active:
            LOGGER.info('Beam %i:%s - specd partitions already active' % (
                self.index, self.name))
            return False
        self._check_partitions(partitions)
        self.partitions_active = partitions[:]

        # TODO - send SPEAD metadata about bandwidth and cf

        LOGGER.info('Beam %i:%s - active partitions: %s' % (
                self.index, self.name, self.partitions_active))
        return True

    def partitions_current(self):
        results = THREADED_FPGA_FUNC(self.hosts, 5,
                                     ('beam_partitions_read', [self], {}))
        curr = []
        for host in self.hosts:
            curr.extend(results[host.host])
        rv = []
        for ctr, cval in enumerate(curr):
            if cval == 1:
                rv.append(ctr)
        return rv

    def tx_control_update(self):
        """
        Start transmission of active partitions on this beam
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, 5,
                           ('beam_partitions_control', [self], {}))

    def set_weights(self, input_name, new_weight):
        """
        Set the weight for this beam for a given input
        :return:
        """
        input_index = self.source_labels.index(input_name)
        if new_weight == self.source_weights[input_index]:
            LOGGER.info('Beam %i:%s: %s weight already %.3f' % (
                self.index, self.name, input_name, new_weight))
            return False
        self.source_weights[input_index] = new_weight
        THREADED_FPGA_FUNC(self.hosts, 5,
                           ('beam_weights_set', [self], {}))

        # TODO - send SPEAD metadata about weights

        LOGGER.info('Beam %i:%s: %s weight set to %.3f' % (
            self.index, self.name, input_name, new_weight))
        return True

    def get_weights(self, input_name):
        """
        Get the current weight(s) associated with an input on this beam.
        :param input_name:
        :return:
        """
        input_index = self.source_labels.index(input_name)
        return self.source_weights[input_index]

    def _bandwidth_to_partitions(self, bandwidth, centerfreq):
        """
        Given a bandwidth and center frequency, return the relevant
        partitions that should be activated.
        :param bandwidth: in hz
        :param centerfreq: in hz
        :return: a list of partition numbers
        """
        # configured freq range
        startbw = self.center_freq - (self.bandwidth / 2.0)
        endbw = self.center_freq + (self.bandwidth / 2.0)
        # given freq range
        startgiven = centerfreq - (bandwidth / 2.0)
        endgiven = centerfreq + (bandwidth / 2.0)
        # check
        if (startgiven < startbw) or (endgiven > endbw):
            raise ValueError('Given freq range (%.2f, %.2f) falls outside '
                             'beamformer range (%.2f, %.2f)' %
                             (startgiven, endgiven, startbw, endbw))
        # bb and partitions
        bbstart = startgiven - startbw
        bbend = endgiven - startbw
        hz_per_partition = self.bandwidth / self.partitions_total
        part_start = int(numpy.floor(bbstart / hz_per_partition))
        part_end = int(numpy.ceil(bbend / hz_per_partition))
        return range(part_start, part_end)

    def _partitions_to_bandwidth(self, partitions=None):
        """
        Given a list of partitions, return the corresponding cf and bw
        :param partitions: a list of partitions
        :return: tuple, (bw, cf)
        """
        if not partitions:
            partitions = self.partitions_active
        if len(partitions) == 0:
            return 0, 0
        hz_per_partition = self.bandwidth / self.partitions_total
        rv_bw = hz_per_partition * len(partitions)
        first_part = partitions[0]
        part_start_hz = first_part * hz_per_partition
        actual_start_hz = self.center_freq - (self.bandwidth / 2.0)
        rv_cf = actual_start_hz + part_start_hz + (rv_bw / 2.0)
        return rv_bw, rv_cf

    def set_beam_bandwidth(self, bandwidth, centerfreq):
        """
        Set the partitions for this beam based on a provided bandwidth
        and center frequency.
        :param bandwidth: the bandwidth, in hz
        :param centerfreq: the center freq of this band, in hz
        :return: tuple, the set (bw, cf) for that beam
        """
        currbw, currcf = self.get_beam_bandwidth()
        if (currbw == bandwidth) and (currcf == centerfreq):
            LOGGER.info('Beam %s: bw, cf already set to %.3f, %.3f' % (
                self.name, bandwidth, centerfreq))
            return
        parts = self._bandwidth_to_partitions(bandwidth, centerfreq)
        LOGGER.info('BW(%.3f) CF(%.3f) translates to partitions: %s' %
                    (bandwidth, centerfreq, parts))
        self.partitions_activate(parts)
        self.spead_meta_update_bandwidth()
        self.spead_meta_transmit_all()
        return self.get_beam_bandwidth()

    def get_beam_bandwidth(self):
        """
        Get the partitions for this beam i.t.o. bandwidth
        and center frequency.
        :return: (beam bandwidth, beam_cf)
        """
        (bw, cf) = self._partitions_to_bandwidth()
        LOGGER.info('Partitions %s give BW(%.3f) CF(%.3f)' %
                    (self.partitions_active, bw, cf))
        return bw, cf

    def update_labels(self, oldnames, newnames):
        """
        Update the input labels
        :return: True if anything changed, False if not
        """
        changes = False
        for oldname_pos, oldname in enumerate(oldnames):
            for ctr, srcname in enumerate(self.source_labels):
                if srcname == oldname:
                    LOGGER.info('Beam %i:%s: changed input %i label from '
                                '%s to %s' % (self.index, self.name, ctr,
                                              oldname, newnames[oldname_pos]))
                    self.source_labels[ctr] = newnames[oldname_pos]
                    changes = True
                    continue
        if changes:
            self.spead_meta_update_weights()
            self.spead_meta_update_labels()
            self.spead_meta_transmit_all()
        return changes

    def spead_meta_update_bandwidth(self):
        """
        Update the metadata regarding this beam's bandwidth
        :return:
        """
        bw, cf = self.get_beam_bandwidth()
        meta_ig = self.data_product.meta_ig
        meta_ig.add_item(
            name='bandwidth', id=0x1013,
            description='The analogue bandwidth in this beam data product.',
            shape=[], format=[('f', 64)],
            value=bw)

    def spead_meta_update_dataheap(self):
        """
        Update meta information about the beamformer data heap
        :return:
        """
        meta_ig = self.data_product.meta_ig
        n_bhosts = len(self.hosts)
        chans_per_host = self.n_chans / n_bhosts
        chans_per_partition = chans_per_host / self.beng_per_host
        beam_chans = chans_per_partition * len(self.partitions_active)
        # id is 0x5 + 12 least sig bits id of each beam
        beam_data_id = 0x5000 + self.index
        meta_ig.add_item(
            name='bf_raw', id=beam_data_id,
            description='Raw data for bengines in the system. Frequencies '
                        'are assembled from lowest frequency to highest '
                        'frequency. Frequencies come in blocks of values '
                        'in time order where the number of samples in a '
                        'block is given by xeng_acc_len (id 0x101F). Each '
                        'value is a complex number -- two (real and '
                        'imaginary) signed integers.',
            dtype=numpy.int8,
            shape=[beam_chans, self.xeng_acc_len, 2])
        LOGGER.info('Beam %i:%s - updated dataheap metadata' % (
            self.index, self.name))

    def spead_meta_update_beamformer(self):
        """
        Issues the SPEAD metadata packets containing the payload
        and options descriptors and unpack sequences.
        :return:
        """
        meta_ig = self.data_product.meta_ig

        # calculate a few things for this beam
        n_bhosts = len(self.hosts)
        n_bengs = self.beng_per_host * n_bhosts

        self.speadops.item_0x1007(sig=meta_ig)
        self.speadops.item_0x1009(sig=meta_ig)
        self.speadops.item_0x100a(sig=meta_ig)

        meta_ig.add_item(
            name='n_bengs', id=0x100F,
            description='The total number of B engines in the system.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=n_bengs)

        self.speadops.item_0x1020(sig=meta_ig)
        self.speadops.item_0x1027(sig=meta_ig)
        self.speadops.item_0x1045(sig=meta_ig)
        self.speadops.item_0x1046(sig=meta_ig)

        meta_ig.add_item(
            name='b_per_fpga', id=0x1047,
            description='The number of b-engines per fpga.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.beng_per_host)

        meta_ig.add_item(
            name='beng_out_bits_per_sample', id=0x1050,
            description='The number of bits per value in the beng output. '
                        'Note that this is for a single value, not the '
                        'combined complex value size.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=8)

        self.speadops.item_0x1600(sig=meta_ig)

        LOGGER.info('Beam %i:%s - updated beamformer metadata' % (
            self.index, self.name))

    def spead_meta_update_destination(self):
        """
        Update the SPEAD IGs to notify the receiver of changes to destination
        :return:
        """
        meta_ig = self.data_product.meta_ig
        meta_ig.add_item(
            name='rx_udp_port', id=0x1022,
            description='Destination UDP port for B engine output.',
            shape=[], format=[('u', SPEAD_ADDRSIZE)],
            value=self.data_product.destination.port)

        ipstr = numpy.array(str(self.data_product.destination.ip))
        meta_ig.add_item(
            name='rx_udp_ip_str', id=0x1024,
            description='Destination IP address for B engine output UDP '
                        'packets.',
            shape=ipstr.shape,
            dtype=ipstr.dtype,
            value=ipstr)
        LOGGER.info('Beam %i:%s - updated meta destination '
                    'metadata' % (self.index, self.name))

    def spead_meta_update_weights(self):
        """
        Update the weights in the BEAM SPEAD ItemGroups.
        :return:
        """
        meta_ig = self.data_product.meta_ig
        meta_ig.add_item(
            name='beamweight',
            id=0x2000,
            description='The unitless per-channel digital scaling '
                        'factors implemented prior to combining '
                        'antenna signals during beamforming for input '
                        'beam %s. Complex number real 32 bit '
                        'floats.' % self.name,
            shape=[len(self.source_weights)], format=[('i', 32)],
            value=self.source_weights)
        LOGGER.info('Beam %i:%s - updated weights metadata' % (
            self.index, self.name))

    def spead_meta_update_labels(self):
        """
        Update the labels in the BEAM SPEAD ItemGroups.
        :return:
        """
        meta_ig = self.data_product.meta_ig
        self.speadops.item_0x100e(sig=meta_ig)
        LOGGER.info('Beam %i:%s - updated label metadata' % (
            self.index, self.name))

    def spead_meta_update_all(self):
        """
        Update the IGs for all beams for all beamformer info
        :return:
        """
        self.spead_meta_update_beamformer()
        self.spead_meta_update_dataheap()
        self.spead_meta_update_destination()
        self.spead_meta_update_weights()
        self.spead_meta_update_labels()

    def spead_meta_transmit_all(self):
        """
        Transmit SPEAD metadata for all beams
        :return:
        """
        self.data_product.meta_transmit()

    def spead_meta_issue_all(self, data_product):
        """
        Issue = update + transmit
        """
        self.spead_meta_update_all()
        self.spead_meta_transmit_all()

