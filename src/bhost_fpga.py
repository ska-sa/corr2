"""
A BHost is an extension of an XHost. It contains memory and registers
to set up and control one or more beamformers.

Author: Jason Manley, Andrew Martens, Ruby van Rooyen, Monika Obrocka
"""

import logging
from xhost_fpga import FpgaXHost

LOGGER = logging.getLogger(__name__)


class FpgaBHost(FpgaXHost):
    def __init__(self, host, index, katcp_port=7147, boffile=None,
                 connect=True, config=None):
        # parent constructor
        FpgaXHost.__init__(self, host, index, katcp_port=katcp_port,
                           boffile=boffile, connect=connect, config=config)
        self.beng_per_host = int(self.config['x_per_fpga'])
        LOGGER.info('FpgaBHost %i:%s created' % (
            self.index, self.host))

    @classmethod
    def from_config_source(cls, hostname, index, katcp_port, config_source):
        boffile = config_source['bitstream']
        return cls(hostname, index, katcp_port=katcp_port, boffile=boffile,
                   connect=True, config=config_source)

    def beam_destination_set(self, beam):
        """
        Set the data destination for this beam.
        :param beam: The Beam() on which to act
        :return
        """
        beam_cfgreg = self.registers['bf%i_config' % beam.index]
        beam_ipreg = self.registers['bf%i_ip' % beam.index]
        beam_cfgreg.write(port=beam.data_stream.destination.port)
        beam_ipreg.write(ip=int(beam.data_stream.destination.ip))
        LOGGER.info('%s:%i: Beam %i:%s destination set to %s' % (
            self.host, self.index, beam.index, beam.name,
            beam.data_stream.destination))

    def beam_index_set(self, beam):
        """
        Set the beam index.
        :param beam: The Beam() on which to act
        :return:
        """
        beam_cfgreg = self.registers['bf%i_config' % beam.index]
        beam_cfgreg.write(beam_id=beam.index)
        LOGGER.info('%s:%i: Beam %i:%s index set - %i' % (
            self.host, self.index, beam.index, beam.name, beam.index))

    def beam_num_partitions_set(self, beam):
        """
        :param beam: The Beam() on which to act
        :return
        """
        beam_cfgreg = self.registers['bf%i_config' % beam.index]
        # in newer versions this moved to a different register
        if 'n_partitions' not in beam_cfgreg.field_names():
            beam_cfgreg = self.registers['bf%i_num_parts' % beam.index]
        numparts = len(beam.partitions_active)
        beam_cfgreg.write(n_partitions=numparts)
        LOGGER.debug('%s:%i: Beam %i:%s num_partitions set - %i' % (
            self.host, self.index, beam.index, beam.name, numparts))

    # def beam_partitions_set(self, beam):
    #     """
    #     :param beam: a Beam object
    #     :return
    #     """
    #     # partitions offsets must be worked out
    #     partition_start = self.index * self.beng_per_host
    #     beam_reg = self.registers['bf%i_partitions' % beam.index]
    #     beam_reg.write(partition0_offset=partition_start,
    #                    partition1_offset=partition_start+1,
    #                    partition2_offset=partition_start+2,
    #                    partition3_offset=partition_start+3)
    #     LOGGER.info('%s:%i: Beam %i:%s partitions set to %i:%i' % (
    #         self.host, self.index, beam.index, beam.name,
    #         partition_start, partition_start+self.beng_per_host-1))

    def beam_weights_set(self, beam, source_indices=None):
        """
        Set the beam weights for the given beam.
        :param beam: The Beam() on which to act
        :param source_indices: a list of the input/ant/source indices to set
        """
        if not source_indices:
            source_indices = range(len(beam.source_weights))
        for ant_ctr in source_indices:
            ant_weight = beam.source_weights[ant_ctr]
            self.registers.bf_value_in0.write(bw=ant_weight)
            for beng_ctr in range(0, self.beng_per_host):
                self.registers.bf_control.write(
                    stream=beam.index, beng=beng_ctr, antenna=ant_ctr)
                self.registers.bf_value_ctrl.write(bw='pulse')
                LOGGER.info('%s:%i: Beam %i:%s set beng(%i) antenna(%i) '
                            'weight(%.5f)' % (self.host, self.index,
                                              beam.index, beam.name,
                                              beng_ctr, ant_ctr, ant_weight))

    def beam_weights_get(self, beam, source_indices=None):
        """
        Get the beam weights for the given beam.
        :param beam: The Beam() on which to act
        :param source_indices: a list of the input/ant/source indices to get
        """
        if not source_indices:
            source_indices = range(len(beam.source_weights))
        rv = []
        for ant_ctr in source_indices:
            self.registers.bf_control.write(
                stream=beam.index, beng=0, antenna=ant_ctr)
            d = self.registers.bf_valout_bw1.read()['data']
            d.update(self.registers.bf_valout_bw0.read()['data'])
            drv = [d['bw%i' % beng_ctr] for beng_ctr in range(self.x_per_fpga)]
            rv.append(drv)
        return rv

    def beam_quant_gains_set(self, beam, new_gain):
        """
        Set the beam quantiser gains for the given beam on the host.
        :param beam: The Beam() on which to act
        :param new_gain: the new gain value to apply, float
        :return the value actually written to the host
        """
        self.registers.bf_value_in1.write(quant=new_gain)
        for beng_ctr in range(0, self.beng_per_host):
            self.registers.bf_control.write(
                stream=beam.index, beng=beng_ctr, antenna=0)
            self.registers.bf_value_ctrl.write(quant='pulse')
            LOGGER.info(
                '%s:%i: Beam %i:%s set beng(%i) quant_gain(%.5f)' % (
                    self.host, self.index, beam.index, beam.name,
                    beng_ctr, new_gain))
        return self.beam_quant_gains_get(beam)

    def beam_quant_gains_get(self, beam):
        """
        Read the beam quantiser gains for the given beam from the host.
        :param beam: The Beam() on which to act
        :return one value for the quant gain set on all b-engines on this host
        """
        self.registers.bf_control.write(stream=beam.index, beng=0, antenna=0)
        d = self.registers.bf_valout_quant0.read()['data']
        d.update(self.registers.bf_valout_quant1.read()['data'])
        drv = [d['quant%i' % beng_ctr]
               for beng_ctr in range(self.x_per_fpga)]
        for v in drv:
            if v != drv[0]:
                errstr = 'Host({host}) Beam({bidx}:{beam}): quantiser gains ' \
                         'differ across b-engines on this host: {vals}'.format(
                    host=self.host, bidx=beam.index, beam=beam.name, vals=drv)
                LOGGER.error(errstr)
                raise ValueError(errstr)
        return drv[0]

    def beam_partitions_read(self, beam):
        """
        Determine which partitions are currently active in the hardware.
        :param beam: The Beam() on which to act
        """
        self.registers.bf_control.write(stream=beam.index)
        vals = self.registers.bf_valout_filt.read()['data']
        rv = [vals['filt%i' % beng_ctr] for beng_ctr in range(self.x_per_fpga)]
        return rv

    def beam_partitions_control(self, beam):
        """
        Enable the active partitions for a beam on this host.
        :param beam: The Beam() on which to act
        """
        host_parts = beam.partitions_by_host[self.index]
        actv_parts = beam.partitions_active
        parts_to_set = set(host_parts).intersection(actv_parts)
        parts_to_clr = set(host_parts).difference(parts_to_set)
        if (len(parts_to_set) > 0) or (len(parts_to_clr) > 0):
            LOGGER.debug('%s:%i: Beam %i:%s beam_active(%s) host(%s) toset(%s) '
                         'toclr(%s)' %
                         (self.host, self.index, beam.index, beam.name,
                          list(actv_parts), list(host_parts),
                          list(parts_to_set), list(parts_to_clr),))
        if (len(parts_to_set) > 4) or (len(parts_to_clr) > 4):
            raise RuntimeError('Cannot set or clear more than 4 partitions'
                               'per host?')
        # set the total number of partitions
        if (len(parts_to_set) > 0) or (len(parts_to_clr) > 0):
            self.beam_num_partitions_set(beam)
        # clear first
        if len(parts_to_clr) > 0:
            self.registers.bf_value_in1.write(filt=0)
            for part in parts_to_clr:
                beng_for_part = host_parts.index(part)
                self.registers.bf_control.write(stream=beam.index,
                                                beng=beng_for_part)
                self.registers.bf_value_ctrl.write(filt='pulse')
        # enable next
        if len(parts_to_set) > 0:
            # set the offsets
            part_offsets = {}
            for part in parts_to_set:
                beng_for_part = host_parts.index(part)
                part_offset = actv_parts.index(part)
                part_offsets['partition%i_offset' % beng_for_part] = part_offset
            LOGGER.debug('%s:%i: Beam %i:%s %s' % (
                self.host, self.index, beam.index, beam.name, part_offsets))
            beam_poffset_reg = self.registers['bf%i_partitions' % beam.index]
            beam_poffset_reg.write(**part_offsets)
            # enable filter stages
            self.registers.bf_value_in1.write(filt=1)
            for part in parts_to_set:
                beng_for_part = host_parts.index(part)
                self.registers.bf_control.write(stream=beam.index,
                                                beng=beng_for_part)
                self.registers.bf_value_ctrl.write(filt='pulse')
