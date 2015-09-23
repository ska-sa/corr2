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
        if self.config is not None:
            self.bf_per_fpga = int(self.config['bengine']['bf_be_per_fpga'])
        LOGGER.info('Beamformer created')

    # specifying many frequencies is redundant for MK case

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['xengine']['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile,
                   connect=True, config=config_source)

    def read_bf_config(self):
        """
        Reads data from bf_config register from this bhost
        :param 'data_id', 'time_id'
        :return: dictionary
        """
        return self.registers['bf_config'].read()['data']

    def read_value_out(self):
        """

        :return:
        """
        return self.registers.bf_value_out.read()['data']['reg']

    # TODO frac bits
    def read_value_in(self):
        """

        :return:
        """
        return self.registers.bf_value_in.read()['data']['reg']

    # TODO frac bits
    def write_value_in(self, value):
        """

        :param value:
        :return:
        """
        self.registers.bf_value_in.write(reg=value)

    def read_beng_value_out(self, beng=0):
        """
        Read value_out register from all b-engines
        :return:
        """
        n_beng = self.bf_per_fpga
        # check if beng is in the range
        if beng in range(n_beng):
            # check if requested beng is already set
            if beng == self.read_bf_control()['beng']:
                data = self.read_value_out()
            else:
                self.write_beng(value=beng)
                data = self.read_value_out()
        else:
            raise LOGGER.error('Wrong b-eng index %i on host %s'
                               % (beng, self.host))
        return data

    def write_data_id(self, value=0):
        """

        :param value:
        :return:
        """
        self.registers['bf_config'].write(data_id=value)

    def write_time_id(self, value=0):
        """

        :param value:
        :return:
        """
        self.registers['bf_config'].write(time_id=value)

    def read_bf_control(self):
        """
        Reads data from bf_control register from all x-eng
        'antenna' 'beng' 'read_destination'
        'stream' 'write_destination'
        :return: dictionary
        """
        return self.registers['bf_control'].read()['data']

    def write_beng(self, value=0):
        """
        Write b-eng index
        :param value:
        :return:
        """
        n_beng = self.bf_per_fpga
        if value in range(n_beng):
            self.registers['bf_control'].write(beng=value)
        else:
            raise LOGGER.error('Wrong b-eng index %i on host %s'
                               % (value, self.host))

    def write_antenna(self, value=0):
        """

        :param value:
        :return:
        """
        self.registers['bf_control'].write(antenna=value)

    def write_stream(self, value=0):
        """
        Write which beam we are using (0 or 1 now)
        :param value:
        :return:
        """
        self.registers['bf_control'].write(stream=value)

    def write_read_destination(self, value=0):
        """

        :param value:
        :return:
        """
        self.registers['bf_control'].write(read_destination=value)

    def write_write_destination(self, value=0):
        """

        :param value:
        :return:
        """
        self.registers['bf_control'].write(write_destination=value)

    def write_bf_control(self, value=None):
        """
        :param value:
        :return:
        """
        # set everything to zero
        if value is None:
            self.write_beng(value=0)
            self.write_antenna(value=0)
            self.write_stream(value=0)
            self.write_read_destination(value=0)
            self.write_write_destination(value=0)
        else:
            self.write_beng(value=value['beng'])
            self.write_antenna(value=value['antenna'])
            self.write_stream(value=value['stream'])
            self.write_read_destination(value=value['read_destination'])
            self.write_write_destination(value=value['write_destination'])

    def read_beam_config(self, beam=0):
        """
        Reads data from bf_config register from all x-eng
        :param int
        :return: dictionary 'rst', 'beam_id' 'n_partitions' 'port'
        """
        try:
            data = self.registers['bf%d_config' % beam].read()['data']
            return data
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))

    def write_beam_rst(self, value=0, beam=0):
        """

        :param value:
        :param beam:
        :return:
        """
        self.registers['bf%d_config' % beam].write(rst=value)

    def write_beam_id(self, value=0, beam=0):
        """

        :param value:
        :param beam:
        :return:
        """
        self.registers['bf%d_config' % beam].write(beam_id=value)

    def write_beam_partitions(self, value=0, beam=0):
        """

        :param value:
        :param beam:
        :return:
        """
        self.registers['bf%d_config' % beam].write(n_partitions=value)

    def write_beam_port(self, value=0, beam=0):
        """

        :param value:
        :param beam:
        :return:
        """
        self.registers['bf%d_config' % beam].write(port=value)

    def write_beam_config(self, value=None, beam=0):
        """

        :param value:
        :param beam:
        :return:
        """
        # set everything to zero
        if value is None:
            self.write_beam_rst(value=0, beam=beam)
            self.write_beam_id(value=0, beam=beam)
            self.write_beam_partitions(value=0, beam=beam)
            # self.write_beam_port(value=0, beam=beam)  # bitstream not ready
        else:
            self.write_beam_rst(value=value['rst'], beam=beam)
            self.write_beam_id(value=value['beam_id'], beam=beam)
            self.write_beam_partitions(value=value['n_partitions'],
                                       beam=beam)
            # self.write_beam_partitions(value=value['port'], beam=beam)  # bitstream not ready

    # might be hardcoded in the future
    def write_beam_offset(self, value=0, beam=0, beng=0):
        """

        :param value:
        :param beam:
        :param beng:
        :return:
        """
        if beng == 0:
            self.registers['bf%d_partitions' % beam].write(partition0_offset=value)
        elif beng == 1:
            self.registers['bf%d_partitions' % beam].write(partition1_offset=value)
        elif beng == 2:
            self.registers['bf%d_partitions' % beam].write(partition2_offset=value)
        elif beng == 3:
            self.registers['bf%d_partitions' % beam].write(partition3_offset=value)
        else:
            raise RuntimeError('No such beng: %i' % beng)

    def read_beam_offset(self, beam=0, beng=0):
        """
        Reads data from bf_config register from all x-eng
        :param 'rst', 'beam_id' 'n_partitions'
        :return: dictionary
        """
        _regval = self.registers['bf%d_partitions' % beam].read()['data']
        return _regval['partition%d_offset' % beng]

    def read_beam_ip(self, beam=0):
        """

        :param beam:
        :return:
        """
        try:
            return self.registers['bf%d_ip' % beam].read()['data']['reg']
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))

    def read_beam_eof_count(self, beam=0):
        """

        :param beam:
        :return:
        """
        try:
            return self.registers['bf%d_out_count' % beam].read()['data']
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))

    def read_beam_of_count(self, beam=0):
        """

        :param beam:
        :return:
        """
        try:
            return self.registers['bf%d_ot_count' % beam].read()['data']
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))
