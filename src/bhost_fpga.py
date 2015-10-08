"""
A BHost is an extension of an XHost. It contains memory and registers
to set up and control one or more beamformers.

Author: Jason Manley, Andrew Martens, Ruby van Rooyen, Monika Obrocka
"""

import logging
from xhost_fpga import FpgaXHost

LOGGER = logging.getLogger(__name__)


class FpgaBHost(FpgaXHost):
    def __init__(self, host, katcp_port=7147, boffile=None,
                 connect=True, config=None):
        # parent constructor
        FpgaXHost.__init__(self, host, katcp_port=katcp_port,
                           boffile=boffile, connect=connect, config=config)
        self.beng_per_host = int(self.config['xengine']['x_per_fpga'])
        LOGGER.info('FpgaBHost created')

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['xengine']['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile,
                   connect=True, config=config_source)

    def beam_destination_set(self, beam):
        """
        Set the data destination for this beam.
        :param beam: a Beam object
        """
        self.registers['bf%i_config' % beam.beam_index].write(port=beam.destination_port)
        self.registers['bf%i_ip' % beam.beam_index].write(ip=int(beam.destination_ip))

    def value_duplicate_set(self):
        raise NotImplementedError

    def value_calibrate_set(self):
        raise NotImplementedError

    def value_steer_set(self):
        raise NotImplementedError

    def value_combine_set(self):
        raise NotImplementedError

    def value_visibility_set(self):
        raise NotImplementedError

    def value_quantise_set(self):
        raise NotImplementedError

    def value_filter_set(self, value, beng_indices=None):
        """
        Write a value to the filter stage of this bhost's beamformer.
        """
        self.registers.bf_value_in1.write(filt=value)
        bindices = self._write_value_bengines(beng_indices, 'filt')
        LOGGER.info('%s: wrote %.3f to filters on bengines %s' %
                    (self.host, value, bindices))

    def _write_value_bengines(self, beng_indices=None, stage_ctrl_field=''):
        """
        Strobe a value into a stage on a list of bengines by selecting
        the bengine and then pulsing the enable for that stage.
        """
        if beng_indices is None:
            beng_indices = range(0, self.beng_per_host)
        if len(beng_indices) == 0:
            raise RuntimeError('Makes no sense acting on no b-engines?')
        # enable each of the bengines in turn
        self.registers.bf_value_ctrl.write(**{stage_ctrl_field: 0})
        for beng_index in beng_indices:
            self.registers.bf_control.write(beng=beng_index)
            self.registers.bf_value_ctrl.write(**{stage_ctrl_field: 'pulse'})
        return beng_indices


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
