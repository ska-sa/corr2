# /usr/bin/env python
"""
Selection of commonly-used beamformer control functions.

Author: Jason Manley, Andrew Martens, Ruby van Rooyen, Monika Obrocka
"""
"""
Revisions:
2012-10-02 JRM Initial
2013-02-10 AM basic boresight
2013-02-11 AM basic SPEAD
2013-02-21 AM flexible bandwidth
2013-03-01 AM calibration
2013-03-05 AM SPEAD metadata
\n"""

import logging
from xhost_fpga import FpgaXHost

LOGGER = logging.getLogger(__name__)


class FpgaBHost(FpgaXHost):
    def __init__(self, host, katcp_port=7147, boffile=None, connect=True, config=None):
        # parent constructor
        FpgaXHost.__init__(self, host, katcp_port=katcp_port, boffile=boffile, connect=connect, config=config)
        self.config = config
        if self.config is not None:
            self.bf_per_fpga = int(self.config['bengine']['bf_be_per_fpga'])
        self.bf_per_fpga = 4

        LOGGER.info('Beamformer created')

    # specifying many frequencies is redundant for MK case

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['xengine']['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile, connect=True, config=config_source)

    def read_bf_config(self):
        """
        Reads data from bf_config register from all x-eng
        :param 'data_id', 'time_id'
        :return: dictionary
        """
        return self.registers['bf_config'].read()['data']

    def read_value_out(self):
        """

        :return:
        """
        return self.registers.bf_value_out.read()['data']['reg']

    # TODO frac bits no reg
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

    def read_beng_value_out(self, beng):
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

    def write_data_id(self, value):
        """

        :param value:
        :return:
        """
        self.registers['bf_config'].write(data_id=value)

    def write_time_id(self, value):
        """

        :param value:
        :return:
        """
        self.registers['bf_config'].write(time_id=value)

    def write_bf_config(self, value):
        """
        :param value: dictionary ex. {'data_id': 0, 'time_id': 1}
        :return:
        """
        if value is None:  # set everything to zero
            self.write_data_id(value=0)
            self.write_time_id(value=0)
        else:
            self.write_data_id(value=value['data_id'])
            self.write_time_id(value=value['time_id'])

    def read_bf_control(self):
        """
        Reads data from bf_control register from all x-eng
        'antenna' 'beng' 'read_destination'
        'stream' 'write_destination'
        :return: dictionary
        """
        return self.registers['bf_control'].read()['data']

    def write_beng(self, value):
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

    def write_antenna(self, value):
        """

        :param value:
        :return:
        """
        self.registers['bf_control'].write(antenna=value)

    def write_stream(self, value):
        """
        Write which beam we are using (0 or 1 now)
        :param value:
        :return:
        """
        self.registers['bf_control'].write(stream=value)

    def write_read_destination(self, value):
        """

        :param value:
        :return:
        """
        self.registers['bf_control'].write(read_destination=value)

    def write_write_destination(self, value):
        """

        :param value:
        :return:
        """
        self.registers['bf_control'].write(write_destination=value)

    def write_bf_control(self, value):
        """
        :param value: dictionary ex. {'antenna': 0, 'beng': 1, 'frequency': 2,
        'read_destination': 3, 'stream': 1, 'write_destination': 2}
        :return:
        """
        if value is None:  # set everything to zero
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

    def read_beam_config(self, beam):
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

    def write_beam_rst(self, value, beam):
        """

        :param value:
        :param beam:
        :return: <nothing>
        """
        self.registers['bf%d_config'
                       % beam].write(rst=value)

    def write_beam_id(self, value, beam):
        """

        :param value:
        :param beam:
        :return: <nothing>
        """
        self.registers['bf%d_config'
                       % beam].write(beam_id=value)

    def write_beam_n_partitions(self, value, beam):
        """

        :param value:
        :param beam:
        :return: <nothing>
        """
        self.registers['bf%d_config'
                       % beam].write(n_partitions=value)

    # TODO no register
    def write_beam_port(self, value, beam):
        """

        :param value:
        :param beam:
        :return: <nothing>
        """
        self.registers['bf%d_config'
                       % beam].write(port=value)

    def write_beam_config(self, value, beam):
        """

        :param value: dictionary ex. {'rst': 0, 'beam_id': 1, 'n_partitions': 2}
        :param beam: int
        :return: <nothing>
        """
        if value is None:  # set everything to zero
            self.write_beam_rst(value=0, beam=beam)
            self.write_beam_id(value=0, beam=beam)
            self.write_beam_n_partitions(value=0, beam=beam)
            # self.write_beam_port(value=0, beam=beam)  # bitstream not ready
        else:
            self.write_beam_rst(value=value['rst'], beam=beam)
            self.write_beam_id(value=value['beam_id'], beam=beam)
            self.write_beam_n_partitions(value=value['n_partitions'],
                                       beam=beam)
            # self.write_beam_port(value=value, beam=beam)  # bitstream not ready

    def write_beam_offset(self, value, beam):
        """
        Increments partition offset for each b-engine per roach
        :param value: start value (0,4,8,12,16,etc)
        :param beam:
        :return:
        """
        n_beng = range(int(self.config['bengine']['bf_be_per_fpga']))
        if len(n_beng) > 4:
            LOGGER.error('Hardcoded number of b-engines.')
            return
        self.registers['bf%d_partitions' % beam].write(partition0_offset=value+n_beng[0])
        self.registers['bf%d_partitions' % beam].write(partition1_offset=value+n_beng[1])
        self.registers['bf%d_partitions' % beam].write(partition2_offset=value+n_beng[2])
        self.registers['bf%d_partitions' % beam].write(partition3_offset=value+n_beng[3])

    def read_beam_offset(self, beam):
        """

        :param beam:
        :return:
        """
        return self.registers['bf%d_partitions'
                              % beam].read()['data']

    # TODO no register
    def read_beam_ip(self, beam):
        """

        :param beam:
        :return:
        """
        try:
            return self.registers['bf%d_ip' % beam].read()['data']['reg']
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))

    # TODO no register
    def write_beam_ip(self, value, beam):
        """

        :param value: ip int
        :param beam:
        :return:
        """
        try:
            return self.registers['bf%d_ip' % beam].write(reg=value)
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))

    # TODO no register
    def read_beam_eof_count(self, beam):
        """

        :param beam:
        :return:
        """
        try:
            return self.registers['bf%d_out_count' % beam].read()['data']
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))

    # TODO no register
    def read_beam_of_count(self, beam):
        """
        :param beam:
        :return:
        """
        try:
            return self.registers['bf%d_ot_count' % beam].read()['data']
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))