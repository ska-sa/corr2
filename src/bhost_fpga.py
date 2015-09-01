# /usr/bin/env python
"""
Selection of commonly-used beamformer control functions.

Author: Jason Manley, Andrew Martens, Ruby van Rooyen
"""
"""
Revisions:
2012-10-02 JRM Initial
2013-02-10 AM basic boresight
2013-02-11 AM basic SPEAD
2013-02-21 AM flexible bandwidth
2013-03-01 AM calibration
2013-03-02 RR fbfExceptions
2013-03-05 AM SPEAD metadata
\n"""

import numpy
import inspect
import logging
import struct
import socket
import time
import spead64_48 as spead
from casperfpga import utils

LOGGER = logging.getLogger(__name__)

class fbfException(Exception):
    def __init__(self, errno, msg, trace=None, logger=None):
        self.args = (errno, msg)
        self.errno = errno
        self.errmsg = msg
        self.__trace__ = trace
        if logger:
            logger.error('BFError: %s\n%s' % (msg, trace))

class FrequencyBeamformer(object):
    def __init__(self, host_correlator, simulate=False, optimisations=True):
        self.c = host_correlator

        self.config = self.c.configd
        #  optimisations on writes (that currently expose bugs)
        self.optimisations = optimisations
        #  simulate operations (and output debug data). Useful for when there is no hardware
        self.simulate = simulate
        self.c.b = self

        self.spead_initialise()
        LOGGER.info('Beamformer created')

# -----------------------
#  helper functions
# -----------------------

    # from corr.cn_conf.py
    def _get_ant_mapping_list(self):
        """
        assign index to each antenna and each beam for that antenna
        there's no current mapping or the mapping is bad... set default:
        :return:
        """
        n_pols = 2  # hadrcoded for now self.config['pols']
        n_inputs = int(self.config['fengine']['n_antennas'])*n_pols
        ant_list = []
        for a in range(int(self.config['fengine']['n_antennas'])):
            for p in range(n_pols):
                ant_list.append('%i%c' % (a, p))
        return ant_list[0:n_inputs]

    # from corr.corr_functions.py
    def eq_default_get(self, antennas=[], beam=[]):
        """
        Fetches the default equalisation configuration from the config file and returns
        a list of the coefficients for a given input.
        :param ant_str:
        :return:
        """
        n_coeffs = int(self.c.configd['fengine']['n_chans'])/int(
            self.c.configd['equalisation']['eq_decimation'])
        input_n = self.map_ant_to_input(beam=beam, antennas=antennas)
        if self.c.configd['equalisation']['eq_default'] == 'coeffs':
            equalisation = self.c.configd['equalisation']['eq_coeffs_%s' % input_n]
        elif self.c.configd['equalisation']['eq_default'] == 'poly':
            poly = []
            for pol in range(len(input_n)):
                poly.append(int(self.c.configd['equalisation']['eq_poly_%i' % input_n[pol]]))
            equalisation = numpy.polyval(poly, range(int(self.c.configd['fengine']['n_chans'])))[float(
                self.c.configd['equalisation']['eq_decimation'])/2::float(
                self.c.configd['equalisation']['eq_decimation'])]
            if self.c.configd['equalisation']['eq_type'] == 'complex':
                equalisation = [eq+0*1j for eq in equalisation]
        else:
            raise RuntimeError("Your EQ type, %s, is not understood." % self.c.configd['equalisation']['eq_type'])
        if len(equalisation) != n_coeffs:
            raise RuntimeError("Something's wrong. I have %i eq coefficients when I should have %i." %
                               (len(equalisation), n_coeffs))
        return equalisation

    def set_param(self, param, value):
        """
        Set beamformer parameter value
        :param param:
        :param value:
        :return:
        """
        try:
            self.config['beamformer'][param] = value
        except KeyError as ke:
            LOGGER.error('set_param: error setting value of self.config[%s]' % ke)
            raise
        except Exception as err:
            # Issues a message at the ERROR level and adds exception information to the log message
            LOGGER.exception(err.__class__)
            raise

    def get_beam_param(self, beams, param):
        """
        Read beam parameter (same for all antennas)
        :param beams: string
        :param param: location, name, centre_frequency, bandwidth, rx_meta_ip_str,
                      rx_udp_ip_str, rx_udp_port
        :return: values
        """
        values = []
        beams = self.beams2beams(beams)
        beam_indices = self.beam2index(beams)
        if beam_indices == []:
            raise fbfException(1, 'Error locating beams',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        for beam_index in beam_indices:
            values.append(self.config['beamformer']['bf_%s_beam%d' % (param, beam_index)])
        # for single item
        if len(values) == 1:
            values = values[0]
        return values

    def set_beam_param(self, beams, param, values):
        """

        :param beams:
        :param param:
        :param values:
        :return:
        """
        beams = self.beams2beams(beams)
        # check vector lengths match up
        if type(values) == list and len(values) != len(beams):
            raise fbfException(1, 'Beam vector must be same length as value vector if passing many values',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        beam_indices = self.beam2index(beams)
        if len(beam_indices) == 0:
            raise fbfException(1, 'Error locating beams',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        for index, beam_index in enumerate(beam_indices):
            if type(values) == list:
                value = values[index]
            else:
                value = values
            self.set_param('bf_%s_beam%d' % (param, beam_index), value)

    def get_fpgas(self):
        """
        Get fpga names that host b-eng (for now x-eng)
        :return: all_fpgas
        """
        # if doing dummy load (no correlator), use roach names as have not got fpgas yet
        if self.simulate == True:
            try:
                all_fpgas = self.config['xengine']['hosts']
                all_fpgas = all_fpgas.split(',')
            except:
                raise fbfException(1, 'Error accessing self.c.xsrvs',
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
        else:
            try:
                all_fpgas = self.c.xhosts
            except:
                raise fbfException(1, 'Error accessing self.c.xsrvs',
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
        return all_fpgas

    def get_bfs(self):
        """
        get bf blocks per fpga
        :return: all_bfs
        """
        all_bfs = range(int(self.config['beamformer']['bf_be_per_fpga']))
        return all_bfs

    def get_beams(self):
        """
        get a list of beam names in system (same for all antennas)
        :return: all_beams
        """
        all_beams = []
        # number of beams per beamformer
        n_beams = int(self.config['beamformer']['bf_n_beams'])
        for beam_index in range(n_beams):
            all_beams.append(self.config['beamformer']['bf_name_beam%i' % beam_index])
        return all_beams

    def map_ant_to_input(self, beam, antennas=[]):
        """
        maps antenna strings specified to input to beamformer
        gives index of antennas in the list of all_antennas
        :param beam: 'i' or 'q'
        :param ant_strs: ['0\x00', '0\x01', '1\x00', '1\x01', '2\x00', '2\x01', '3\x00', '3\x01']
        :return: inputs
        """
        beam_ants = self.ants2ants(beam=beam, antennas=antennas)
        ant_strs = self._get_ant_mapping_list()
        inputs = []
        for ant_str in beam_ants:
            if self.simulate:
                print 'finding index for %s' % ant_str
            inputs.append(ant_strs.index(ant_str))
        return inputs

    def ants2ants(self, beam, antennas=[]):
        """
        From antenna+polarisation list extract only the str for the beam
        (expands all, None etc into valid antenna strings. Checks for valid antenna strings)
        :param beam: string
        :param ant_strs:
        :return: ants
        """
        if antennas == None:
            return []
        beam = self.beams2beams(beams=beam)[0]
        # construct a list of valid ant_strs for each beam, then check specified ants are in
        if self.simulate:
            print 'finding ants for beam %s' % beam
        beam_ants = []
        beam_idx = self.beam2index(beam)[0]
        for ant_str in antennas:
            if ord(ant_str[-1]) == beam_idx:
                beam_ants.append(ant_str)
        return beam_ants

    def input2ants(self, beam, antennas=[]):
        if antennas == None:
            return []
        beam = self.beams2beams(beams=beam)[0]
        # construct a list of valid ant_strs for each beam, then check specified ants are in
        if self.simulate:
            print 'finding ants for beam %s' % beam
        beam_ants = []
        beam_idx = self.beam2index(beam)[0]
        for ant_str in antennas:
            if ord(ant_str[-1]) == beam_idx:
                beam_ants.append(int(ant_str[0]))
        return beam_ants

    def beams2beams(self, beams=[]):
        """
        expands all, None etc into valid beam names. Checks for valid beam names
        :param beams: ['i', 'q']
        :return: new_beams
        """
        new_beams = []
        if beams == None:
            return
        all_beams = self.get_beams()
        if beams == all_beams:
            new_beams = all_beams
        else:
            if type(beams) == str:
                beams = [beams]
            # weed out beam names that do not occur
            for beam in beams:
                try:
                    all_beams.index(beam)
                    new_beams.append(beam)
                except:
                    raise fbfException(1, '%s not found in our system' % beam, 'function %s, line no %s\n'
                                       % (__name__, inspect.currentframe().f_lineno), LOGGER)
        return new_beams

    def beam2index(self, beams=[]):
        """
        returns index of beam with specified name
        :param beams: 'i' or 'q' or all
        :return: indices
        """
        indices = []
        # expand all etc, check for valid names etc
        all_beams = self.get_beams()
        for beam in beams:
            indices.append(all_beams.index(beam))
        return indices

    def frequency2fpgas(self, frequencies=[], fft_bins=[], unique=False):
        """
        returns fpgas associated with frequencies specified. unique only returns unique fpgas
        e.g. for 8 x-eng there are 4096 channels produced by the f-eng and 512 different freqs per x-eng
        :param frequencies:
        :param fft_bins:
        :param unique:
        :return: fpgas
        """
        fpgas = []
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies=frequencies)
        all_fpgas = self.get_fpgas()
        n_chans = self.config['fengine']['n_chans']
        n_chans_per_fpga = int(n_chans)/len(all_fpgas)
        prev_index = -1
        for fft_bin in fft_bins:
            index = numpy.int(fft_bin/n_chans_per_fpga)  # floor built in
            if index < 0 or index > len(all_fpgas)-1:
                raise fbfException(1, 'FPGA index calculated out of range',
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
            if (unique == False) or index != prev_index:
                fpgas.append(all_fpgas[index])
            prev_index = index
        return fpgas

    def frequency2bf_label(self, frequencies=[], fft_bins=[], unique=False):
        """
        returns bf labels associated with the frequencies specified
        :param frequencies:
        :param fft_bins:
        :param unique:
        :return: bf_labels
        """
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies=frequencies)
        bf_labels = []
        bf_be_per_fpga = len(self.get_bfs())
        bf_indices = self.frequency2bf_index(frequencies, fft_bins, unique)
        for bf_index in bf_indices:
            bf_labels.append(numpy.mod(bf_index, bf_be_per_fpga))
        return bf_labels

    def frequency2bf_index(self, frequencies=[], fft_bins=[], unique=False):
        """
        returns bf indices associated with the frequencies specified
        :param frequencies:
        :param fft_bins:
        :param unique:
        :return: bf_indices
        """
        bf_indices = []
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies=frequencies)
        n_fpgas = len(self.get_fpgas())  # x-eng
        bf_be_per_fpga = len(self.get_bfs())
        n_bfs = n_fpgas*bf_be_per_fpga  # total number of bfs
        n_chans = int(self.config['fengine']['n_chans'])
        n_chans_per_bf = n_chans/n_bfs
        if max(fft_bins) > n_chans-1 or min(fft_bins) < 0:
            raise fbfException(1, 'FFT bin/s out of range', 'function %s, line no %s\n' %
                               (__name__, inspect.currentframe().f_lineno), LOGGER)
        for fft_bin in fft_bins:
            bf_index = fft_bin/n_chans_per_bf
            if unique == False or bf_indices.count(bf_index) == 0:
                bf_indices.append(bf_index)
        return bf_indices

    def frequency2frequency_reg_index(self, frequencies=[], fft_bins=[]):
        """
        Returns list of values to write into frequency register corresponding to frequency specified
        :param frequencies:
        :param fft_bins:
        :return: indices
        """
        indices = []
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies)
        n_chans = int(self.config['fengine']['n_chans'])
        bf_be_per_fpga = len(self.get_bfs())
        n_fpgas = len(self.get_fpgas())
        divisions = n_fpgas * bf_be_per_fpga
        if max(fft_bins) > n_chans-1 or min(fft_bins) < 0:
            raise fbfException(1, 'FFT bin/s out of range',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        for fft_bin in fft_bins:
            indices.append(numpy.mod(fft_bin, n_chans/divisions))
        return indices

    def frequency2fft_bin(self, frequencies=[]):
        """
        returns fft bin associated with specified frequencies
        :param frequencies:
        :return: fft_bins
        """
        fft_bins = []
        n_chans = int(self.config['fengine']['n_chans'])
        if frequencies == None:
            fft_bins = []
        elif frequencies == range(n_chans):
            fft_bins = range(n_chans)
        else:
            bandwidth = float(self.config['fengine']['bandwidth'])
            start_freq = 0
            channel_width = bandwidth/n_chans
            for frequency in frequencies:
                frequency_normalised = numpy.mod((frequency-start_freq)+channel_width/2, bandwidth)
                fft_bins.append(numpy.int(frequency_normalised/channel_width))  # conversion to int with truncation
        return fft_bins

    def get_bf_bandwidth(self):
        """
        Returns the bandwidth for one bf engine
        :return: bf_bandwidth
        """
        bandwidth = self.config['fengine']['bandwidth']
        bf_be_per_fpga = len(self.get_bfs())
        n_fpgas = len(self.get_fpgas())
        bf_bandwidth = float(bandwidth)/(bf_be_per_fpga*n_fpgas)
        return bf_bandwidth

    def get_bf_fft_bins(self):
        """
        Returns the number of fft bins for one bf engine
        :return: bf_fft_bins
        """
        n_chans = int(self.config['fengine']['n_chans'])
        bf_be_per_fpga = len(self.get_bfs())
        n_fpgas = len(self.get_fpgas())
        bf_fft_bins = n_chans/(bf_be_per_fpga*n_fpgas)
        return bf_fft_bins

    def get_fft_bin_bandwidth(self):
        """
        get bandwidth of single fft bin
        :return: fft_bin_bandwidth
        """
        n_chans = int(self.config['fengine']['n_chans'])
        bandwidth = int(self.config['fengine']['bandwidth'])
        fft_bin_bandwidth = bandwidth/n_chans
        return fft_bin_bandwidth

    def fft_bin2frequency(self, fft_bins=[]):
        """
        returns a list of centre frequencies associated with the fft bins supplied
        :param fft_bins:
        :return: frequencies
        """
        frequencies = []
        n_chans = int(self.config['fengine']['n_chans'])
        if fft_bins == range(n_chans):
            fft_bins = range(n_chans)
        if type(fft_bins) == int:
            fft_bins = [fft_bins]
        if max(fft_bins) > n_chans or min(fft_bins) < 0:
            raise fbfException(1, 'fft_bins out of range 0 -> %d' % (n_chans-1), 'function %s, line no %s\n'
                               % (__name__, inspect.currentframe().f_lineno), LOGGER)
        bandwidth = int(self.config['fengine']['bandwidth'])
        for fft_bin in fft_bins:
            frequencies.append((float(fft_bin)/n_chans)*bandwidth)
        return frequencies

    def frequency2fpga_bf(self, frequencies=[], fft_bins=[], unique=False):
        """
        returns a list of dictionaries {fpga, beamformer_index} based on frequency.
        unique gives only unique values
        :param frequencies:
        :param fft_bins:
        :param unique:
        :return: locations
        """
        locations = []
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies=frequencies)
        if unique != True and unique != False:
            raise fbfException(1, 'unique must be True or False', 'function %s, line no %s\n' %
                               (__name__, inspect.currentframe().f_lineno), LOGGER)
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies)
        fpgas = self.frequency2fpgas(fft_bins=fft_bins)
        bfs = self.frequency2bf_label(fft_bins=fft_bins)
        if len(fpgas) != len(bfs):
            raise fbfException(1, 'fpga and bfs associated with frequencies not the same length',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno), LOGGER)
        else:
            pfpga = []
            pbf = []
            for index in range(len(fpgas)):
                fpga = fpgas[index]
                bf = bfs[index]
                if (unique == False) or (pfpga != fpga or pbf != bf):
                    locations.append({'fpga': fpga, 'bf': bf})
                pbf = bf
                pfpga = fpga
        return locations

    def beam_frequency2location_fpga_bf(self, beams=[], frequencies=[], fft_bins=[], unique=False):
        """
        returns list of dictionaries {location, fpga, beamformer index} based on beam name, and frequency
        :param beams:
        :param frequencies:
        :param fft_bins:
        :param unique:
        :return: locations
        """
        indices = []
        # get beam locations
        locations = self.beam2location(beams)
        # get fpgas and bfs
        fpgas_bfs = self.frequency2fpga_bf(frequencies, fft_bins, unique)
        for location in locations:
            for fpga_bf in fpgas_bfs:
                fpga = fpga_bf['fpga']
                bf = fpga_bf['bf']
                indices.append({'location': location, 'fpga': fpga, 'bf': bf})
        return indices

    def beam2location(self, beams=[]):
        """
        returns location of beam with associated name or index
        :param beams:
        :return: locations
        """
        locations = []
        beams = self.beams2beams(beams)
        for beam in beams:
            beam_location = self.get_beam_param(beam, 'location')
            locations.append(beam_location)
        return locations

    def antenna2antenna_indices(self, beam, antennas=[]):
        """
        map antenna strings to inputs
        :param beam:
        :param ant_strs:
        :return: antenna_indices
        """
        antenna_indices = []
        n_ants = int(self.config['fengine']['n_antennas'])
        n_pols = 2  # hadrcoded for now self.config['pols']
        if len(antennas) == n_ants*n_pols:
            antenna_indices.extend(range(n_ants))
        else:
            antenna_indices = self.map_ant_to_input(beam, antennas=antennas)
        return antenna_indices

    def write_int(self, device_name, data, offset=0, frequencies=[], fft_bins=[], blindwrite=False, beam=False):
        """
        Writes data to all devices on all bfs in all fpgas associated with the frequencies specified
        :param device_name:
        :param data:
        :param offset:
        :param frequencies:
        :param fft_bins:
        :param blindwrite:
        :return:
        """
        # TODO work this out properly
        timeout = 1
        # get all fpgas, bfs associated with frequencies specified
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies)
        targets = self.frequency2fpga_bf(frequencies, fft_bins, unique=True)
        if len(data) > 1 and len(targets) != len(data):
            raise fbfException(1, 'Many data but size (%d) does not match length of targets (%d)'
                               % (len(data), len(targets)), 'function %s, line no %s\n'
                               % (__name__, inspect.currentframe().f_lineno), LOGGER)
        bf_register_prefix = self.config['beamformer']['bf_register_prefix']
        # if optimisations are enabled and (same data, and multiple targets)
        # write to all targets with the same register name
        if self.optimisations and (len(data) == 1 and len(targets) > 1):
            if self.simulate == True:
                print 'optimisations on, single data item, writing in parallel'
            n_bfs = len(self.get_bfs())
            # run through all bfs
            for bf_index in range(n_bfs):
                fpgas = []
                # generate register name
                name = '%s%s_%s' % (bf_register_prefix, bf_index, device_name)
                datum = struct.pack(">I", data[0])
                # find all fpgas to be written to for this bf
                for target in targets:
                    if target['bf'] == bf_index:
                        fpgas.append(target['fpga'])
                if len(fpgas) != 0:
                    if self.simulate == True:
                        print 'dummy executing non-blocking request for write to %s on %d fpgas' % (name, len(fpgas))
                    else:
                        nottimedout, rv = utils.threaded_non_blocking_request(self.c.xhosts, timeout, 'write',
                                                                              [name, offset*4, datum])
                        if nottimedout == False:
                            raise fbfException(1, 'Timeout asynchronously writing 0x%.8x to %s on %d fpgas offset %i'
                                               % (data[0], name, len(fpgas), offset), 'function %s, line no %s\n'
                                               % (__name__, inspect.currentframe().f_lineno), LOGGER)
                        for k, v in rv.items():
                            if v['reply'] != 'ok':
                                raise fbfException(1, 'Got %s instead of ''ok'' when writing 0x%.8x to %s:%s offset %i'
                                                   % (v['reply'], data[0], k, name, offset), 'function %s, line no %s\n'
                                                   % (__name__, inspect.currentframe().f_lineno), LOGGER)
        # optimisations off, or (many data, or a single target) so many separate writes
        else:
            if self.simulate == True:
                print 'optimisations off or multiple items or single target'
            for target_index in range(len(targets)):
                if len(data) == 1 and len(targets) > 1:
                    datum = data[0]
                else:
                    datum = data[target_index]
                if datum < 0:
                    # big-endian integer
                    datum_str = struct.pack(">i", datum)
                else:
                    # big-endian unsigned integer
                    datum_str = struct.pack(">I", datum)
                    name = '%s%d_%s' % (bf_register_prefix, int(targets[target_index]['bf']), device_name)
                    # name = '%s_%s' % (bf_register_prefix, device_name)
                # pretend to write if no FPGA
                if self.simulate == True:
                    print 'dummy write of 0x%.8x to %s:%s offset %i' % (datum, targets[target_index]['fpga'],
                                                                        name, offset)
                else:
                    try:
                        if blindwrite:
                            targets[target_index]['fpga'].blindwrite(device_name=name, data=datum_str, offset=offset*4)
                        else:
                            targets[target_index]['fpga'].write(device_name=name, data=datum_str, offset=offset*4)
                    except:
                        raise fbfException(1, 'Error writing 0x%.8x to %s:%s offset %i'
                                           % (datum, targets[target_index]['fpga'], name, offset*4),
                                           'function %s, line no %s\n'
                                           % (__name__, inspect.currentframe().f_lineno), LOGGER)

    def read_int(self, device_name, offset=0, frequencies=[], fft_bins=[]):
        """
        Reads data from all devices on all bfs in all fpgas associated with the frequencies specified
        (less registers in new design - might be redundant as only 8 targets not 32)
        :param device_name:
        :param offset:
        :param frequencies:
        :param fft_bins:
        :return: values
        """
        values = []
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies)
        # get all unique fpgas, bfs associated with the specified frequencies
        targets = self.frequency2fpga_bf(frequencies, fft_bins, unique=True)
        for target_index, target in enumerate(targets):
            name = '%s%s_%s' % (self.config['beamformer']['bf_register_prefix'], target['bf'], device_name)
            # name = '%s_%s' % (self.config['beamformer']['bf_register_prefix'], device_name)
            # pretend to read if no FPGA
            if self.simulate == True:
                print 'dummy read from %s:%s offset %i' % (target['fpga'], name, offset)
            else:
                try:
                    values.append(target['fpga'].read_int(device_name=name))
                except:
                    raise fbfException(1, 'Error reading from %s:%s offset %i' % (target['fpga'], name, offset),
                                       'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                       LOGGER)
        return values

    def read_int_bf_config(self, device_name):
        """
        Reads data from all devices on all bfs in all fpgas associated with the frequencies specified
        (config)
        :param device_name: 'data_id', 'time_id'
        :return: values
        """
        values = []
        # get all unique fpgas
        name = '%s_config_%s' % (self.config['beamformer']['bf_register_prefix'], device_name)
            # pretend to read if no FPGA
        if self.simulate == True:
            print 'dummy read from %s:%s offset %i' % name
        else:
            try:
                values = self.read_bf_config(param=device_name)
            except:
                raise fbfException(1, 'Error reading from %s' % name,
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
        return values

    def read_int_bf_control(self, device_name):
        """
        Reads data from all devices on all bfs in all fpgas associated with the frequencies specified
        (config)
        :param device_name: 'antenna' 'beng' 'frequency' 'read_destination' 'stream' 'write_destination'
        :return: values
        """
        values = []
        # get all unique fpgas
        name = '%s_control_%s' % (self.config['beamformer']['bf_register_prefix'], device_name)
            # pretend to read if no FPGA
        if self.simulate == True:
            print 'dummy read from %s:%s offset %i' % name
        else:
            try:
                values = self.read_bf_control(param=device_name)
            except:
                raise fbfException(1, 'Error reading from %s' % name,
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
        return values

    def bf_control_lookup(self, destination):
        """
        Return write/read destination
        :param destination:
        :return: id
        """
        id_control = -1
        if destination == 'duplicate':
            id_control = 0
        elif destination == 'calibrate':
            id_control = 1
        elif destination == 'steer':
            id_control = 2
        elif destination == 'combine':
            id_control = 3
        elif destination == 'visibility':
            id_control = 4
        elif destination == 'accumulate':
            id_control = 5
        elif destination == 'requantise':
            id_control = 6
        elif destination == 'filter':
            id_control = 7
        else:
            raise fbfException(1, 'Invalid destination: %s' % destination,
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        return id_control

    def bf_control_shift(self, id_control):
        control = 0
        control = control | (0x00000001 << id_control)
        return control

    #TODO re-write completely
    def bf_read_int(self, beam, destination, antennas=None, blindwrite=True):
        """
        read from destination in the bf block for a particular beam
        :param beam:
        :param destination:
        :param antennas:
        :param frequencies:
        :param blindwrite:
        :return: values
        """
        if destination == 'calibrate':
            if antennas == None:
                raise fbfException(1, 'Need to specify an antenna when reading from calibrate block',
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
        elif destination == 'filter':
            if antennas != None:
                raise fbfException(1, 'Can''t specify antenna when reading from filter block',
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
        else:
            raise fbfException(1, 'Invalid destination: %s'%destination,
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        # loop over fpgas and set the registers
        fpga_int = []
        for bf in self.get_fpgas():
            # get beam location
            location = self.beam2location(beams=beam)[0]
            # set beam (stream) based on location
            self.write_stream(bf, value=int(location))
            # set read/write destination
            id_control = self.bf_control_lookup(destination)
            control = self.bf_control_shift(id_control)
            self.write_write_destination(bf, value=control)
            # set antenna if needed
            if antennas != None:
                ant_n = self.input2ants(beam, antennas=antennas)
                if len(ant_n) == 1:
                    self.write_antenna(bf, value=ant_n[0], blindwrite=blindwrite)
                else:
                    raise fbfException(1, 'Need to specify a single antenna. Got many. Function %s, line no %s\n'
                                       % (__name__, inspect.currentframe().f_lineno), LOGGER)
            # loop over b-engs
            beng_int = []
            for beng in self.get_bfs():
                # set beng
                self.write_beng(bf, value=beng, blindwrite=blindwrite)
                # triggering write
                self.write_read_destination(bf, value=id_control)
                # read value out
                value_beng = self.read_value_out(bf)
                beng_int.append(value_beng)
            if beng_int.count(beng_int[0]) == len(beng_int):  # values are the same
                fpga_int.append(beng_int[0])
            else:
                raise fbfException(1, 'Problem: value_out on b-engines are not the same. Function %s, line no %s\n'
                                       % (__name__, inspect.currentframe().f_lineno), LOGGER)
        # check if values are the same
        if fpga_int.count(fpga_int[0]) == len(fpga_int):
            values = fpga_int[0]
        else:
            raise fbfException(1, 'Problem: value_out on fpgas are not the same. Function %s, line no %s\n'
                                       % (__name__, inspect.currentframe().f_lineno), LOGGER)
        # return single integer
        return values

    #TODO re-write completely
    def bf_write_int(self, destination, data, offset=0, beams=[], antennas=None, frequencies=[], fft_bins=[],
                     blindwrite=True):
        """
        write to various destinations in the bf block for a particular beam
        :param destination: 'calibrate', 'filter'
        :param data:
        :param offset:
        :param beams:
        :param antennas:
        :param frequencies:
        :param fft_bins:
        :param blindwrite:
        :return:
        """
        if destination == 'calibrate':
            if antennas == None:
                raise fbfException(1, 'Need to specify an antenna when writing to calibrate block',
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
            if frequencies == [] and len(fft_bins) == 0:
                raise fbfException(1, 'Need to specify a frequency or fft bin when writing to calibrate block',
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
        elif destination == 'filter':
            if antennas != None:
                raise fbfException(1, 'Can''t specify antenna for filter block',
                                   'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                                   LOGGER)
        else:
            raise fbfException(1, 'Invalid destination: %s' % destination,
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        # convert frequencies to list of fft_bins
        if len(fft_bins) == 0:
            fft_bins = self.frequency2fft_bin(frequencies)
        # assuming people don't write to the same frequency twice
        if len(fft_bins) == int(self.config['fengine']['n_chans']):
            all_freqs = True
        else:
            all_freqs = False
        # trying to write multiple data but don't have enough frequencies
        if len(data) > 1 and len(fft_bins) != len(data):
            raise fbfException(1, 'data and frequency vector lengths incompatible',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        # disable writes
        # print 'bf_write_int: disabling everything'
        self.write_int('control', [0x0], 0, fft_bins=fft_bins, blindwrite=blindwrite)
        if len(data) == 1:
            if self.simulate:
                print 'bf_write_int: setting up data for single data item'
            # set up the value to be written
            self.write_int('value_in', data, offset, fft_bins=fft_bins, blindwrite=blindwrite)
        # look up control value required to write when triggering write
        control = self.bf_control_lookup(destination)
        # beams = self.beams2beams(beams)  # check if output of this fn is correct
        # cycle through beams to be written to
        for beam in beams:
            # expand, check and convert to input indices
            ants = self.ants2ants(beam, antennas)
            antenna_indices = self.antenna2antenna_indices(beam=beam, antennas=ants)
            location = self.beam2location(beams=beam)[0]
            if self.simulate:
                print 'bf_write_int: setting up location'
            # set up target stream (location of beam in set )
            self.write_int('stream', [int(location)], 0, fft_bins=fft_bins, blindwrite=blindwrite)
            # go through antennas (normally just one but may be all or None)
            for antenna_index in antenna_indices:
                # if no frequency component (i.e all frequencies for this antenna)
                if self.simulate:
                    print 'bf_write_int: setting up antenna'
                # set up antenna register
                self.write_int('antenna', [antenna_index], 0, fft_bins=fft_bins, blindwrite=blindwrite)
                # if we are writing to all fft bins
                if all_freqs:
                    if self.simulate:
                        print 'bf_write_int: writing to'
                    bf_fft_bins = self.get_bf_fft_bins()
                    n_bfs = len(self.get_bfs()) * len(self.get_fpgas())
                    bins = range(0, n_bfs*bf_fft_bins, bf_fft_bins)
                    # list of previous bf values, guaranteed to not be the same for first item
                    pvals = [data[0]+1]*n_bfs
                    # cycle through all register indices
                    for reg_index in range(bf_fft_bins):  # 256
                        if self.simulate:
                            print 'bf_write_int: writing to frequencies that are a multiple of %d from offset %d' \
                                  % (bf_fft_bins, reg_index)
                        # write to all frequency registers
                        self.write_int('frequency', [reg_index], 0, fft_bins=bins, blindwrite=blindwrite)
                        # TODO maybe look for the same value and do asynchronous write?
                        for bf in range(n_bfs):  # 16
                            fft_bin = bf*bf_fft_bins+reg_index
                            value = data[fft_bin]
                            # if this is a new value for this bf, or first time
                            if pvals[bf] != value:
                                # now write value
                                self.write_int('value_in', [value], 0, fft_bins=[fft_bin], blindwrite=blindwrite)
                                pvals[bf] = value
                            else:
                                if self.simulate:
                                    print 'bf_write_int: skipping writing to bf %d' % bf
                        # trigger the write on first item (will happen automatically after that)
                        if reg_index == 0:
                            if self.simulate:
                                print 'bf_write_int: setting up control for first item'
                            self.write_int('control', [control], 0, fft_bins=bins, blindwrite=blindwrite)
                # otherwise we must go through one at a time
                else:
                    # cycle through frequencies
                    for index, fft_bin in enumerate(fft_bins):
                        if self.simulate:
                            print 'bf_write_int: setting up frequency'
                        # set up frequency register on bf associated with fft_bin being processed
                        self.write_int('frequency', [self.frequency2frequency_reg_index(fft_bins=[fft_bin])][0], 0,
                                       fft_bins=[fft_bin], blindwrite=blindwrite)
                        # we have a vector of data
                        if len(data) > 1:
                            # set up the value to be written
                            if self.simulate:
                                print 'bf_write_int: setting up one of multiple data values'
                            value_in = data[index]
                            # write if (we are writing all values and have just moved to next bf) or
                            # (value differs from previous)
                            self.write_int('value_in', [value_in], 0, fft_bins=[fft_bin], blindwrite=blindwrite)
                        # trigger the write
                        # set up the value to be written
                        if self.simulate:
                            print 'bf_write_int: triggering antenna, frequencies'
                        self.write_int('control', [control], 0, fft_bins=[fft_bin], blindwrite=blindwrite)
                # if no frequency component, trigger
                if len(fft_bins) == 0:
                    # trigger the write
                    if self.simulate:
                        print 'bf_write_int: triggering for no antenna but no frequencies'
                    self.write_int('control', [control], 0, fft_bins=fft_bins, blindwrite=blindwrite)
            # if no antenna component, trigger write
            if len(antenna_indices) == 0:
                # trigger the write
                if self.simulate:
                    print 'bf_write_int: triggering for no antennas (and no frequencies)'
                self.write_int('control', [control], 0, fft_bins=fft_bins, blindwrite=blindwrite)

    def cf_bw2fft_bins(self, centre_frequency, bandwidth):
        """
        returns fft bins associated with provided centre_frequency and bandwidth
        centre_frequency is assumed to be the centre of the 2^(N-1) fft bin
        :param centre_frequency:
        :param bandwidth:
        :return: bins
        """
        max_bandwidth = float(self.config['fengine']['bandwidth'])
        fft_bin_width = self.get_fft_bin_bandwidth()
        centre_frequency = float(centre_frequency)
        bandwidth = float(bandwidth)
        # TODO spectral line mode systems??
        if (centre_frequency-bandwidth/2) < 0 or \
           (centre_frequency+bandwidth/2) > max_bandwidth or \
           (centre_frequency-bandwidth/2) >= (centre_frequency+bandwidth/2):
            raise fbfException(1, 'Band specified not valid for our system',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        # get fft bin for edge frequencies
        edge_bins = self.frequency2fft_bin(frequencies=[centre_frequency-bandwidth/2,
                                                        centre_frequency+bandwidth/2-fft_bin_width])
        bins = range(edge_bins[0], edge_bins[1]+1)
        return bins

    def cf_bw2cf_bw(self, centre_frequency, bandwidth):
        """
        converts specfied centre_frequency, bandwidth to values possible for our system
        :param centre_frequency:
        :param bandwidth:
        :return: beam_centre_frequency, beam_bandwidth
        """
        bins = self.cf_bw2fft_bins(centre_frequency, bandwidth)
        bfs = self.frequency2bf_index(fft_bins=bins, unique=True)
        bf_bandwidth = self.get_bf_bandwidth()
        # calculate start frequency accounting for frequency specified in centre of bin
        start_frequency = min(bfs)*bf_bandwidth
        beam_centre_frequency = start_frequency+bf_bandwidth*(float(len(bfs))/2)
        beam_bandwidth = len(bfs) * bf_bandwidth
        return beam_centre_frequency, beam_bandwidth

    def get_enabled_fft_bins(self, beam):
        """
        Returns fft bins representing band that is enabled for beam
        :param beam:
        :return: bins
        """
        bins = []
        cf = float(self.get_beam_param(beam, 'centre_frequency'))
        bw = float(self.get_beam_param(beam, 'bandwidth'))
        bins = self.cf_bw2fft_bins(cf, bw)
        return bins

    def get_disabled_fft_bins(self, beam, frequencies=[]):
        """
        Returns fft bins representing band that is disabled for beam
        :param beam:
        :return:
        """
        all_bins = self.frequency2fft_bin(frequencies)
        enabled_bins = self.get_enabled_fft_bins(beam)
        for fft_bin in enabled_bins:
            all_bins.remove(fft_bin)
        return all_bins

    def read_bf_config(self, param=''):
        """
        Reads data from bf_config register from all x-eng
        :param 'data_id', 'time_id'
        :return: dictionary
        """
        bfs = self.get_fpgas()
        param_values = []
        for bf in bfs:
            data = bf.registers['bf_config'].read()['data'][param]
            param_values.append(data)
        return param_values

    def read_value_out(self, bf):
        # bfs = self.get_fpgas()
        data = bf.registers.bf_value_out.read()['data']['reg']
        return data

    def beng_value_out(self):
        """
        Read value_out register from all boards and all b-engines
        :return:
        """
        n_beng = self.get_bfs()
        bfs = self.get_fpgas()
        data = []
        for bf in bfs:
            val = []
            for beng in n_beng:
                self.write_beng(bf, value=beng, blindwrite=True)  # iterate over b_eng
                time.sleep(0.1)
                val.append(self.read_value_out(bf))
            if val.count(val[0]) == len(val):  # val_out are the same
                data.append({'val_out': val})
            else:
                raise fbfException(1, 'value_out associated with fpga and bfs not the same',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno), LOGGER)
        return data

    def write_data_id(self, bf, value=0):
        bf.registers['bf_config'].write(data_id=value)

    def write_time_id(self, bf, value=0):
        bf.registers['bf_config'].write(time_id=value)

    def read_bf_control(self, param=''):
        """
        Reads data from bf_control register from all x-eng
        :param 'antenna' 'beng' 'frequency' 'read_destination' 'stream' 'write_destination'
        :return: dictionary
        """
        bfs = self.get_fpgas()
        data_values = []
        for bf in bfs:
            data = bf.registers['bf_control'].read()['data'][param]
            data_values.append(data)
        return data_values

    def write_beng(self, bf, value=0, blindwrite=False):
        if blindwrite:
            bf.registers['bf_control'].blindwrite(beng=value)
        else:
            bf.registers['bf_control'].write(beng=value)

    def write_antenna(self, bf, value=0, blindwrite=False):
        if blindwrite:
            bf.registers['bf_control'].blindwrite(antenna=value)
        else:
            bf.registers['bf_control'].write(antenna=value)

    def write_stream(self, bf, value=0):
        bf.registers['bf_control'].write(stream=value)

    def write_frequency(self, bf, value=0, blindwrite=False):
        if blindwrite:
            bf.registers['bf_control'].blindwrite(frequency=value)
        else:
            bf.registers['bf_control'].write(frequency=value)

    def write_read_destination(self, bf, value=0):
        bf.registers['bf_control'].write(read_destination=value)

    def write_write_destination(self, bf, value=0):
        bf.registers['bf_control'].write(write_destination=value)


# -----------------------------------
#  Interface for standard operation
# -----------------------------------
    def initialise(self, beams=[], set_cal=True, config_output=True, send_spead=True):
        """
        Initialises the system and checks for errors.
        :param set_cal:
        :param config_output:
        :param send_spead:
        :return:
        """
        # disable all beams that are transmitting
        # beams = self.beams2beams(['i', 'q'])  # hardcoded for testing
        for beam in beams:
            if self.tx_status_get(beam):
                self.tx_stop(beam)
                LOGGER.info('Stopped beamformer %s' % beam)
        # configure spead_meta data transmitter and spead data destination,
        # don't issue related spead meta-data as will do in spead_issue_all
        if config_output:
            self.config_udp_output(beams, issue_spead=False)
            self.config_meta_output(beams, issue_spead=False)
        else:
            LOGGER.info('Skipped output configuration of beamformer.')
        if set_cal:
            self.cal_set_all(beams, spead_issue=False)
        else:
            LOGGER.info('Skipped calibration config of beamformer.')
        # if we set up calibration weights, then config has these already so don't
        # read from fpga
        if set_cal:
            from_fpga = False
        else:
            from_fpga = True
        if send_spead:
            self.spead_issue_all(beams=beams, from_fpga=from_fpga)
        else:
            LOGGER.info('Skipped issue of spead meta data.')
        LOGGER.info("Beamformer initialisation complete.")

    def tx_start(self, beams=[], frequencies=[]):
        """
        Start outputting SPEAD products. Only works for systems with 10GbE output atm.
        :param beams:
        :return:
        """
        # NOTE that the order of the following operations is significant
        # output from bfs will be enabled if any component frequencies are required
        # convert to actual beam names
        # beams = self.beams2beams(beams)  # check if output of this fn is correct
        beam_indices = self.beam2index(beams)
        for index in beam_indices:
            beam = beams[index]
            beam_index = beam_indices[index]
            # get frequency_indices associated with disabled parts of beam
            disabled_fft_bins = self.get_disabled_fft_bins(beam, frequencies)
            if len(disabled_fft_bins) > 0:
                if self.simulate == True:
                    print 'disabling excluded bfs'
                # disable bfs not required via the filter block in the beamformer
                self.bf_write_int(destination='filter', data=[0x0], offset=0x0, beams=beam,
                                  fft_bins=disabled_fft_bins)
                if self.simulate == True:
                    print 'configuring excluded bfs'
                # configure disabled beamformers to output to HEAP 0 HEAP size of 0, offset 0
                # bf_config = ((0 << 16) & (2**32 - 2**31 - 2**16) | (0 << 8) & (2**16 - 2**8) | 0 & (2**8 - 1)

                bf_config = ((0 << 16) & 0x7fff0000 | (0 << 8) & 0x0000ff00 | 0 & 0x000000ff)
                self.write_int('cfg%i' % beam_index, [bf_config], 0, fft_bins=disabled_fft_bins)
            # get frequency_indices associated with enabled parts of beams
            enabled_fft_bins = self.get_enabled_fft_bins(beam)
            # reset speadify blocks associated with fft bins required
            fpga_bf_e = self.frequency2fpga_bf(fft_bins=enabled_fft_bins, unique=True)
            bf_config = []
            for offset in enumerate(fpga_bf_e):
                bf_config.append((1 << 31))
            if self.simulate == True:
                print 'resetting included speadify blocks'
            self.write_int('cfg%i' % beam_index, bf_config, 0, fft_bins=enabled_fft_bins)
            # generate vector of values that will match the number of bfs in the list
            bf_config = []
            for offset in range(len(fpga_bf_e)):
                bf_config.append((beam_index << 16) & 0x7fff0000 | (len(fpga_bf_e) << 8) & 0x0000ff00 |
                                 offset & 0x000000ff)
            if self.simulate == True: print 'configuring included bfs'
            self.write_int('cfg%i' % beam_index, bf_config, 0, fft_bins=enabled_fft_bins)
            if self.simulate == True:
                print 'enabling included bfs'
            # lastly enable those parts
            self.bf_write_int(destination='filter', data=[0x1], offset=0x0, beams=beam,
                              fft_bins=enabled_fft_bins)
            LOGGER.info('Output for %s started' % beam)

    def tx_stop(self, beams=[], fft_bins=[], spead_stop=True):
        """
        Stops outputting SPEAD data over 10GbE links for specified beams.
        Sends SPEAD packets indicating end of stream if required
        :param beams:
        :param spead_stop:
        :return:
        """
        # beams = self.beams2beams(beams)  # check if output of this fn is correct
        for beam in beams:
            # disable all bf outputs
            self.bf_write_int(destination='filter', data=[0x0], offset=0x0, beams=beams, fft_bins=fft_bins)
            LOGGER.info("Beamformer output paused for beam %s" % beam)
            if spead_stop:
                if self.simulate == True:
                    print 'tx_stop: dummy ending SPEAD stream for beam %s' % beam
                else:
                    spead_tx = self.get_spead_tx(beam)
                    spead_tx.send_halt()
                    LOGGER.info("Sent SPEAD end-of-stream notification for beam %s" % beam)
            else:
                LOGGER.info("Did not send SPEAD end-of-stream notification for beam %s" % beam)

    def tx_status_get(self, beam, frequencies=[]):
        """
        Returns boolean true/false if the beamformer is currently outputting data.
        Currently only works on systems with 10GbE output.
        :param beam:
        :return:
        """
        # if simulating, no beam is enabled
        if self.simulate:
            return False
        rv = True
        LOGGER.info('10Ge output is currently %s' % ('enabled' if rv else 'disabled'))
        # read output status of beams
        mask = self.bf_read_int(beam=beam, frequencies=frequencies, destination='filter')
        # look to see if any portion in enabled
        if mask.count(1) != 0:
            rv = rv
        else:
            rv = False
        return rv

    def config_meta_output(self, beams=[], dest_ip_str=None, dest_port=None, issue_spead=True):
        """
        Configures the destination IP and port for SPEAD meta-data outputs. dest_port and
        dest_ip are optional parameters to override the config file defaults.
        :param beams:
        :param dest_ip_str:
        :param dest_port:
        :param issue_spead:
        :return:
        """
        # beams = self.beams2beams(beams)  # check if output of this fn is correct
        for beam in beams:
            if dest_ip_str == None:
                rx_meta_ip_str = self.get_beam_param(beam, 'rx_meta_ip_str')
            else:
                rx_meta_ip_str = dest_ip_str
                self.set_beam_param(beam, 'rx_meta_ip_str', dest_ip_str)
                self.set_beam_param(beam, 'rx_meta_ip', struct.unpack('>L', socket.inet_aton(dest_ip_str))[0])

            if dest_port == None:
                rx_meta_port = self.get_beam_param(beam, 'rx_udp_port')
            else:
                rx_meta_port = dest_port
                self.set_beam_param(beam, 'rx_udp_port', dest_port)

            self.spead_tx['bf_spead_tx_beam%i' % self.beam2index(beam)[0]] = \
                spead.Transmitter(spead.TransportUDPtx(rx_meta_ip_str, rx_meta_port))
            LOGGER.info("Destination for SPEAD meta data transmitter for beam %s changed. "
                        "New destination IP = %s, port = %d" % (beam, rx_meta_ip_str, int(rx_meta_port)))
            # reissue all SPEAD meta-data to new receiver
            if issue_spead:
                self.spead_issue_all(beam)

    def config_udp_output(self, beams=[], frequencies=[], dest_ip_str=None, dest_port=None, issue_spead=True):
        """
        Configures the destination IP and port for B engine data outputs. dest_port and dest_ip
        are optional parameters to override the config file defaults.
        :param beams:
        :param dest_ip_str:
        :param dest_port:
        :param issue_spead:
        :return:
        """
        # beams = self.beams2beams(beams)
        fft_bins = self.frequency2fft_bin(frequencies)
        for beam in beams:
            if dest_ip_str == None:
                rx_udp_ip_str = self.get_beam_param(beam, 'rx_udp_ip_str')
            else:
                rx_udp_ip_str = dest_ip_str
                self.set_beam_param(beam, 'rx_udp_ip_str', dest_ip_str)
                self.set_beam_param(beam, 'rx_udp_ip', struct.unpack('>L', socket.inet_aton(dest_ip_str))[0])
            if dest_port == None:
                rx_udp_port = self.get_beam_param(beam, 'rx_udp_port')
            else:
                rx_udp_port = dest_port
                self.set_beam_param(beam, 'rx_udp_port', dest_port)
            beam_offset = int(self.get_beam_param(beam, 'location'))
            dest_ip = struct.unpack('>L', socket.inet_aton(rx_udp_ip_str))[0]
            # restart if currently transmitting
            restart = self.tx_status_get(beam)
            if restart:
                self.tx_stop(beam)
            self.write_int('dest', fft_bins=fft_bins, data=[dest_ip], offset=(beam_offset*2))
            self.write_int('dest', fft_bins=fft_bins, data=[int(rx_udp_port)], offset=(beam_offset*2+1))
            # each beam output from each beamformer group can be configured differently
            LOGGER.info("Beam %s configured to output to %s:%i." % (beam, rx_udp_ip_str, int(rx_udp_port)))
            if issue_spead:
                self.spead_destination_meta_issue(beam)
            if restart:
                self.tx_start(beam)

    def set_passband(self, beams=[], centre_frequency=None, bandwidth=None, spead_issue=True):
        """
        sets the centre frequency and/or bandwidth for the specified beams
        :param beams:
        :param centre_frequency:
        :param bandwidth:
        :param spead_issue:
        :return:
        """
        # beams = self.beams2beams(beams)
        for beam in beams:
            # parameter checking
            if centre_frequency == None:
                cf = float(self.get_beam_param(beam, 'centre_frequency'))
            else:
                cf = centre_frequency
            if bandwidth == None:
                b = float(self.get_beam_param(beam, 'bandwidth'))
            else:
                b = bandwidth
            cf_actual, b_actual = self.cf_bw2cf_bw(cf, b)
            if centre_frequency != None:
                self.set_beam_param(beam, 'centre_frequency', cf_actual)
                LOGGER.info('Centre frequency for beam %s set to %i Hz' % (beam, cf_actual))
            if bandwidth != None:
                self.set_beam_param(beam, 'bandwidth', b_actual)
                LOGGER.info('Bandwidth for beam %s set to %i Hz' % (beam, b_actual))
            if centre_frequency != None or bandwidth != None:
                # restart if currently transmitting
                restart = self.tx_status_get(beam)
                if restart:
                    self.tx_stop(beam)
                # issue related spead meta data
                if spead_issue:
                    self.spead_passband_meta_issue(beam)
                if restart:
                    LOGGER.info('Restarting beam %s with new passband parameters' % beam)
                    self.tx_start(beam)

    def get_passband(self, beam):
        """
        gets the centre frequency and bandwidth for the specified beam
        :param beam:
        :return:
        """
        # parameter checking
        cf = self.get_beam_param(beam, 'centre_frequency')
        b = self.get_beam_param(beam, 'bandwidth')
        cf_actual, b_actual = self.cf_bw2cf_bw(cf, b)
        return cf_actual, b_actual

    def get_n_chans(self, beam):
        """
        gets the number of active channels for the specified beam
        :param beam:
        :return:
        """
        fft_bin_bandwidth = self.get_fft_bin_bandwidth()
        cf, bw = self.get_passband(beam)
        n_chans = int(bw/fft_bin_bandwidth)
        return n_chans

#   CALIBRATION

    def cal_set_all(self, beams=[], antennas=[], init_poly=[], init_coeffs=[], spead_issue=True):
        """
        Initialise all antennas for all specified beams' calibration factors to given polynomial.
        If no polynomial or coefficients are given, use defaults from config file.
        :param beams:
        :param init_poly:
        :param init_coeffs:
        :param spead_issue:
        :return:
        """
        # beams = self.beams2beams(beams)
        # go through all beams specified
        for beam in beams:
            # get all antenna input strings
            ant_strs = self.ants2ants(beam, antennas=antennas)
            # go through all antennas for beams
            for ant_str in ant_strs:
                self.cal_spectrum_set(beam=beam, antennas=ant_str, init_coeffs=init_coeffs,
                                      init_poly=init_poly, spead_issue=False)
            # issue spead packet only once all antennas are done, and don't read the values back (we have just set them)
            if spead_issue:
                self.spead_cal_meta_issue(beam, from_fpga=False)

    def cal_default_get(self, beam, antennas=[]):
        """
        Fetches the default calibration configuration from the config file and returns
        a list of the coefficients for a given beam and antenna.
        :param beam:
        :param ant_str:
        :return:
        """
        n_coeffs = int(self.c.configd['fengine']['n_chans'])
        input_n = self.map_ant_to_input(beam, antennas)
        cal_default = self.c.configd['equalisation']['eq_default']
        if cal_default == 'coeffs':
            calibration = self.get_beam_param(beam, 'cal_coeffs_input%i' % input_n)
        elif cal_default == 'poly':
            poly = []
            for pol in range(len(input_n)):
                poly.append(int(self.get_beam_param(beam, 'cal_poly_input%i' % input_n[pol])))
            calibration = numpy.polyval(poly, range(n_coeffs))
            if self.config['beamformer']['bf_cal_type'] == 'complex':
                calibration = [cal+0*1j for cal in calibration]
        else:
            raise fbfException(1, 'Your default beamformer calibration type, %s, is not understood.' % cal_default,
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        if len(calibration) != n_coeffs:
            raise fbfException(1, 'Something\'s wrong. I have %i calibration coefficients when I should have %i.'
                               % (len(calibration), n_coeffs),
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        return calibration

    def cal_default_set(self, beam, antennas, init_coeffs=[], init_poly=[]):
        """
        store current calibration settings in configuration
        :param beam:
        :param ant_str:
        :param init_coeffs:
        :param init_poly:
        :return:
        """
        n_coeffs = int(self.config['fengine']['n_chans'])
        input_n = self.map_ant_to_input(beam=beam, antennas=antennas)[0]
        if len(init_coeffs) == n_coeffs:
            self.set_beam_param(beam, 'cal_coeffs_input%i' % input_n, [init_coeffs])
            self.set_beam_param(beam, 'cal_default_input%i' % input_n, 'coeffs')
        elif len(init_poly) > 0:
            self.set_beam_param(beam, 'cal_poly_input%i' % input_n, [init_poly])
            self.set_beam_param(beam, 'cal_default_input%i' % input_n, 'poly')
        else:
            raise fbfException(1, 'calibration settings are not sensical',
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)

    def cal_fpga2floats(self, data):
        """
        Converts vector of values in format as from FPGA to float vector
        :param data:
        :return:
        """
        values = []
        bin_pt = int(self.c.configd['fengine']['quant_format'].split('.')[1])
        for datum in data:
            val_real = (numpy.int16((datum & 0xFFFF0000) >> 16))
            val_imag = (numpy.int16(datum & 0x0000FFFF))
            datum_real = numpy.float(val_real)/(2**bin_pt)
            datum_imag = numpy.float(val_imag)/(2**bin_pt)
            values.append(complex(datum_real, datum_imag))
        return values

    def cal_spectrum_get(self, beam, antennas=[], frequencies=[], from_fpga=True):
        """
        Retrieves the calibration settings currently programmed in all bengines
        for the given beam and antenna. Returns an array of length n_chans.
        :param beam:
        :param ant_str:
        :param from_fpga:
        :return:
        """
        if from_fpga:
            # read them directly from fpga
            fpga_values = self.bf_read_int(beam=beam, destination='calibrate', antennas=antennas,
                                           frequencies=frequencies)
            float_values = self.cal_fpga2floats(fpga_values)
            # float_values are not assigned here
        else:
            base_values = self.cal_default_get(beam, antennas)
            # calculate values that would be written to fpga
            fpga_values = self.cal_floats2fpga(base_values)
            float_values = self.cal_fpga2floats(fpga_values)
        return float_values

    def cal_floats2fpga(self, data):
        """
        Convert floating point values to vector for writing to FPGA
        :param data:
        :return:
        """
        values = []
        bf_cal_type = self.c.configd['beamformer']['bf_cal_type']
        if bf_cal_type == 'scalar':
            data = numpy.real(data)
        elif bf_cal_type == 'complex':
            data = numpy.array(data, dtype=numpy.complex128)
        else:
            raise fbfException(1, 'Sorry, your beamformer calibration type is not supported. Expecting scalar '
                                  'or complex.', 'function %s, line no %s\n'
                               % (__name__, inspect.currentframe().f_lineno), LOGGER)
        n_bits = int(self.config['beamformer']['bf_bits_out'])  # bf_cal_n_bits replaced
        bin_pt = int(self.c.configd['fengine']['quant_format'].split('.')[1])  # not in the config file
        whole_bits = n_bits-bin_pt
        top = 2**(whole_bits-1)-1
        bottom = -2**(whole_bits-1)
        if max(numpy.real(data)) > top or min(numpy.real(data)) < bottom:
            LOGGER.info('real calibration values out of range, will saturate')
        if max(numpy.imag(data)) > top or min(numpy.imag(data)) < bottom:
            LOGGER.info('imaginary calibration values out of range, will saturate')
        # convert data
        for datum in data:
            datum_real = numpy.real(datum)
            datum_imag = numpy.imag(datum)
            # shift up for binary point
            val_real = numpy.int32(datum_real * (2**bin_pt))
            val_imag = numpy.int32(datum_imag * (2**bin_pt))
            # pack real and imaginary values into 32 bit value
            values.append((val_real << 16) | (val_imag & 0x0000FFFF))
        return values

    def cal_spectrum_set(self, beam, antennas=[], frequencies=[], init_coeffs=[], init_poly=[], spead_issue=True):
        """Set given beam and antenna calibration settings to given co-efficients."""
        if self.simulate:
            print 'setting spectrum for beam %s antenna %s' % (beam, antennas)
        n_coeffs = self.config['fengine']['n_chans']
        if init_coeffs == [] and init_poly == []:
            coeffs = self.cal_default_get(beam=beam, antennas=antennas)
        elif len(init_coeffs) == n_coeffs:
            coeffs = init_coeffs
            self.cal_default_set(beam, antennas, init_coeffs=init_coeffs)
        elif len(init_coeffs) > 0:
            raise fbfException(1, 'You specified %i coefficients, but there are %i cal coefficients '
                                  'required for this design.' % (len(init_coeffs), n_coeffs),
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        else:
            coeffs = numpy.polyval(init_poly, range(n_coeffs))
            self.cal_default_set(beam, antennas, init_poly=init_poly)
            fpga_values = self.cal_floats2fpga(data=coeffs)
            # write final vector to calibrate block
            self.bf_write_int('calibrate', fpga_values, offset=0, beams=[beam], antennas=antennas,
                              frequencies=frequencies)
        if spead_issue:
            self.spead_cal_meta_issue(beam, from_fpga=False)

# -----------
#   SPEAD
# -----------

    def spead_initialise(self):
        """
        creates spead transmitters that will be used by the beams in our system
        :return:
        """
        self.spead_tx = dict()
        # create a spead transmitter for every beam and store in config
        beams = self.beams2beams(beams=['i', 'q'])  # hardcoded for now
        for beam in beams:
            ip_str = self.get_beam_param(beam, 'rx_meta_ip_str')
            port = self.get_beam_param(beam, 'rx_udp_port')
            self.spead_tx['bf_spead_tx_beam%i' % self.beam2index(beam)[0]] = \
                spead.Transmitter(spead.TransportUDPtx(ip_str, port))
            LOGGER.info("Created spead transmitter for beam %s. Destination IP = %s, port = %d"
                        % (beam, ip_str, int(port)))

    def get_spead_tx(self, beam):
        """

        :param beam:
        :return:
        """
        beam = self.beams2beams(beam)
        beam_index = self.beam2index(beam)[0]
        try:
            spead_tx = self.spead_tx['bf_spead_tx_beam%i' % beam_index]
        except:
            raise fbfException(1, 'Error locating SPEAD transmitter for beam %s' % beam,
                               'function %s, line no %s\n' % (__name__, inspect.currentframe().f_lineno),
                               LOGGER)
        return spead_tx

    def send_spead_heap(self, beam, ig):
        """
        Sends spead item group via transmitter for beam specified
        :param beam:
        :param ig:
        :return:
        """
        beam = self.beams2beams(beam)
        spead_tx = self.get_spead_tx(beam)
        if self.simulate:
            print 'dummy sending spead heap'
        else:
            spead_tx.send_heap(ig.get_heap())

    def spead_labelling_issue(self, beams=[]):
        """
        Issues the SPEAD metadata packets describing the labelling/location/connections
        of the system's analogue inputs.
        :param beams:
        :return:
        """
        # beams = self.beams2beams(beams)
        spead_ig = spead.ItemGroup()
        for beam in beams:
            if self.simulate:
                print 'Issuing labelling meta data for beam %s' % beam
            self.send_spead_heap(beam, spead_ig)
            LOGGER.info("Issued SPEAD metadata describing baseline labelling and input mapping for beam %s" % beam)

    def spead_static_meta_issue(self, beams=[]):
        """
        Issues the SPEAD metadata packets containing the payload and options descriptors and unpack sequences.
        :param beams:
        :return:
        """
        # beams = self.beams2beams(beams)
        # spead stuff that does not care about beam
        spead_ig = spead.ItemGroup()
        spead_ig.add_item(name="adc_clk",
                          id=0x1007,
                          description="Clock rate of ADC (samples per second).",
                          shape=[],
                          fmt=spead.mkfmt(('u', 64)),
                          init_val=self.c.configd['FxCorrelator']['sample_rate_hz'])
        spead_ig.add_item(name="n_ants",
                          id=0x100A,
                          description="The total number of dual-pol antennas in the system.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['fengine']['n_antennas'])
        spead_ig.add_item(name="n_bengs",
                          id=0x100F,
                          description="The total number of B engines in the system.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['beamformer']['bf_be_per_fpga']*len(self.get_fpgas()))
        # 1015/1016 are taken (see time_metadata_issue below)
        spead_ig.add_item(name="xeng_acc_len",
                          id=0x101F,
                          description="Number of spectra accumulated inside X engine. Determines minimum integration "
                                      "time and user-configurable integration time stepsize. X-engine correlator "
                                      "internals.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['xengine']['xeng_accumulation_len'])
        spead_ig.add_item(name="requant_bits",
                          id=0x1020,
                          description="Number of bits after requantisation in the F engines (post FFT and any "
                                      "phasing stages).",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['fengine']['sample_bits'])
        spead_ig.add_item(name="feng_pkt_len",
                          id=0x1021,
                          description="Payload size of 10GbE packet exchange between F and X engines in 64 bit words. "
                                      "Usually equal to the number of spectra accumulated inside X engine. F-engine "
                                      "correlator internals.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['fengine']['10gbe_pkt_len'])
        spead_ig.add_item(name="feng_udp_port",
                          id=0x1023,
                          description="Destination UDP port for B engine data exchange.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['fengine']['10gbe_port'])
        spead_ig.add_item(name="feng_start_ip",
                          id=0x1025,
                          description="F engine starting IP address.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['fengine']['10gbe_start_ip'])
        # TODO ADD VERSION INFO!
        spead_ig.add_item(name="b_per_fpga",
                          id=0x1047,
                          description="The number of b-engines per fpga.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['beamformer']['bf_be_per_fpga'])
        # spead_ig.add_item(name="ddc_mix_freq",
        #                   id=0x1043,
        #                   description="Digital downconverter mixing freqency as a fraction of the ADC "
        #                               "sampling frequency. eg: 0.25. Set to zero if no DDC is present.",
        #                   shape=[],
        #                   fmt=spead.mkfmt(('f', 64)),
        #                   init_val=self.config[]['ddc_mix_freq'])  # not in ini file
        spead_ig.add_item(name="adc_bits",
                          id=0x1045,
                          description="ADC quantisation (bits).",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['fengine']['sample_bits'])
        spead_ig.add_item(name="beng_out_bits_per_sample", id=0x1050,
                          description="The number of bits per value in the beng output. Note that this "
                                      "is for a single value, not the combined complex value size.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['beamformer']['bf_bits_out'])
        spead_ig.add_item(name="fft_shift",
                          id=0x101E,
                          description="The FFT bitshift pattern. F-engine correlator internals.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=self.c.configd['fengine']['fft_shift'])
        # timestamp
        spead_ig.add_item(name='timestamp',
                          id=0x1600,
                          description='Timestamp of start of this block of data. uint counting multiples '
                                      'of ADC samples since last sync (sync_time, id=0x1027). Divide this number'
                                      ' by timestamp_scale (id=0x1046) to get back to seconds since last sync '
                                      'when this block of data started.',
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=0)
        for beam in beams:
            if self.simulate:
                print 'Issuing static meta data for beam %s' % beam
            self.send_spead_heap(beam, spead_ig)
            LOGGER.info("Issued static SPEAD metadata for beam %s" % beam)

    def spead_destination_meta_issue(self, beams=[]):
        """
        Issues a SPEAD packet to notify the receiver of changes to destination
        :param beams:
        :return:
        """
        # beams = self.beams2beams(beams)
        for beam in beams:
            spead_ig = spead.ItemGroup()
            spead_ig.add_item(name="rx_udp_port",
                              id=0x1022,
                              description="Destination UDP port for B engine output.",
                              shape=[],
                              fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                              init_val=self.get_beam_param(beam, 'rx_udp_port'))
            spead_ig.add_item(name="rx_udp_ip_str",
                              id=0x1024,
                              description="Destination IP address for B engine output UDP packets.",
                              shape=[-1],
                              fmt=spead.STR_FMT,
                              init_val=self.get_beam_param(beam, 'rx_udp_ip_str'))
            if self.simulate:
                print 'Issuing destination meta data for beam %s' % beam
                self.send_spead_heap(beam, spead_ig)
                LOGGER.info("Issued destination SPEAD metadata for beam %s" % beam)

    def spead_passband_meta_issue(self, beams=[]):
        """
        Issues a SPEAD packet to notify the receiver of changes to passband parameters
        :param beams:
        :return:
        """
        # beams = self.beams2beams(beams)
        for beam in beams:
            spead_ig = spead.ItemGroup()
            cf, bw = self.get_passband(beam)
            spead_ig.add_item(name="center_freq",
                              id=0x1011,
                              description="The center frequency of the output data in Hz, 64-bit IEEE "
                                          "floating-point number.",
                              shape=[],
                              fmt=spead.mkfmt(('f', 64)),
                              init_val=cf)
            spead_ig.add_item(name="bandwidth",
                              id=0x1013,
                              description="The analogue bandwidth of the digitally processed signal in Hz.",
                              shape=[],
                              fmt=spead.mkfmt(('f', 64)),
                              init_val=bw)
            spead_ig.add_item(name="n_chans",
                              id=0x1009,
                              description="The total number of frequency channels present in the output data.",
                              shape=[],
                              fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                              init_val=self.get_n_chans(beam))
            # data item
            beam_index = self.beam2index(beam)[0]
            # id is 0xB + 12 least sig bits id of each beam
            beam_data_id = 0xB000 | (beam_index & 0x00000FFF)
            spead_ig.add_item(name=beam,
                              id=beam_data_id,
                              description="Raw data for bengines in the system. Frequencies are assembled from "
                                          "lowest frequency to highest frequency. Frequencies come in blocks of "
                                          "values in time order where the number of samples in a block is given "
                                          "by xeng_acc_len (id 0x101F). Each value is a complex number -- "
                                          "two (real and imaginary) signed integers.",
                              ndarray=numpy.ndarray(shape=(self.get_n_chans(beam),
                                                           int(self.config['xengine']['xeng_accumulation_len']), 2),
                                                    dtype=numpy.int8))
            if self.simulate:
                print 'Issuing passband meta data for beam %s' % beam
                self.send_spead_heap(beam, spead_ig)
                LOGGER.info("Issued passband SPEAD metadata for beam %s" % beam)

    def spead_time_meta_issue(self, beams=[]):
        """
        Issues a SPEAD packet to notify the receiver that we've resync'd the system, acc len has changed etc.
        :param beams:
        :return:
        """
        # beams = self.beams2beams(beams)
        spead_ig = spead.ItemGroup()
        # sync time
        if self.simulate:
            val = 0
        else:
            val = 0  # val = self.config[]['sync_time']
        spead_ig.add_item(name='sync_time',
                          id=0x1027,
                          description="Time at which the system was last synchronised (armed and triggered "
                                      "by a 1PPS) in seconds since the Unix Epoch.",
                          shape=[],
                          fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                          init_val=val)
        # scale factor for timestamp
        spead_ig.add_item(name="scale_factor_timestamp",
                          id=0x1046,
                          description="Timestamp scaling factor. Divide the SPEAD data packet timestamp "
                                      "by this number to get back to seconds since last sync.",
                          shape=[],
                          fmt=spead.mkfmt(('f', 64)))
                          # init_val=self.config[]['spead_timestamp_scale_factor'])
        for beam in beams:
            ig = spead_ig
            if self.simulate:
                    print 'Issuing time meta data for beam %s' % beam
            self.send_spead_heap(beam, ig)
            LOGGER.info("Issued SPEAD timing metadata for beam %s" % beam)

    def spead_eq_meta_issue(self, beams=[], antennas=[]):
        """
        Issues a SPEAD heap for the RF gain and EQ settings settings.
        :param beams:
        :return:
        """
        # beams = self.beams2beams(beams)
        spead_ig = spead.ItemGroup()
        # equaliser settings
        for beam in beams:
            for in_n in range(len(antennas)):
                if self.simulate:
                    vals = [[numpy.real(coeff), numpy.imag(coeff)] for coeff in self.eq_default_get(antennas, beam=beam)]
                else:
                    vals = [[numpy.real(coeff), numpy.imag(coeff)] for coeff in self.eq_spectrum_get(antennas)]
                spead_ig.add_item(name="eq_coef_%s" % antennas[in_n],
                                  id=0x1400+in_n,
                                  description="The unitless per-channel digital scaling factors implemented "
                                              "prior to requantisation, post-FFT, for input %s. Complex number "
                                              "real, imag 32 bit integers." % antennas[in_n],
                                  shape=[self.c.configd['fengine']['n_chans'], 2],
                                  fmt=spead.mkfmt(('u', 32)),
                                  init_val=vals)
                if self.simulate:
                    print 'Issuing equalisation and rf meta data for beam %s' % beam
                self.send_spead_heap(beam, spead_ig)
                LOGGER.info("Issued SPEAD EQ and RF metadata for beam %s" % beam)

    def spead_cal_meta_issue(self, beams=[], antennas=[], frequencies=[], from_fpga=True):
        """
        Issues a SPEAD heap for the RF gain, EQ settings and calibration settings.
        :param beams:
        :param from_fpga:
        :return:
        """
        # beams = self.beams2beams(beams)
        spead_ig = spead.ItemGroup()
        # override if simulating
        if self.simulate:
            from_fpga = False
        for beam in beams:
            ig = spead_ig
            # calibration settings
            for in_n in range(len(self.ants2ants(beam, antennas))):
                vals = [[numpy.real(coeff), numpy.imag(coeff)] for coeff in
                        self.cal_spectrum_get(beam, antennas, frequencies, from_fpga)]
                ig.add_item(name="beamweight_input%s" % antennas[in_n],
                            id=0x2000+in_n,
                            description="The unitless per-channel digital scaling factors implemented prior to "
                                        "combining antenna signals during beamforming for input %s. Complex number "
                                        "real,imag 64 bit floats." % antennas[in_n],
                            shape=[self.config['fengine']['n_chans'], 2],
                            fmt=spead.mkfmt(('f', 64)),
                            init_val=vals)
            if self.simulate:
                print 'Issuing calibration meta data for beam %s' % beam
                self.send_spead_heap(beam, ig)
                LOGGER.info("Issued SPEAD EQ metadata for beam %s" % beam)

    def spead_issue_all(self, beams=[], from_fpga=True):
        """
        Issues all SPEAD metadata.
        :param beams:
        :param from_fpga:
        :return:
        """
        self.spead_static_meta_issue(beams=beams)
        self.spead_passband_meta_issue(beams=beams)
        self.spead_destination_meta_issue(beams=beams)
        self.spead_time_meta_issue(beams=beams)
        self.spead_eq_meta_issue(beams=beams)
        self.spead_cal_meta_issue(beams=beams, from_fpga=from_fpga)
        self.spead_labelling_issue(beams=beams)

