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

LOGGER = logging.getLogger(__name__)


class FpgaBHost(object):
    def __init__(self, xeng):
        self.b = xeng
        self.bf_per_fpga = 4

        # self.spead_initialise()
        LOGGER.info('Beamformer created')

    # specifying many frequencies is redundant for MK case

    def read_bf_config(self):
        """
        Reads data from bf_config register from all x-eng
        :param 'data_id', 'time_id'
        :return: dictionary
        """
        return self.b.registers['bf_config'].read()['data']

    def read_value_out(self):
        return self.b.registers.bf_value_out.read()['data']['reg']

    def read_value_in(self):
        return self.b.registers.bf_value_in.read()['data']['reg']

    def write_value_in(self, value):
        """
        :param value:
        :return:
        """
        self.b.registers.bf_value_in.write(reg=value)

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
                               % (beng, self.b.host))
        return data

    def write_data_id(self, value=0):
        self.b.registers['bf_config'].write(data_id=value)

    def write_time_id(self, value=0):
        self.b.registers['bf_config'].write(time_id=value)

    def read_bf_control(self):
        """
        Reads data from bf_control register from all x-eng
        'antenna' 'beng' 'frequency' 'read_destination'
        'stream' 'write_destination'
        :return: dictionary
        """
        return self.b.registers['bf_control'].read()['data']

    def write_beng(self, value=0):
        """
        Write b-eng index
        :param value:
        :return:
        """
        n_beng = self.bf_per_fpga
        if value in range(n_beng):
            self.b.registers['bf_control'].write(beng=value)
        else:
            raise LOGGER.error('Wrong b-eng index %i on host %s'
                               % (value, self.b.host))

    def write_antenna(self, value=0):
        self.b.registers['bf_control'].write(antenna=value)

    def write_stream(self, value=0):
        """
        Write which beam we are using (0 or 1 now)
        :param value:
        :return:
        """
        self.b.registers['bf_control'].write(stream=value)

    def write_frequency(self, value=0):
        self.b.registers['bf_control'].write(frequency=value)

    def write_read_destination(self, value=0):
        self.b.registers['bf_control'].write(read_destination=value)

    def write_write_destination(self, value=0):
        self.b.registers['bf_control'].write(write_destination=value)

    def write_bf_control(self, value={}):
        """
        :param value:
        :return:
        """
        if value == {} or None:  # set everything to zero
            self.write_beng(value=0)
            self.write_antenna(value=0)
            self.write_stream(value=0)
            self.write_frequency(value=0)
            self.write_read_destination(value=0)
            self.write_write_destination(value=0)
        else:
            self.write_beng(value=value['beng'])
            self.write_antenna(value=value['antenna'])
            self.write_stream(value=value['stream'])
            self.write_frequency(value=value['frequency'])
            self.write_read_destination(value=value['read_destination'])
            self.write_write_destination(value=value['write_destination'])

    def read_beam_config(self, beam=0):
        """
        Reads data from bf_config register from all x-eng
        :param 'rst', 'beam_id' 'n_partitions'
        :return: dictionary
        """
        try:
            data = self.b.registers['bf%d_config' % beam].read()['data']
            return data
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.b.host))

    def write_beam_rst(self, value=0, beam=0):
        self.b.registers['bf%d_config'
                         % beam].write(rst=value)

    def write_beam_id(self, value=0, beam=0):
        self.b.registers['bf%d_config'
                         % beam].write(beam_id=value)

    def write_beam_partitions(self, value=0, beam=0):
        self.b.registers['bf%d_config'
                         % beam].write(n_partitions=value)

    def write_beam_config(self, value={}, beam=0):
        if value == {} or None:  # set everything to zero
            self.write_beam_rst(value=0, beam=beam)
            self.write_beam_id(value=0, beam=beam)
            self.write_beam_partitions(value=0, beam=beam)
        else:
            self.write_beam_rst(value=value['rst'], beam=beam)
            self.write_beam_id(value=value['beam_id'], beam=beam)
            self.write_beam_partitions(value=value['n_partitions'],
                                       beam=beam)

    # might be hardcoded in the future
    def write_beam_offset(self, value=0, beam=0, beng=0):
        if beng == 0:
            self.b.registers['bf%d_partitions'
                             % beam].write(partition0_offset=value)
        elif beng == 1:
            self.b.registers['bf%d_partitions'
                             % beam].write(partition1_offset=value)
        elif beng == 2:
            self.b.registers['bf%d_partitions'
                             % beam].write(partition2_offset=value)
        else:
            self.b.registers['bf%d_partitions'
                             % beam].write(partition3_offset=value)

    def read_beam_offset(self, beam=0, beng=0):
        """
        Reads data from bf_config register from all x-eng
        :param 'rst', 'beam_id' 'n_partitions'
        :return: dictionary
        """
        return self.b.registers['bf%d_partitions'
                                % beam].read()['data']['partition%d_offset'
                                                       % beng]

