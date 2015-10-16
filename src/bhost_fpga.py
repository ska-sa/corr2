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
        self.beng_per_host = int(self.config['xengine']['x_per_fpga'])
        LOGGER.info('FpgaBHost %i:%s created' % (
            self.index, self.host))

    @classmethod
    def from_config_source(cls, hostname, index, katcp_port, config_source):
        boffile = config_source['xengine']['bitstream']
        return cls(hostname, index, katcp_port=katcp_port, boffile=boffile,
                   connect=True, config=config_source)

    def beam_destination_set(self, beam):
        """
        Set the data destination for this beam.
        :param beam: a Beam object
        :return
        """
        self.registers['bf%i_config' % beam.index].write(
            port=beam.data_destination['port'])
        self.registers['bf%i_ip' % beam.index].write(
            ip=int(beam.data_destination['ip']))
        LOGGER.info('%s:%i: Beam %i:%s destination set to %s:%i' % (
            self.host, self.index, beam.index, beam.name,
            beam.data_destination['ip'], beam.data_destination['port']))

    def beam_config_set(self, beam):
        """
        :param beam: a Beam object
        :return
        """
        beam_reg = self.registers['bf%i_config' % beam.index]
        beam_reg.write(beam_id=beam.index,
                       n_partitions=beam.partitions_total)
        LOGGER.info('%s:%i: Beam %i:%s config register set' % (
            self.host, self.index, beam.index, beam.name))

    def beam_partitions_set(self, beam):
        """
        :param beam: a Beam object
        :return
        """
        # partitions offsets must be worked out
        partition_start = self.index * self.beng_per_host
        beam_reg = self.registers['bf%i_partitions' % beam.index]
        beam_reg.write(partition0_offset=partition_start,
                       partition1_offset=partition_start+1,
                       partition2_offset=partition_start+2,
                       partition3_offset=partition_start+3)
        LOGGER.info('%s:%i: Beam %i:%s partitions set to %i:%i' % (
            self.host, self.index, beam.index, beam.name,
            partition_start, partition_start+self.beng_per_host-1))

    def beam_weights_set(self, beam):
        """
        Set the beam weights for the given beam.
        """
        for ant_ctr, ant_weight in enumerate(beam.source_weights):
            self.registers.bf_value_in0.write(bw=ant_weight)
            for beng_ctr in range(0, self.beng_per_host):
                self.registers.bf_control.write(stream=beam.index,
                                                beng=beng_ctr,
                                                antenna=ant_ctr)
                self.registers.bf_value_ctrl.write(bw='pulse')
        LOGGER.info('%s:%i: Beam %i:%s set antenna(%i) stream(%i) weights(%s)'
                    % (self.host, self.index, beam.index, beam.name,
                       self.index, beam.index, beam.source_weights))

    def beam_partitions_control(self, beam):
        """
        Set the active partitions for a beam on this host.
        """
        host_parts = beam.partitions_by_host[self.index]
        actv_parts = beam.partitions_active
        parts_to_set = set(host_parts).intersection(actv_parts)
        parts_to_clr = set(host_parts).difference(parts_to_set)
        LOGGER.info('%s:%i: Beam %i:%s beam_active(%s) host(%s) toset(%s) '
                    'toclr(%s)' %
                    (self.host, self.index, beam.index, beam.name,
                     list(actv_parts), list(host_parts), list(parts_to_set),
                     list(parts_to_clr)))
        if len(parts_to_set) > 0:
            self.registers.bf_value_in1.write(filt=1)
            for part in parts_to_set:
                beng_for_part = host_parts.index(part)
                self.registers.bf_control.write(stream=beam.index,
                                                beng=beng_for_part)
                self.registers.bf_value_ctrl.write(filt='pulse')
        if len(parts_to_clr) > 0:
            self.registers.bf_value_in1.write(filt=0)
            for part in parts_to_clr:
                beng_for_part = host_parts.index(part)
                self.registers.bf_control.write(stream=beam.index,
                                                beng=beng_for_part)
                self.registers.bf_value_ctrl.write(filt='pulse')

    # def value_duplicate_set(self):
    #     raise NotImplementedError
    #
    # def value_calibrate_set(self):
    #     raise NotImplementedError
    #
    # def value_steer_set(self):
    #     raise NotImplementedError
    #
    # def value_combine_set(self):
    #     raise NotImplementedError
    #
    # def value_visibility_set(self):
    #     raise NotImplementedError
    #
    # def value_quantise_set(self):
    #     raise NotImplementedError
    #
    # def value_filter_set(self, value, beng_indices=None):
    #     """
    #     Write a value to the filter stage of this bhost's beamformer.
    #     """
    #     self.registers.bf_value_in1.write(filt=value)
    #     bindices = self._write_value_bengines(beng_indices, 'filt')
    #     LOGGER.info('%s: wrote %.3f to filters on bengines %s' %
    #                 (self.host, value, bindices))
    #
    # def _write_value_bengines(self, beng_indices=None, stage_ctrl_field=''):
    #     """
    #     Strobe a value into a stage on a list of bengines by selecting
    #     the bengine and then pulsing the enable for that stage.
    #     """
    #     if beng_indices is None:
    #         beng_indices = range(0, self.beng_per_host)
    #     if len(beng_indices) == 0:
    #         raise RuntimeError('Makes no sense acting on no b-engines?')
    #     # enable each of the bengines in turn
    #     self.registers.bf_value_ctrl.write(**{stage_ctrl_field: 0})
    #     for beng_index in beng_indices:
    #         self.registers.bf_control.write(beng=beng_index)
    #         self.registers.bf_value_ctrl.write(**{stage_ctrl_field: 'pulse'})
    #     return beng_indices

    # def read_bf_config(self):
    #     """
    #     Reads data from bf_config register from this bhost
    #     :param 'data_id', 'time_id'
    #     :return: dictionary
    #     """
    #     return self.registers.bf_config.read()['data']
    #
    # def read_value_out(self):
    #     """
    #
    #     :return:
    #     """
    #     return self.registers.bf_value_out.read()['data']['reg']
    #
    # def read_value_in(self):
    #     """
    #
    #     :return:
    #     """
    #     return self.registers.bf_value_in.read()['data']['reg']

    # def write_value_in(self, value):
    #     """
    #
    #     :param value: pass a float
    #     :return:
    #     """
    #     self.registers.bf_value_in.write(reg=value)

    # def read_beng_value_out(self, beng):
    #     """
    #     Read value_out register from all b-engines
    #     :return:
    #     """
    #     n_beng = self.bf_per_fpga
    #     # check if beng is in the range
    #     if beng in range(n_beng):
    #         # check if requested beng is already set
    #         if beng == self.read_bf_control()['beng']:
    #             data = self.read_value_out()
    #         else:
    #             self.write_beng(value=beng)
    #             data = self.read_value_out()
    #     else:
    #         raise LOGGER.error('Wrong b-eng index %i on host %s'
    #                            % (beng, self.host))
    #     return data
    #
    # def write_data_id(self, value):
    #     """
    #
    #     :param value:
    #     :return:
    #     """
    #     self.registers.bf_config.write(data_id=value)
    #
    # def write_time_id(self, value):
    #     """
    #
    #     :param value:
    #     :return:
    #     """
    #     self.registers.bf_config.write(time_id=value)
    #
    # def write_bf_config(self, value):
    #     """
    #     :param value: dictionary ex. {'data_id': 0, 'time_id': 1}
    #     :return:
    #     """
    #     if value is None:  # set everything to zero
    #         self.write_data_id(value=0)
    #         self.write_time_id(value=0)
    #     else:
    #         self.write_data_id(value=value['data_id'])
    #         self.write_time_id(value=value['time_id'])
    #
    # def read_bf_control(self):
    #     """
    #     Reads data from bf_control register from all x-eng
    #     'antenna' 'beng' 'read_destination'
    #     'stream' 'write_destination'
    #     :return: dictionary
    #     """
    #     return self.registers.bf_control.read()['data']
    #
    # def write_beng(self, value):
    #     """
    #     Write b-eng index
    #     :param value:
    #     :return:
    #     """
    #     n_beng = self.bf_per_fpga
    #     if value in range(n_beng):
    #         self.registers.bf_control.write(beng=value)
    #     else:
    #         raise LOGGER.error('Wrong b-eng index %i on host %s'
    #                            % (value, self.host))
    #
    # def write_bf_control(self, value=None):
    #     """
    #     :param value: dictionary ex. {'antenna': 0, 'beng': 1, 'frequency': 2,
    #     'read_destination': 3, 'stream': 1, 'write_destination': 2}
    #     :return:
    #     """
    #     if value is None:
    #         value = {'antenna': 0, 'beng': 0, 'frequency': 0,
    #                  'read_destination': 0, 'stream': 0,
    #                  'write_destination': 0}
    #     self.registers['bf_control'].write(**value)
    #
    # def read_beam_config(self, beam):
    #     """
    #     Reads data from bf_config register from all x-eng
    #     :param int
    #     :return: dictionary 'rst', 'beam_id' 'n_partitions' 'port'
    #     """
    #     try:
    #         data = self.registers['bf%d_config' % beam].read()['data']
    #         return data
    #     except AttributeError:
    #         LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))
    #
    # def write_beam_rst(self, value, beam):
    #     """
    #
    #     :param value:
    #     :param beam:
    #     :return: <nothing>
    #     """
    #     self.registers['bf%d_config' % beam].write(rst=value)
    #
    # def write_beam_id(self, value, beam):
    #     """
    #
    #     :param value:
    #     :param beam:
    #     :return: <nothing>
    #     """
    #     self.registers['bf%d_config' % beam].write(beam_id=value)
    #
    # def write_beam_n_partitions(self, value, beam):
    #     """
    #
    #     :param value:
    #     :param beam:
    #     :return: <nothing>
    #     """
    #     self.registers['bf%d_config' % beam].write(n_partitions=value)
    #
    # # TODO no register
    # def write_beam_port(self, value, beam):
    #     """
    #
    #     :param value:
    #     :param beam:
    #     :return: <nothing>
    #     """
    #     self.registers['bf%d_config' % beam].write(port=value)
    #
    # def write_beam_config(self, value=None, beam=0):
    #     """
    #
    #     :param value: dictionary ex. {'rst': 0, 'beam_id': 1, 'n_partitions': 2}
    #     :param beam: int
    #     :return: <nothing>
    #     """
    #     # set everything to zero
    #     if value is None:
    #         self.write_beam_rst(value=0, beam=beam)
    #         self.write_beam_id(value=0, beam=beam)
    #         self.write_beam_n_partitions(value=0, beam=beam)
    #         # self.write_beam_port(value=0, beam=beam)  # bitstream not ready
    #     else:
    #         self.write_beam_rst(value=value['rst'], beam=beam)
    #         self.write_beam_id(value=value['beam_id'], beam=beam)
    #         self.write_beam_n_partitions(value=value['n_partitions'],
    #                                    beam=beam)
    #         # self.write_beam_port(value=value, beam=beam)  # bitstream not ready

    # def write_beam_offset(self, value, beam):
    #     """
    #     Increments partition offset for each b-engine per roach
    #     :param value: start value (0,4,8,12,16,etc)
    #     :param beam:
    #     :return:
    #     """
    #     self.registers['bf%i_partitions' % beam].write(partition0_offset=value+0,
    #                                                    partition1_offset=value+1,
    #                                                    partition2_offset=value+2,
    #                                                    partition3_offset=value+3)

    # def read_beam_offsets(self, beam):
    #     """
    #
    #     :param beam:
    #     :return:
    #     """
    #     return self.registers['bf%d_partitions' % beam].read()['data']
    #
    # def read_beam_ip(self, beam):
    #     """
    #
    #     :param beam:
    #     :return:
    #     """
    #     try:
    #         return self.registers['bf%d_ip' % beam].read()['data']['ip']
    #     except AttributeError:
    #         LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))
    #
    # def write_beam_ip(self, value, beam):
    #     """
    #
    #     :param value: ip 32-bit unsigned integer
    #     :param beam:
    #     :return:
    #     """
    #     try:
    #         return self.registers['bf%d_ip' % beam].write(ip=value)
    #     except AttributeError:
    #         LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))
    #
    # def read_beam_eof_counts(self, beam):
    #     """
    #
    #     :param beam:
    #     :return:
    #     """
    #     try:
    #         return self.registers['bf%d_out_count' % beam].read()['data']
    #     except AttributeError:
    #         LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))
    #
    # def read_beam_of_counts(self, beam):
    #     """
    #     :param beam:
    #     :return:
    #     """
    #     try:
    #         return self.registers['bf%d_ot_count' % beam].read()['data']
    #     except AttributeError:
    #         LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))
