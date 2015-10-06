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

import inspect
import logging
from host_fpga import FpgaHost

LOGGER = logging.getLogger(__name__)

class FpgaBHost(FpgaHost):
    def __init__(self, host, katcp_port=7147, boffile=None,
                 connect=True, config=None):
        FpgaHost.__init__(self, host, katcp_port=katcp_port, boffile=boffile, connect=connect)
        self.config = config
        self.bf_per_fpga = 4

        # self.spead_initialise()
        LOGGER.info('Beamformer created')

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile,
                   connect=True, config=config_source)

    # specifying many frequencies is redundant for MK case

    # TODO check when registers are there
    def read_speadify_status(self, beam=0):
        return self.registers['bf%i_status' % beam].read()['data']

    # TODO check when registers are there
    def read_beam_destination(self, beam=0):
        return self.registers['bf%i_dest' % beam].read()['data']

    def read_bf_config(self):
        """
        Reads data from bf_config register from all x-eng
        :param 'data_id', 'time_id'
        :return: dictionary
        """
        return self.registers['bf_config'].read()['data']

    def read_value_out(self):
        return self.registers.bf_value_out.read()['data']['reg']

    def read_value_in(self):
        return self.registers.bf_value_in.read()['data']['reg']

    def write_value_in(self, value, blindwrite=False):
        """
        :param value:
        :return:
        """
        if blindwrite:
            self.registers.bf_value_in.blindwrite(reg=value)
        else:
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
                self.write_beng(value=beng, blindwrite=True)
                data = self.read_value_out()
        else:
            raise LOGGER.error('Wrong b-eng index %i on host %s'
                               % (beng, self.host))
        return data

    def write_data_id(self, value=0, blindwrite=False):
        if blindwrite:
            self.registers['bf_config'].blindwrite(data_id=value)
        else:
            self.registers['bf_config'].write(data_id=value)

    def write_time_id(self, value=0, blindwrite=False):
        if blindwrite:
            self.registers['bf_config'].blindwrite(time_id=value)
        else:
            self.registers['bf_config'].write(time_id=value)

    def read_bf_control(self):
        """
        Reads data from bf_control register from all x-eng
        'antenna' 'beng' 'frequency' 'read_destination'
        'stream' 'write_destination'
        :return: dictionary
        """
        return self.registers['bf_control'].read()['data']

    def write_beng(self, value=0, blindwrite=False):
        """
        Write b-eng index
        :param value:
        :param blindwrite:
        :return:
        """
        n_beng = self.bf_per_fpga
        if value in range(n_beng):
            if blindwrite:
                self.registers['bf_control'].blindwrite(beng=value)
            else:
                self.registers['bf_control'].write(beng=value)
        else:
            raise LOGGER.error('Wrong b-eng index %i on host %s'
                               % (value, self.host))

    def write_antenna(self, value=0, blindwrite=False):
        if blindwrite:
            self.registers['bf_control'].blindwrite(antenna=value)
        else:
            self.registers['bf_control'].write(antenna=value)

    def write_stream(self, value=0, blindwrite=False):
        """
        Write which beam we are using (0 or 1 now)
        :param value:
        :param blindwrite:
        :return:
        """
        if blindwrite:
            self.registers['bf_control'].blindwrite(stream=value)
        else:
            self.registers['bf_control'].write(stream=value)

    def write_frequency(self, value=0, blindwrite=False):
        if blindwrite:
            self.registers['bf_control'].blindwrite(frequency=value)
        else:
            self.registers['bf_control'].write(frequency=value)

    def write_read_destination(self, value=0, blindwrite=False):
        if blindwrite:
            self.registers['bf_control'].blindwrite(read_destination=value)
        else:
            self.registers['bf_control'].write(read_destination=value)

    def write_write_destination(self, value=0, blindwrite=False):
        if blindwrite:
            self.registers['bf_control'].blindwrite(write_destination=value)
        else:
            self.registers['bf_control'].write(write_destination=value)

    def write_bf_control(self, value={}, blindwrite=False):
        """

        :param value:
        :param blindwrite:
        :return:
        """
        if value == {} or None:  # set everything to zero
            self.write_beng(value=0, blindwrite=blindwrite)
            self.write_antenna(value=0, blindwrite=blindwrite)
            self.write_stream(value=0, blindwrite=blindwrite)
            self.write_frequency(value=0, blindwrite=blindwrite)
            self.write_read_destination(value=0, blindwrite=blindwrite)
            self.write_write_destination(value=0, blindwrite=blindwrite)
        else:
            self.write_beng(value=value['beng'], blindwrite=blindwrite)
            self.write_antenna(value=value['antenna'], blindwrite=blindwrite)
            self.write_stream(value=value['stream'], blindwrite=blindwrite)
            self.write_frequency(value=value['frequency'], blindwrite=blindwrite)
            self.write_read_destination(value=value['read_destination'], blindwrite=blindwrite)
            self.write_write_destination(value=value['write_destination'], blindwrite=blindwrite)

    def read_beam_config(self, beam=0):
        """
        Reads data from bf_config register from all x-eng
        :param 'rst', 'beam_id' 'n_partitions'
        :return: dictionary
        """
        try:
            data = self.registers['bf%d_config' % beam].read()['data']
            return data
        except AttributeError:
            LOGGER.error('Beam index %i out of range on host %s' % (beam, self.host))

    def write_beam_rst(self, value=0, beam=0, blindwrite=False):
        if blindwrite:
            self.registers['bf%d_config' % beam].blindwrite(rst=value)
        else:
            self.registers['bf%d_config' % beam].write(rst=value)

    def write_beam_id(self, value=0, beam=0, blindwrite=False):
        if blindwrite:
            self.registers['bf%d_config' % beam].blindwrite(beam_id=value)
        else:
            self.registers['bf%d_config' % beam].write(beam_id=value)

    def write_beam_partitions(self, value=0, beam=0, blindwrite=False):
        if blindwrite:
            self.registers['bf%d_config' % beam].blindwrite(n_partitions=value)
        else:
            self.registers['bf%d_config' % beam].write(n_partitions=value)

    def write_beam_config(self, value={}, beam=0, blindwrite=True):
        if value == {} or None:  # set everything to zero
            self.write_beam_rst( value=0, beam=beam, blindwrite=blindwrite)
            self.write_beam_id(value=0, beam=beam, blindwrite=blindwrite)
            self.write_beam_partitions(value=0, beam=beam, blindwrite=blindwrite)
        else:
            self.write_beam_rst(value=value['rst'], beam=beam, blindwrite=blindwrite)
            self.write_beam_id(value=value['beam_id'], beam=beam, blindwrite=blindwrite)
            self.write_beam_partitions(value=value['n_partitions'], beam=beam, blindwrite=blindwrite)

    # might be hardcoded in the future
    def write_beam_offset(self, value=0, beam=0, beng=0):
        if beng == 0:
            self.registers['bf%d_partitions' % beam].blindwrite(partition0_offset=value)
        elif beng == 1:
            self.registers['bf%d_partitions' % beam].blindwrite(partition1_offset=value)
        elif beng == 2:
            self.registers['bf%d_partitions' % beam].blindwrite(partition2_offset=value)
        else:
            self.registers['bf%d_partitions' % beam].blindwrite(partition3_offset=value)

    def read_beam_offset(self, beam=0, beng=0):
        """
        Reads data from bf_config register from all x-eng
        :param 'rst', 'beam_id' 'n_partitions'
        :return: dictionary
        """
        return self.registers['bf%d_partitions'
                              % beam].read()['data']['partition%d_offset'
                                                     % beng]

