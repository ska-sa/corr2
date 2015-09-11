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
                 connect=True, config=None,
                 simulate=False, optimisations=True):
        FpgaHost.__init__(self, host, katcp_port=katcp_port, boffile=boffile, connect=connect)
        self.config = config
        # if self.config is not None:
        #     self.bf_per_fpga = int(self.config['bf_be_per_fpga'])
        self.bf_per_fpga = 4
        #  optimisations on writes (that currently expose bugs)
        self.optimisations = optimisations
        #  simulate operations (and output debug data).
        # Useful for when there is no hardware
        self.simulate = simulate


        # self.spead_initialise()
        LOGGER.info('Beamformer created')

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile, connect=True, config=config_source)

    # specifying many frequencies is redundant for MK case

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

#######################
# OBSOLETE
#######################

# def set_beam_param(self, beams, param, values):
#     """
#
#     :param beams:
#     :param param:
#     :param values:
#     :return:
#     """
#     beams = self.beams2beams(beams)
#     # check vector lengths match up
#     if type(values) == list and len(values) != len(beams):
#         raise LOGGER.error('Beam vector must be same length as '
#                            'value vector if passing many values',
#                            'function %s, line no %s\n'
#                            % (__name__, inspect.currentframe().f_lineno),
#                            LOGGER)
#     beam_indices = self.beam2index(beams)
#     if len(beam_indices) == 0:
#         raise LOGGER.error('Error locating beams function %s, line no %s\n'
#                            % (__name__, inspect.currentframe().f_lineno),
#                            LOGGER)
#     for index, beam_index in enumerate(beam_indices):
#         if type(values) == list:
#             value = values[index]
#         else:
#             value = values
#         self.set_param('bf_%s_beam%d' % (param, beam_index), value)

#  obsolete
    # def set_param(self, param, value):
    #     """
    #     Set beamformer parameter value
    #     :param param:
    #     :param value:
    #     :return:
    #     """
    #     try:
    #         self.config['beamformer'][param] = value
    #     except KeyError as ke:
    #         LOGGER.error('set_param: error setting value of self.config[%s]' % ke)
    #         raise
    #     except Exception as err:
    #         # Issues a message at the ERROR level and adds exception information to the log message
    #         LOGGER.exception(err.__class__)
    #         raise

    #  obsolete
    # def frequency2fpgas(self, frequencies=[], fft_bins=[], unique=False):
    #     """
    #     returns fpgas associated with frequencies specified. unique only returns unique fpgas
    #     e.g. for 8 x-eng there are 4096 channels produced by the f-eng and 512 different freqs per x-eng
    #     :param frequencies:
    #     :param fft_bins:
    #     :param unique:
    #     :return: fpgas
    #     """
    #     fpgas = []
    #     if len(fft_bins) == 0:
    #         fft_bins = self.frequency2fft_bin(frequencies=frequencies)
    #     all_fpgas = self.get_fpgas()
    #     n_chans = self.config['fengine']['n_chans']
    #     n_chans_per_fpga = int(n_chans)/len(all_fpgas)
    #     prev_index = -1
    #     for fft_bin in fft_bins:
    #         index = numpy.int(fft_bin/n_chans_per_fpga)  # floor built in
    #         if index < 0 or index > len(all_fpgas)-1:
    #             raise LOGGER.error('FPGA index calculated out of range',
    #                                'function %s, line no %s\n'
    #                                % (__name__, inspect.currentframe().f_lineno),
    #                                LOGGER)
    #         if (unique == False) or index != prev_index:
    #             fpgas.append(all_fpgas[index])
    #         prev_index = index
    #     return fpgas

    #  obsolete
    # def frequency2bf_label(self, frequencies=[], fft_bins=[], unique=False):
    #     """
    #     returns bf labels associated with the frequencies specified
    #     :param frequencies:
    #     :param fft_bins:
    #     :param unique:
    #     :return: bf_labels
    #     """
    #     if len(fft_bins) == 0:
    #         fft_bins = self.frequency2fft_bin(frequencies=frequencies)
    #     bf_labels = []
    #     bf_be_per_fpga = len(self.get_bfs())
    #     bf_indices = self.frequency2bf_index(frequencies, fft_bins, unique)
    #     for bf_index in bf_indices:
    #         bf_labels.append(numpy.mod(bf_index, bf_be_per_fpga))
    #     return bf_labels

    #  obsolete
    # def frequency2bf_index(self, frequencies=[], fft_bins=[], unique=False):
    #     """
    #     returns bf indices associated with the frequencies specified
    #     :param frequencies:
    #     :param fft_bins:
    #     :param unique:
    #     :return: bf_indices
    #     """
    #     bf_indices = []
    #     if len(fft_bins) == 0:
    #         fft_bins = self.frequency2fft_bin(frequencies=frequencies)
    #     n_fpgas = len(self.get_fpgas())  # x-eng
    #     bf_be_per_fpga = len(self.get_bfs())
    #     n_bfs = n_fpgas*bf_be_per_fpga  # total number of bfs
    #     n_chans = int(self.config['fengine']['n_chans'])
    #     n_chans_per_bf = n_chans/n_bfs
    #     if max(fft_bins) > n_chans-1 or min(fft_bins) < 0:
    #         raise LOGGER.error('FFT bin/s out of range', 'function %s, '
    #                                                      'line no %s\n'
    #                            % (__name__, inspect.currentframe().f_lineno),
    #                            LOGGER)
    #     for fft_bin in fft_bins:
    #         bf_index = fft_bin/n_chans_per_bf
    #         if unique == False or bf_indices.count(bf_index) == 0:
    #             bf_indices.append(bf_index)
    #     return bf_indices

    #  obsolete
    # def frequency2frequency_reg_index(self, frequencies=[], fft_bins=[]):
    #     """
    #     Returns list of values to write into frequency register corresponding to frequency specified
    #     :param frequencies:
    #     :param fft_bins:
    #     :return: indices
    #     """
    #     indices = []
    #     if len(fft_bins) == 0:
    #         fft_bins = self.frequency2fft_bin(frequencies)
    #     n_chans = int(self.config['fengine']['n_chans'])
    #     bf_be_per_fpga = len(self.get_bfs())
    #     n_fpgas = len(self.get_fpgas())
    #     divisions = n_fpgas * bf_be_per_fpga
    #     if max(fft_bins) > n_chans-1 or min(fft_bins) < 0:
    #         raise LOGGER.error('FFT bin/s out of range',
    #                            'function %s, line no %s\n'
    #                            % (__name__, inspect.currentframe().f_lineno),
    #                            LOGGER)
    #     for fft_bin in fft_bins:
    #         indices.append(numpy.mod(fft_bin, n_chans/divisions))
    #     return indices

    #  obsolete

    #  obsolete
    # def fft_bin2frequency(self, fft_bins=[]):
    #     """
    #     returns a list of centre frequencies associated with the fft bins supplied
    #     :param fft_bins:
    #     :return: frequencies
    #     """
    #     frequencies = []
    #     n_chans = int(self.config['fengine']['n_chans'])
    #     if fft_bins == range(n_chans):
    #         fft_bins = range(n_chans)
    #     if type(fft_bins) == int:
    #         fft_bins = [fft_bins]
    #     if max(fft_bins) > n_chans or min(fft_bins) < 0:
    #         raise LOGGER.error('fft_bins out of range 0 -> %d'
    #                            % (n_chans-1), 'function %s, line no %s\n'
    #                            % (__name__, inspect.currentframe().f_lineno),
    #                            LOGGER)
    #     bandwidth = int(self.config['fengine']['bandwidth'])
    #     for fft_bin in fft_bins:
    #         frequencies.append((float(fft_bin)/n_chans)*bandwidth)
    #     return frequencies

    #  obsolete
    # def write_int(self, device_name, data, offset=0, frequencies=[],
    #               fft_bins=[], blindwrite=False, beam=False):
    #     """
    #     Writes data to all devices on all bfs in all fpgas associated with the
    #     frequencies specified
    #     :param device_name:
    #     :param data:
    #     :param offset:
    #     :param frequencies:
    #     :param fft_bins:
    #     :param blindwrite:
    #     :return:
    #     """
    #     # TODO work this out properly
    #     timeout = 1
    #     # get all fpgas, bfs associated with frequencies specified
    #     if len(fft_bins) == 0:
    #         fft_bins = self.frequency2fft_bin(frequencies)
    #     targets = self.frequency2fpga_bf(frequencies, fft_bins, unique=True)
    #     if len(data) > 1 and len(targets) != len(data):
    #
    #         raise LOGGER.error('Many data but size (%d) does not match length of targets (%d)'
    #                            % (len(data), len(targets)), 'function %s, line no %s\n'
    #                            % (__name__, inspect.currentframe().f_lineno), LOGGER)
    #     bf_register_prefix = self.config['beamformer']['bf_register_prefix']
    #     # if optimisations are enabled and (same data, and multiple targets)
    #     # write to all targets with the same register name
    #     if self.optimisations and (len(data) == 1 and len(targets) > 1):
    #         if self.simulate == True:
    #             print 'optimisations on, single data item, writing in parallel'
    #         n_bfs = len(self.get_bfs())
    #         # run through all bfs
    #         for bf_index in range(n_bfs):
    #             fpgas = []
    #             # generate register name
    #             name = '%s%s_%s' % (bf_register_prefix, bf_index, device_name)
    #             datum = struct.pack(">I", data[0])
    #             # find all fpgas to be written to for this bf
    #             for target in targets:
    #                 if target['bf'] == bf_index:
    #                     fpgas.append(target['fpga'])
    #             if len(fpgas) != 0:
    #                 if self.simulate == True:
    #                     print 'dummy executing non-blocking request for write to %s on %d fpgas' % (name, len(fpgas))
    #                 else:
    #                     nottimedout, rv = utils.threaded_non_blocking_request(self.c.xhosts, timeout, 'write',
    #                                                                           [name, offset*4, datum])
    #                     if nottimedout == False:
    #                         raise LOGGER.error('Timeout asynchronously writing 0x%.8x to %s on %d fpgas offset %i'
    #                                            % (data[0], name, len(fpgas), offset), 'function %s, line no %s\n'
    #                                            % (__name__, inspect.currentframe().f_lineno), LOGGER)
    #                     for k, v in rv.items():
    #                         if v['reply'] != 'ok':
    #                             raise LOGGER.error('Got %s instead of ''ok'' when writing 0x%.8x to %s:%s offset %i'
    #                                                % (v['reply'], data[0], k, name, offset), 'function %s, line no %s\n'
    #                                                % (__name__, inspect.currentframe().f_lineno), LOGGER)
    #     # optimisations off, or (many data, or a single target) so many separate writes
    #     else:
    #         if self.simulate == True:
    #             print 'optimisations off or multiple items or single target'
    #         for target_index in range(len(targets)):
    #             if len(data) == 1 and len(targets) > 1:
    #                 datum = data[0]
    #             else:
    #                 datum = data[target_index]
    #             if datum < 0:
    #                 # big-endian integer
    #                 datum_str = struct.pack(">i", datum)
    #             else:
    #                 # big-endian unsigned integer
    #                 datum_str = struct.pack(">I", datum)
    #                 name = '%s%d_%s' % (bf_register_prefix, int(targets[target_index]['bf']), device_name)
    #                 # name = '%s_%s' % (bf_register_prefix, device_name)
    #             # pretend to write if no FPGA
    #             if self.simulate == True:
    #                 print 'dummy write of 0x%.8x to %s:%s offset %i' % (datum, targets[target_index]['fpga'],
    #                                                                     name, offset)
    #             else:
    #                 try:
    #                     if blindwrite:
    #                         targets[target_index]['fpga'].blindwrite(device_name=name, data=datum_str, offset=offset*4)
    #                     else:
    #                         targets[target_index]['fpga'].write(device_name=name, data=datum_str, offset=offset*4)
    #                 except:
    #                     raise LOGGER.error('Error writing 0x%.8x to %s:%s offset %i'
    #                                        % (datum, targets[target_index]['fpga'], name, offset*4),
    #                                        'function %s, line no %s\n'
    #                                        % (__name__, inspect.currentframe().f_lineno), LOGGER)
    #
    # #  obsolete
    # def read_int(self, device_name, offset=0, frequencies=[], fft_bins=[]):
    #     """
    #     Reads data from all devices on all bfs in all fpgas associated with the frequencies specified
    #     (less registers in new design - might be redundant as only 8 targets not 32)
    #     :param device_name:
    #     :param offset:
    #     :param frequencies:
    #     :param fft_bins:
    #     :return: values
    #     """
    #     values = []
    #     if len(fft_bins) == 0:
    #         fft_bins = self.frequency2fft_bin(frequencies)
    #     # get all unique fpgas, bfs associated with the specified frequencies
    #     targets = self.frequency2fpga_bf(frequencies, fft_bins, unique=True)
    #     for target_index, target in enumerate(targets):
    #         name = '%s%s_%s' % (self.config['beamformer']['bf_register_prefix'], target['bf'], device_name)
    #         # name = '%s_%s' % (self.config['beamformer']['bf_register_prefix'], device_name)
    #         # pretend to read if no FPGA
    #         if self.simulate == True:
    #             print 'dummy read from %s:%s offset %i' % (target['fpga'], name, offset)
    #         else:
    #             try:
    #                 values.append(target['fpga'].read_int(device_name=name))
    #             except:
    #                 raise LOGGER.error('Error reading from %s:%s offset %i' % (target['fpga'], name, offset),
    #                                    'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
    #                                    LOGGER)
    #     return values

    #  obsolete
    # def frequency2fpga_bf(self, frequencies=[], fft_bins=[], unique=False):
    #     """
    #     returns a list of dictionaries {fpga, beamformer_index} based on frequency.
    #     unique gives only unique values
    #     :param frequencies:
    #     :param fft_bins:
    #     :param unique:
    #     :return: locations
    #     """
    #     locations = []
    #     if len(fft_bins) == 0:
    #         fft_bins = self.frequency2fft_bin(frequencies=frequencies)
    #     if unique != True and unique != False:
    #         raise LOGGER.error('unique must be True or False function %s, '
    #                            'line no %s\n'
    #                            % (__name__, inspect.currentframe().f_lineno),
    #                            LOGGER)
    #     if len(fft_bins) == 0:
    #         fft_bins = self.frequency2fft_bin(frequencies)
    #     fpgas = self.frequency2fpgas(fft_bins=fft_bins)
    #     bfs = self.frequency2bf_label(fft_bins=fft_bins)
    #     if len(fpgas) != len(bfs):
    #         raise LOGGER.error('fpga and bfs associated with frequencies '
    #                            'not the same length function %s, line no %s\n'
    #                            % (__name__, inspect.currentframe().f_lineno),
    #                            LOGGER)
    #     else:
    #         pfpga = []
    #         pbf = []
    #         for index in range(len(fpgas)):
    #             fpga = fpgas[index]
    #             bf = bfs[index]
    #             if (unique == False) or (pfpga != fpga or pbf != bf):
    #                 locations.append({'fpga': fpga, 'bf': bf})
    #             pbf = bf
    #             pfpga = fpga
    #     return locations
    #
    # #  obsolete
    # def beam_frequency2location_fpga_bf(self, beams=[],
    #                                     frequencies=[], fft_bins=[], unique=False):
    #     """
    #     returns list of dictionaries {location, fpga, beamformer index} based on beam name, and frequency
    #     :param beams:
    #     :param frequencies:
    #     :param fft_bins:
    #     :param unique:
    #     :return: locations
    #     """
    #     indices = []
    #     # get beam locations
    #     locations = self.beam2location(beams)
    #     # get fpgas and bfs
    #     fpgas_bfs = self.frequency2fpga_bf(frequencies, fft_bins, unique)
    #     for location in locations:
    #         for fpga_bf in fpgas_bfs:
    #             fpga = fpga_bf['fpga']
    #             bf = fpga_bf['bf']
    #             indices.append({'location': location, 'fpga': fpga, 'bf': bf})
    #     return indices

    #  obsolete
    # def get_enabled_fft_bins(self, beam):
    #     """
    #     Returns fft bins representing band that is enabled for beam
    #     :param beam:
    #     :return: bins
    #     """
    #     bins = []
    #     cf = float(self.get_beam_param(beam, 'centre_frequency'))
    #     bw = float(self.get_beam_param(beam, 'bandwidth'))
    #     bins = self.cf_bw2fft_bins(cf, bw)
    #     return bins
    #
    # #  obsolete
    # def get_disabled_fft_bins(self, beam, frequencies=[]):
    #     """
    #     Returns fft bins representing band that is disabled for beam
    #     :param beam:
    #     :return:
    #     """
    #     all_bins = self.frequency2fft_bin(frequencies)
    #     enabled_bins = self.get_enabled_fft_bins(beam)
    #     for fft_bin in enabled_bins:
    #         all_bins.remove(fft_bin)
    #     return all_bins

