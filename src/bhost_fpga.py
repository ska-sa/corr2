"""
A BHost is an extension of an XHost. It contains memory and registers
to set up and control one or more beamformers.

Author: Jason Manley, Andrew Martens, Ruby van Rooyen, Monika Obrocka
"""

import logging
import time

from xhost_fpga import FpgaXHost

LOGGER = logging.getLogger(__name__)


class FpgaBHost(FpgaXHost):
    def __init__(self, host, index, katcp_port=7147, bitstream=None,
                 connect=True, config=None):
        # parent constructor
        FpgaXHost.__init__(self, host, index, katcp_port=katcp_port,
                           bitstream=bitstream, connect=connect, config=config)
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
        beam_cfgreg = self.registers['bf%i_config' % beam.index]
        beam_ipreg = self.registers['bf%i_ip' % beam.index]
        beam_cfgreg.write(port=beam.destination.port)
        beam_ipreg.write(ip=int(beam.destination.ip_address))
        LOGGER.info('%s:%i: Beam %i:%s destination set to %s' % (
            self.host, self.index, beam.index, beam.name,
            beam.destination))

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

#    def beam_num_partitions_set(self, beam):
#        """
#        :param beam: The Beam() on which to act
#        :return
#        """
#        beam_cfgreg = self.registers['bf%i_config' % beam.index]
#        # in newer versions this moved to a different register
#        if 'n_partitions' not in beam_cfgreg.field_names():
#            beam_cfgreg = self.registers['bf%i_num_parts' % beam.index]
#        numparts = len(beam.partitions_active)
#        beam_cfgreg.write(n_partitions=numparts)
#        LOGGER.debug('%s:%i: Beam %i:%s num_partitions set - %i' % (
#            self.host, self.index, beam.index, beam.name, numparts))
#
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

    def beam_weights_set(self, beam, source_labels=None):
        """
        Set the beam weights for the given beam and given input labels.
        :param beam: The Beam() on which to act
        :param source_labels: a list of the input/ant/source labels to set
        """
        if not source_labels:
            source_labels = []
            for source in beam.source_streams:
                source_labels.append(source.name)
        for source_name in source_labels:
            source = beam.get_source(source_name)
            source_info = beam.source_streams[source]
            source_weight = source_info['weight']
            source_index = source_info['index']
            self.registers.bf_value_in0.write(bw=source_weight)
            for beng_ctr in range(0, self.beng_per_host):
                self.registers.bf_control.write(
                    stream=beam.index, beng=beng_ctr, antenna=source_index)
                self.registers.bf_value_ctrl.write(bw='pulse')
                LOGGER.debug(
                    '%s:%i: Beam %i:%s set beng(%i) antenna(%i) weight(%.5f)'
                    '' % (self.host, self.index, beam.index, beam.name,
                          beng_ctr, source_index, source_weight))
        LOGGER.info('%s: set beamweights for beam %i' % (self.host, beam.index))

    def beam_weights_get(self, beam, source_labels=None):
        """
        Get the beam weights for the given beam.
        :param beam: The Beam() on which to act
        :param source_labels: a list of the input/ant/source names to get
        """
        if not source_labels:
            source_labels = []
            for source in beam.source_streams:
                source_labels.append(source.name)
        rv = []
        for source_name in source_labels:
            source = beam.get_source(source_name)
            source_info = beam.source_streams[source]
            source_index = source_info['index']
            self.registers.bf_control.write(
                stream=beam.index, beng=0, antenna=source_index)
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
        if hasattr(self.registers, 'bf0_gain'):
            # new style gain setting
            reg = self.registers['bf{}_gain'.format(beam.index)]
            reg.write(gain=new_gain)
        else:
            LOGGER.warning('OLD STYLE B-ENGINE GAIN SETTING DEPRECATED.')
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
        if hasattr(self.registers, 'bf0_gain'):
            # new style gain setting
            reg = self.registers['bf{}_gain'.format(beam.index)]
            return reg.read()['data']['gain']
        else:
            LOGGER.warning('OLD STYLE B-ENGINE GAIN SETTING DEPRECATED.')
            self.registers.bf_control.write(stream=beam.index, beng=0,
                                            antenna=0)
            d = self.registers.bf_valout_quant0.read()['data']
            d.update(self.registers.bf_valout_quant1.read()['data'])
            drv = [d['quant%i' % beng_ctr]
                   for beng_ctr in range(self.x_per_fpga)]
            for v in drv:
                if v != drv[0]:
                    errmsg = 'Host({host}) Beam({bidx}:{beam}): quantiser ' \
                             'gains differ across b-engines on ' \
                             'this host: {vals}'.format(host=self.host,
                                                        bidx=beam.index,
                                                        beam=beam.name,
                                                        vals=drv)
                    LOGGER.error(errmsg)
                    raise ValueError(errmsg)
            return drv[0]

    def check_beng(self, x_indices=None):
        """

        :param x_indices: a list of the beng indices to check
        :return:
        """
        if x_indices is None:
            x_indices = range(self.x_per_fpga)
        stat0 = self.beng_get_status(x_indices)
        time.sleep(self._get_checktime())
        stat1 = self.beng_get_status(x_indices)
        rv = []
        for xeng in x_indices:
            rvb = []
            for beng in range(2):
                st0 = stat0[xeng][beng]
                st1 = stat1[xeng][beng]
                if st0['of_err_cnt'] != st1['of_err_cnt']:
                    msg = '{host}: beng{b},{x} errors incrementing'.format(
                        host=self.host, x=xeng, b=beng)
                    LOGGER.error(msg)
                    rvb.append(1)
                elif st0['pkt_cnt'] == st1['pkt_cnt']:
                    msg = '{host}: beng{b},{x} not sending packets'.format(
                        host=self.host, x=xeng, b=beng)
                    LOGGER.warn(msg)
                    rvb.append(2)
                else:
                    rvb.append(0)
            rv.append(rvb)
        return rv

#    def beam_partitions_read(self, beam):
#        """
#        Determine which partitions are currently active in the hardware.
#        :param beam: The Beam() on which to act
#        """
#        self.registers.bf_control.write(stream=beam.index)
#        vals = self.registers.bf_valout_filt.read()['data']
#        rv = [vals['filt%i' % beng_ctr] for beng_ctr in range(self.x_per_fpga)]
#        return rv

#    def beam_partitions_control(self, beam):
#        """
#        Enable the active partitions for a beam on this host.
#        :param beam: The Beam() on which to act
#        """
#        host_parts = beam.partitions_by_host[self.index]
#        actv_parts = beam.partitions_active
#        parts_to_set = set(host_parts).intersection(actv_parts)
#        parts_to_clr = set(host_parts).difference(parts_to_set)
#        if (len(parts_to_set) > 0) or (len(parts_to_clr) > 0):
#            LOGGER.debug('%s:%i: Beam %i:%s beam_active(%s) host(%s) toset(%s) '
#                         'toclr(%s)' %
#                         (self.host, self.index, beam.index, beam.name,
#                          list(actv_parts), list(host_parts),
#                          list(parts_to_set), list(parts_to_clr),))
#        if (len(parts_to_set) > 4) or (len(parts_to_clr) > 4):
#            raise RuntimeError('Cannot set or clear more than 4 partitions'
#                               'per host?')
#        # set the total number of partitions
#        if (len(parts_to_set) > 0) or (len(parts_to_clr) > 0):
#            self.beam_num_partitions_set(beam)
#        # clear first
#        if len(parts_to_clr) > 0:
#            self.registers.bf_value_in1.write(filt=0)
#            for part in parts_to_clr:
#                beng_for_part = host_parts.index(part)
#                self.registers.bf_control.write(stream=beam.index,
#                                                beng=beng_for_part)
#                self.registers.bf_value_ctrl.write(filt='pulse')
#        # enable next
#        if len(parts_to_set) > 0:
#            # set the offsets
#            part_offsets = {}
#            for part in parts_to_set:
#                beng_for_part = host_parts.index(part)
#                part_offset = actv_parts.index(part)
#                part_offsets['partition%i_offset' % beng_for_part] = part_offset
#            LOGGER.debug('%s:%i: Beam %i:%s %s' % (
#                self.host, self.index, beam.index, beam.name, part_offsets))
#            beam_poffset_reg = self.registers['bf%i_partitions' % beam.index]
#            beam_poffset_reg.write(**part_offsets)
#            # enable filter stages
#            self.registers.bf_value_in1.write(filt=1)
#            for part in parts_to_set:
#                beng_for_part = host_parts.index(part)
#                self.registers.bf_control.write(stream=beam.index,
#                                                beng=beng_for_part)
#                self.registers.bf_value_ctrl.write(filt='pulse')
