import numpy
import struct
import socket
from casperfpga import utils as fpgautils
import spead64_48 as spead

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

def bf_control_lookup(destination):
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
        raise('Invalid destination %s' % destination)
    return id_control


def bf_control_shift(id_control):
    control = 0
    control = control | (0x00000001 << id_control)
    return control


def _get_ant_mapping_list(corr):
    """
    assign index to each antenna and each beam for that antenna
    there's no current mapping or the mapping is bad... set default:
    :return:
    """
    n_pols = 2  # hadrcoded for now self.config['pols']
    n_inputs = int(corr.configd['fengine']['n_antennas'])*n_pols
    ant_list = []
    for a in range(int(corr.configd['fengine']['n_antennas'])):
        for p in range(n_pols):
            ant_list.append('%i%c' % (a, p))
    return ant_list[0:n_inputs]


# from corr.corr_functions.py
def eq_default_get(corr, antennas=[], beam=[]):
    """
    Fetches the default equalisation configuration from the config file and returns
    a list of the coefficients for a given input.
    :param ant_str:
    :return:
    """
    n_coeffs = int(corr.configd['fengine']['n_chans'])/int(
        corr.configd['equalisation']['eq_decimation'])
    input_n = corr.map_ant_to_input(beam=beam, antennas=antennas)
    if corr.configd['equalisation']['eq_default'] == 'coeffs':
        equalisation = corr.configd['equalisation']['eq_coeffs_%s' % input_n]
    elif corr.configd['equalisation']['eq_default'] == 'poly':
        poly = []
        for pol in range(len(input_n)):
            poly.append(int(corr.configd['equalisation']['eq_poly_%i' % input_n[pol]]))
        equalisation = numpy.polyval(poly, range(int(corr.configd['fengine']['n_chans'])))[float(
            corr.configd['equalisation']['eq_decimation'])/2::float(
            corr.configd['equalisation']['eq_decimation'])]
        if corr.configd['equalisation']['eq_type'] == 'complex':
            equalisation = [eq+0*1j for eq in equalisation]
    else:
        raise RuntimeError("Your EQ type, %s, is not understood." % corr.configd['equalisation']['eq_type'])
    if len(equalisation) != n_coeffs:
        raise RuntimeError("Something's wrong. I have %i eq coefficients when I should have %i." %
                           (len(equalisation), n_coeffs))
    return equalisation


def get_fpgas(corr):
    """
    Get fpga names that host b-eng (for now x-eng)
    :return: all_fpgas
    """
    try:
        all_fpgas = corr.xhosts
    except:
        raise corr.logger.error('Error accessing xhosts')
    return all_fpgas


def get_bfs(corr):
    """
    get bf blocks per fpga
    :return: all_bfs
    """
    all_bfs = range(int(corr.configd['beamformer']['bf_be_per_fpga']))
    return all_bfs


def get_beams(corr):
    """
    get a list of beam names in system (same for all antennas)
    :return: all_beams
    """
    all_beams = []
    # number of beams per beamformer
    n_beams = int(corr.configd['beamformer']['bf_n_beams'])
    for beam_index in range(n_beams):
        all_beams.append(corr.configd['beamformer']['bf_name_beam%i' % beam_index])
    return all_beams


def fft_bin2frequency(corr, fft_bins=[]):
        """
        returns a list of centre frequencies associated with the fft bins supplied
        :param fft_bins:
        :return: frequencies
        """
        frequencies = []
        n_chans = int(corr.configd['fengine']['n_chans'])
        if fft_bins == range(n_chans):
            fft_bins = range(n_chans)
        if type(fft_bins) == int:
            fft_bins = [fft_bins]
        if max(fft_bins) > n_chans or min(fft_bins) < 0:
            raise corr.logging.error('fft_bins out of range 0 -> %d' % (n_chans-1))
        bandwidth = int(corr.configd['fengine']['bandwidth'])
        for fft_bin in fft_bins:
            frequencies.append((float(fft_bin)/n_chans)*bandwidth)
        return frequencies


def frequency2fft_bin(corr, frequencies=[]):
    """
    returns fft bin associated with specified frequencies
    :param frequencies:
    :return: fft_bins
    """
    fft_bins = []
    n_chans = int(corr.configd['fengine']['n_chans'])
    if frequencies == None:
        fft_bins = []
    elif frequencies == range(n_chans):
        fft_bins = range(n_chans)
    else:
        bandwidth = float(corr.configd['fengine']['bandwidth'])
        start_freq = 0
        channel_width = bandwidth/n_chans
        for frequency in frequencies:
            frequency_normalised = numpy.mod((frequency-start_freq)+channel_width/2, bandwidth)
            fft_bins.append(numpy.int(frequency_normalised/channel_width))  # conversion to int with truncation
    return fft_bins


def map_ant_to_input(corr, beam, antennas=[]):
    """
    maps antenna strings specified to input to beamformer
    gives index of antennas in the list of all_antennas
    :param beam: 'i' or 'q'
    :param ant_strs: ['0\x00', '0\x01', '1\x00', '1\x01', '2\x00', '2\x01', '3\x00', '3\x01']
    :return: inputs
    """
    beam_ants = ants2ants(corr, beam=beam, antennas=antennas)
    ant_strs = _get_ant_mapping_list(corr)
    inputs = []
    for ant_str in beam_ants:
        inputs.append(ant_strs.index(ant_str))
    return inputs


def ants2ants(corr, beam, antennas=[]):
    """
    From antenna+polarisation list extract only the str for the beam
    (expands all, None etc into valid antenna strings. Checks for valid antenna strings)
    :param beam: string
    :param ant_strs:
    :return: ants
    """
    if antennas == None:
        return []
    beam_ants = []
    beam_idx = beam2index(corr, beam)[0]
    for ant_str in antennas:
        if ord(ant_str[-1]) == beam_idx:
            beam_ants.append(ant_str)
    return beam_ants


def beam2index(corr, beams=[]):
    """
    returns index of beam with specified name
    :param beams: 'i' or 'q' or all
    :return: indices
    """
    indices = []
    # expand all etc, check for valid names etc
    all_beams = get_beams(corr)
    for beam in beams:
        indices.append(all_beams.index(beam))
    return indices


def input2ants(corr, beam, antennas=[]):
    """
    :param beam:
    :param antennas:
    :return:
    """
    if antennas == None:
        return []
    beam = beams2beams(corr, beams=beam)[0]
    beam_ants = []
    beam_idx = beam2index(corr, beam)[0]
    for ant_str in antennas:
        if ord(ant_str[-1]) == beam_idx:
            beam_ants.append(int(ant_str[0]))
    return beam_ants


def beams2beams(corr, beams=[]):
    """
    expands all, None etc into valid beam names.
    Checks for valid beam names
    :param beams: ['i', 'q']
    :return: new_beams
    """
    new_beams = []
    if beams == None:
        return
    all_beams = get_beams(corr)
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
                raise corr.logging.error('%s not found in our system' % beam)
    return new_beams


def get_bf_bandwidth(corr):
    """
    Returns the bandwidth for one bf engine
    :return: bf_bandwidth
    """
    bandwidth = corr.configd['fengine']['bandwidth']
    bf_be_per_fpga = len(get_bfs(corr))
    n_fpgas = len(get_fpgas(corr))
    bf_bandwidth = float(bandwidth)/(bf_be_per_fpga*n_fpgas)
    return bf_bandwidth


def get_bf_fft_bins(corr):
    """
    Returns the number of fft bins for one bf engine
    :return: bf_fft_bins
    """
    n_chans = int(corr.configd['fengine']['n_chans'])
    bf_be_per_fpga = len(get_bfs(corr))
    n_fpgas = len(get_fpgas(corr))
    bf_fft_bins = n_chans/(bf_be_per_fpga*n_fpgas)
    return bf_fft_bins


def get_fft_bin_bandwidth(corr):
    """
    get bandwidth of single fft bin
    :return: fft_bin_bandwidth
    """
    n_chans = int(corr.configd['fengine']['n_chans'])
    bandwidth = int(corr.configd['fengine']['bandwidth'])
    fft_bin_bandwidth = bandwidth/n_chans
    return fft_bin_bandwidth


def beam2location(corr, beams=[]):
    """
    returns location of beam with associated name or index
    :param beams:
    :return: locations
    """
    locations = []
    beams = beams2beams(corr, beams)
    for beam in beams:
        beam_location = get_beam_param(corr, beam, 'location')
        locations.append(beam_location)
    return locations


def get_beam_param(corr, beams, param):
    """
    Read beam parameter (same for all antennas)
    :param beams: string
    :param param: location, name, centre_frequency, bandwidth, rx_meta_ip_str,
                  rx_udp_ip_str, rx_udp_port
    :return: values
    """
    values = []
    beams = beams2beams(corr, beams)
    beam_indices = beam2index(corr, beams)
    if beam_indices == []:
        raise corr.logging.error('Error locating beams function')
    for beam_index in beam_indices:
        values.append(corr.configd['beamformer']['bf_%s_beam%d' % (param, beam_index)])
    # for single item
    if len(values) == 1:
        values = values[0]
    return values


def antenna2antenna_indices(corr, beam, antennas=[]):
    """
    map antenna strings to inputs
    :param beam:
    :param ant_strs:
    :return: antenna_indices
    """
    antenna_indices = []
    n_ants = int(corr.configd['fengine']['n_antennas'])
    n_pols = 2  # hadrcoded for now self.config['pols']
    if len(antennas) == n_ants*n_pols:
        antenna_indices.extend(range(n_ants))
    else:
        antenna_indices = map_ant_to_input(corr, beam, antennas=antennas)
    return antenna_indices


def bf_read_int(corr, beam, destination, antennas=None, blindwrite=True):
    """
    read from destination in the bf block for a particular beam
    :param beam:
    :param destination: 'calibrate' 'requantise' 'duplicate' 'filter'
    :param antennas:
    :param frequencies:
    :param blindwrite:
    :return: values
    """
    if destination == 'calibrate':
        if antennas == None:
            raise corr.logger.error('Need to specify an antenna when writing to calibrate block function')
    if destination == 'requantise':
        if antennas != None:
            raise corr.logger.error('Can''t specify antenna for requantise block function')
    # loop over fpgas and set the registers
    # get beam location
    location = int(beam2location(corr, beams=beam)[0])
    # set beam (stream) based on location
    THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_stream', (int(location), True)))
    # set read/write destination
    id_control = bf_control_lookup(destination)
    control = bf_control_shift(id_control)
    THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_write_destination', (control, True)))
    # set antenna if needed
    if antennas != None:
        # check if ant string is correct
        if ants2ants(corr, beam=beam, antennas=antennas) != []:
            ant_n = input2ants(corr, beam, antennas=[antennas])
            if len(ant_n) == 1:
                THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_antenna', (ant_n[0], blindwrite)))
            else:
                raise corr.logger.error('Need to specify a single antenna. Got many')
        else:
            raise corr.logger.error('Need to specify a single antenna. Got many')
    # loop over b-engs
    beng_data = []
    for beng in get_bfs(corr):
        # set beng
        THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_beng', (beng, blindwrite)))
        # triggering write
        THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_read_destination', (id_control, blindwrite)))
        # read value out
        read_bf = THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('read_value_out', ))
        if read_bf.values().count(read_bf.values()[0]) != len(read_bf.values()):  # values are not the same
            raise corr.logger.error('Problem: value_out on b-engines %i are not the same.' % beng)
        else:
            beng_data.append(read_bf.values()[0])
    if beng_data.count(beng_data[0]) == len(beng_data):
        values = beng_data[0]
    else:
        raise corr.logger.error('Problem: value_out on b-hosts are not the same.')
    # return single integer
    return values


def bf_write_int(corr, destination, data, beams=[],
                 antennas=None, frequencies=None, blindwrite=True):
    """
    write to various destinations in the bf block for a particular beam
    :param destination: 'calibrate', 'filter'
    :param data:
    :param beams:
    :param antennas:
    :param frequencies:
    :param blindwrite:
    :return:
    """
    if destination == 'calibrate':
        if antennas == None:
            raise corr.logger.error('Need to specify an antenna when writing to calibrate block')
        if frequencies == None:
            raise corr.logger.error('Need to specify a frequency when writing to calibrate block')
    if destination == 'requantise':
        if antennas != None:
            raise corr.logger.error('Can''t specify antenna for requantise block')
    # loop over fpgas and set the registers
    location = int(beam2location(corr, beams=beams)[0])
    # set beam (stream) based on location
    THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_stream', (int(location), True)))
    # set read/write destination
    id_control = bf_control_lookup(destination)
    control = bf_control_shift(id_control)
    THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_write_destination', (control, True)))
    # set antenna if needed
    if destination == 'calibrate':
        # check if ant string is correct
        if ants2ants(corr, beam=beams, antennas=antennas) != []:
            ant_n = input2ants(corr, beams, antennas=[antennas])
            THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_antenna', (ant_n[0], blindwrite)))
            # convert frequencies to list of fft_bins
            bandwidth = get_fft_bin_bandwidth(corr)
            fft_bin = cf_bw2fft_bins(corr, frequencies, bandwidth)[0]
            THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_frequency', (fft_bin, blindwrite)))
            THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_value_in', (data, blindwrite)))
        else:
            raise corr.logger.error('Need to specify a single antenna. Got many.')
    elif destination == 'duplicate' or destination == 'filter':
        THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_value_in', (data, blindwrite)))
    elif destination == 'requantise':
        bandwidth = get_fft_bin_bandwidth(corr)
        fft_bin = cf_bw2fft_bins(corr, frequencies, bandwidth)[0]
        THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_frequency', (fft_bin, blindwrite)))
        THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_value_in', (data, blindwrite)))
    else:
        raise corr.logger.error('Invalid destination')


def cf_bw2fft_bins(corr, centre_frequency, bandwidth):
    """
    returns fft bins associated with provided centre_frequency and bandwidth
    centre_frequency is assumed to be the centre of the 2^(N-1) fft bin
    :param centre_frequency:
    :param bandwidth:
    :return: bins
    """
    max_bandwidth = float(corr.configd['fengine']['bandwidth'])
    fft_bin_width = get_fft_bin_bandwidth(corr)
    centre_frequency = float(centre_frequency)
    bandwidth = float(bandwidth)
    # TODO spectral line mode systems??
    if (centre_frequency-bandwidth/2) < 0 or \
            (centre_frequency+bandwidth/2) > max_bandwidth or \
            (centre_frequency-bandwidth/2) >= (centre_frequency+bandwidth/2):
        raise corr.logger.error('Band specified not valid for our system')
    # get fft bin for edge frequencies
    edge_bins = frequency2fft_bin(corr, frequencies=[centre_frequency-bandwidth/2,
                                                     centre_frequency+bandwidth/2-fft_bin_width])
    bins = range(edge_bins[0], edge_bins[1]+1)
    return bins


def frequency2bf_index(corr, frequencies=[], fft_bins=[], unique=False):
    """
    returns bf indices associated with the frequencies specified
    :param frequencies:
    :param fft_bins:
    :param unique:
    :return: bf_indices
    """
    bf_indices = []
    if len(fft_bins) == 0:
        fft_bins = frequency2fft_bin(corr, frequencies=frequencies)
    n_fpgas = len(get_fpgas(corr))  # x-eng
    bf_be_per_fpga = len(get_bfs(corr))
    n_bfs = n_fpgas*bf_be_per_fpga  # total number of bfs
    n_chans = int(corr.configd['fengine']['n_chans'])
    n_chans_per_bf = n_chans/n_bfs
    if max(fft_bins) > n_chans-1 or min(fft_bins) < 0:
        raise corr.logging.error('FFT bin/s out of range')
    for fft_bin in fft_bins:
        bf_index = fft_bin/n_chans_per_bf
        if unique == False or bf_indices.count(bf_index) == 0:
            bf_indices.append(bf_index)
    return bf_indices


def cf_bw2cf_bw(corr, centre_frequency, bandwidth):
    """
    converts specfied centre_frequency, bandwidth to values possible for our system
    :param centre_frequency:
    :param bandwidth:
    :return: beam_centre_frequency, beam_bandwidth
    """
    bins = cf_bw2fft_bins(corr, centre_frequency, bandwidth)
    bfs = frequency2bf_index(corr, fft_bins=bins, unique=True)
    # bfs = 1  # for now
    bf_bandwidth = get_bf_bandwidth(corr)
    # calculate start frequency accounting for frequency specified in centre of bin
    start_frequency = min(bfs)*bf_bandwidth
    beam_centre_frequency = start_frequency+bf_bandwidth*(float(len(bfs))/2)
    beam_bandwidth = len(bfs) * bf_bandwidth
    return beam_centre_frequency, beam_bandwidth


# TODO
def beng_initialise(corr, beams=[], set_cal=True, config_output=True,
               send_spead=True, set_weights=True):
    """
    Initialises the b-engines and checks for errors.
    :param set_cal:
    :param config_output:
    :param send_spead:
    :return:
    """
    # disable all beams that are transmitting
    for beam in beams:
        if tx_status_get(corr, beam):
            tx_stop(corr, beam)
            corr.logger.info('Stopped beamformer %s' % beam)
    # give control register a known state
    # THREADED_FPGA_FUNC(self.get_fpgas(), timeout=10, target_function=('write_bf_control', None),)
    # configure spead_meta data transmitter and spead data destination,
    # don't issue related spead meta-data as will do in spead_issue_all
    # TODO missing registers
    if config_output:
        config_udp_output(corr, beams, issue_spead=False)
        config_meta_output(corr, beams, issue_spead=False)
    else:
        corr.logger.info('Skipped output configuration of beamformer.')
    if set_cal:
        # THREADED_FPGA_FUNC(self.get_fpgas(), timeout=10, target_function=('cal_set_all', (beams, False)))
        cal_set_all(corr, beams, spead_issue=False)
    else:
        corr.logger.info('Skipped calibration config of beamformer.')
    if set_weights:
        weights = dict()
        for beam in beams:
            weight = get_beam_weights(corr, beam)
            weights.update(weight)
            # write_int it to value_in
    # if we set up calibration weights, then config has these already so don't
    # read from fpga
    if set_cal:
        from_fpga = False
    else:
        from_fpga = True
    if send_spead:
        spead_issue_all(corr, beams=beams, from_fpga=from_fpga)
    else:
        corr.logger.info('Skipped issue of spead meta data.')
    corr.logger.info("Beamformer initialisation complete.")


def tx_start(corr, beams=[]):
    """
    Start outputting SPEAD products on all boards.
    Only works for systems with 10GbE output atm.
    :param beams:
    :return:
    """
    # NOTE that the order of the following operations is significant
    # output from bfs will be enabled if any component frequencies are required
    # loop over fpgas and set the registers
    beam_indices = beam2index(corr, beams)
    for index in beam_indices:
        value = {'beam_id': index, 'n_partitions': 0, 'rst': 1}
        THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_beam_config', (value, index, True)))
        for beng in range(int(corr.configd['beamformer']['bf_be_per_fpga'])):
            THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('write_beam_offset', (0, index, beng)))
        bf_write_int(corr, destination='filter', data=1, beams=beams[index], antennas=None, frequencies=None, blindwrite=True)  # enables output
        corr.logger.info('Output for beam %i started' % index)


# TODO
def tx_stop(corr, beams=[], spead_stop=True):
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
        THREADED_FPGA_FUNC(corr.bhosts, timeout=10, target_function=('bf_write_int',
                                                                     (corr, 'filter', 0, beam, None, None)))
        corr.logger.info("Beamformer output paused for beam %s" % beam)
        if spead_stop:
            spead_tx = get_spead_tx(corr, beam)
            spead_tx.send_halt(corr)
            corr.logger.info("Sent SPEAD end-of-stream notification for beam %s" % beam)
        else:
            corr.logger.info("Did not send SPEAD end-of-stream notification for beam %s" % beam)


# TODO
def tx_status_get(corr, beam):
    """
    Returns boolean true/false if the beamformer is currently outputting data.
    Currently only works on systems with 10GbE output.
    :param beam:
    :return:
    """
    # if simulating, no beam is enabled

    rv = True
    corr.logger.info('10Ge output is currently %s' % ('enabled' if rv else 'disabled'))
    # read output status of all beams (8 now)

    mask = [bf_read_int(corr, beam=beam, destination='filter', antennas=None)]
    # look to see if any portion in enabled
    if mask.count(1) != 0:
        rv = rv
    else:
        rv = False
    return rv


# TODO no registers
def config_meta_output(corr, beams=[], dest_ip_str=None,
                       dest_port=None, issue_spead=True):
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
            rx_meta_ip_str = get_beam_param(beam, 'rx_meta_ip_str')
        else:
            rx_meta_ip_str = dest_ip_str
            set_beam_param(beam, 'rx_meta_ip_str', dest_ip_str)
            # set_beam_param(beam, 'rx_meta_ip', struct.unpack('>L', socket.inet_aton(dest_ip_str))[0])
        if dest_port == None:
            rx_meta_port = int(get_beam_param(beam, 'rx_udp_port'))
        else:
            rx_meta_port = dest_port
            set_beam_param(beam, 'rx_udp_port', dest_port)

        # spead_tx['bf_spead_tx_beam%i' % beam2index(beam)[0]] = \
        #     spead.Transmitter(spead.TransportUDPtx(rx_meta_ip_str, rx_meta_port))
        corr.logger.info("Destination for SPEAD meta data transmitter for beam %s changed. "
                    "New destination IP = %s, port = %d" % (beam, rx_meta_ip_str, int(rx_meta_port)))
        # reissue all SPEAD meta-data to new receiver
        if issue_spead:
            spead_issue_all(beam)


# TODO no destination register
def config_udp_output(corr, beams=[], frequencies=[],
                          dest_ip_str=None, dest_port=None, issue_spead=True):
        """
        Configures the destination IP and port for B engine data outputs. dest_port and dest_ip
        are optional parameters to override the config file defaults.
        :param beams:
        :param dest_ip_str:
        :param dest_port:
        :param issue_spead:
        :return:
        """
        fft_bins = corr.frequency2fft_bin(frequencies)
        for beam in beams:
            if dest_ip_str == None:
                rx_udp_ip_str = corr.get_beam_param(beam, 'rx_udp_ip_str')
            else:
                rx_udp_ip_str = dest_ip_str
                corr.set_beam_param(beam, 'rx_udp_ip_str', dest_ip_str)
                corr.set_beam_param(beam, 'rx_udp_ip', struct.unpack('>L', socket.inet_aton(dest_ip_str))[0])
            if dest_port == None:
                rx_udp_port = corr.get_beam_param(beam, 'rx_udp_port')
            else:
                rx_udp_port = dest_port
                corr.set_beam_param(beam, 'rx_udp_port', dest_port)
            beam_offset = int(corr.get_beam_param(corr, beam, 'location'))
            dest_ip = struct.unpack('>L', socket.inet_aton(rx_udp_ip_str))[0]
            # restart if currently transmitting
            restart = corr.tx_status_get(beam)
            if restart:
                corr.tx_stop(beam)
            # no dest register
            corr.write_int('dest', fft_bins=fft_bins, data=[dest_ip], offset=(beam_offset*2))
            corr.write_int('dest', fft_bins=fft_bins, data=[int(rx_udp_port)], offset=(beam_offset*2+1))
            # each beam output from each beamformer group can be configured differently
            corr.logging.info("Beam %s configured to output to %s:%i." % (beam, rx_udp_ip_str, int(rx_udp_port)))
            if issue_spead:
                corr.spead_destination_meta_issue(beam)
            if restart:
                corr.tx_start(beam)


# TODO might be obsolete
def set_passband(corr, beams=[], centre_frequency=None,
                 bandwidth=None, spead_issue=True):
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
            cf = float(get_beam_param(beam, 'centre_frequency'))
        else:
            cf = centre_frequency
        if bandwidth == None:
            b = float(get_beam_param(beam, 'bandwidth'))
        else:
            b = bandwidth
        cf_actual, b_actual = cf_bw2cf_bw(cf, b)
        if centre_frequency != None:
            set_beam_param(beam, 'centre_frequency', cf_actual)
            corr.logger.info('Centre frequency for beam %s set to %i Hz' % (beam, cf_actual))
        if bandwidth != None:
            set_beam_param(beam, 'bandwidth', b_actual)
            corr.logger.info('Bandwidth for beam %s set to %i Hz' % (beam, b_actual))
        if centre_frequency != None or bandwidth != None:
            # restart if currently transmitting
            restart = tx_status_get(beam)
            if restart:
                tx_stop(beam)
            # issue related spead meta data
            if spead_issue:
                spead_passband_meta_issue(beam)
            if restart:
                corr.logger.info('Restarting beam %s with new passband parameters' % beam)
                tx_start(beam)


def get_passband(corr, beam):
    """
    gets the centre frequency and bandwidth for the specified beam
    :param beam:
    :return:
    """
    # parameter checking
    cf = get_beam_param(corr, beam, 'centre_frequency')
    b = get_beam_param(corr, beam, 'bandwidth')
    cf_actual, b_actual = cf_bw2cf_bw(corr, cf, b)
    return cf_actual, b_actual


def get_n_chans(corr, beam):
    """
    gets the number of active channels for the specified beam
    :param beam:
    :return:
    """
    fft_bin_bandwidth = get_fft_bin_bandwidth(corr, )
    cf, bw = get_passband(corr, beam)
    n_chans = int(bw/fft_bin_bandwidth)
    return n_chans


def get_beam_weights(corr, beams=[]):
    """
    Fetches the weights from the config file and returns
    :param beam:
    :param ant_str:
    :return:
    """
    ant_str = _get_ant_mapping_list(corr)
    # default format
    weight_default = corr.configd['beamformer']['weight_default']
    weights = dict()
    if weight_default == 'int':
        for beam in beams:
            input_n = antenna2antenna_indices(corr, beam, antennas=ant_str)
            beam_idx = beam2index(corr, beam)[0]
            for num in input_n:
                weight = int(get_beam_param(corr, beam, 'weight_ant%i' % input_n[num]))
                weights.update({'beam%i_ant%i' % (beam_idx, input_n[num]): weight})
    else:
        raise corr.logger.error('Your default beamformer weights '
                           'type, %s, is not understood.' % weight_default)
    if len(weights) != len(ant_str):
        raise corr.logger.error('Something\'s wrong. I have %i weights '
                           'when I should have %i.'
                                % (len(weights), len(ant_str)))
    return weights


# TODO
def set_beam_weights(corr, beam=0, antenna=0):
    # get weights from config per antenna
    weights = get_beam_weights(corr, [beam])
    # set the antenna
    THREADED_FPGA_FUNC(corr.bhosts, timeout=10,
                       target_function=('write_antenna', (antenna, False)))
    THREADED_FPGA_FUNC(corr.bhosts, timeout=10,
                       target_function=('write_value_in',
                                        (weights['beam%i_ant%i'
                                                 % (beam, antenna)], False)))

def cal_set_all(corr, beams=[], antennas=[], init_poly=[],
                init_coeffs=[], spead_issue=True):
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
        ant_strs = ants2ants(corr, beam, antennas=antennas)
        # go through all antennas for beams
        for ant_str in ant_strs:
            cal_spectrum_set(corr, beam=beam, antennas=ant_str, init_coeffs=init_coeffs,
                             init_poly=init_poly, spead_issue=False)
        # issue spead packet only once all antennas are done, and don't read the values back (we have just set them)
        if spead_issue:
            spead_cal_meta_issue(corr, beam, from_fpga=False)


def cal_default_get(corr, beam, antennas=[]):
    """
    Fetches the default calibration configuration from the config file and returns
    a list of the coefficients for a given beam and antenna.
    :param beam:
    :param ant_str:
    :return:
    """
    n_coeffs = int(corr.configd['fengine']['n_chans'])
    input_n = map_ant_to_input(beam, antennas)
    cal_default = corr.configd['equalisation']['eq_default']
    if cal_default == 'coeffs':
        calibration = get_beam_param(beam, 'cal_coeffs_input%i'
                                          % input_n)
    elif cal_default == 'poly':
        poly = []
        for pol in range(len(input_n)):
            poly.append(int(get_beam_param(beam, 'cal_poly_input%i'
                                                % input_n[pol])))
        calibration = numpy.polyval(poly, range(n_coeffs))
        if corr.configd['beamformer']['bf_cal_type'] == 'complex':
            calibration = [cal+0*1j for cal in calibration]
    else:
        raise corr.logger.error('Your default beamformer calibration '
                           'type, %s, is not understood.' % cal_default)
    if len(calibration) != n_coeffs:
        raise corr.logger.error('Something\'s wrong. I have %i calibration '
                           'coefficients when I should have %i.'
                           % (len(calibration), n_coeffs))
    return calibration


# TODO obsolete?
def cal_default_set(corr, beam, antennas, init_coeffs=[], init_poly=[]):
    """
    store current calibration settings in configuration
    :param beam:
    :param ant_str:
    :param init_coeffs:
    :param init_poly:
    :return:
    """
    n_coeffs = int(corr.config['fengine']['n_chans'])
    input_n = map_ant_to_input(beam=beam, antennas=antennas)[0]
    if len(init_coeffs) == n_coeffs:
        set_beam_param(beam, 'cal_coeffs_input%i' % input_n, [init_coeffs])
        set_beam_param(beam, 'cal_default_input%i' % input_n, 'coeffs')
    elif len(init_poly) > 0:
        set_beam_param(beam, 'cal_poly_input%i' % input_n, [init_poly])
        set_beam_param(beam, 'cal_default_input%i' % input_n, 'poly')
    else:
        raise corr.logger.error('calibration settings are not sensical')


def cal_fpga2floats(corr, data):
    """
    Converts vector of values in format as from FPGA to float vector
    :param data:
    :return:
    """
    values = []
    bin_pt = int(corr.configd['fengine']['quant_format'].split('.')[1])
    for datum in data:
        val_real = (numpy.int16((datum & 0xFFFF0000) >> 16))
        val_imag = (numpy.int16(datum & 0x0000FFFF))
        datum_real = numpy.float(val_real)/(2**bin_pt)
        datum_imag = numpy.float(val_imag)/(2**bin_pt)
        values.append(complex(datum_real, datum_imag))
    return values


# TODO check
def cal_spectrum_get(corr, beam, antennas=[], from_fpga=True):
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
        fpga_values = bf_read_int(corr, beam=beam, destination='calibrate', antennas=antennas)
        float_values = cal_fpga2floats(corr, fpga_values)
        # float_values are not assigned here
    else:
        base_values = cal_default_get(corr, beam, antennas)
        # calculate values that would be written to fpga
        fpga_values = cal_floats2fpga(corr, base_values)
        float_values = cal_fpga2floats(corr, fpga_values)
    return float_values


# TODO check
def cal_floats2fpga(corr, data):
    """
    Convert floating point values to vector for writing to FPGA
    :param data:
    :return:
    """
    values = []
    bf_cal_type = corr.configd['beamformer']['bf_cal_type']
    if bf_cal_type == 'scalar':
        data = numpy.real(data)
    elif bf_cal_type == 'complex':
        data = numpy.array(data, dtype=numpy.complex128)
    else:
        raise corr.logger.error('Sorry, your beamformer calibration type '
                                'is not supported. Expecting scalar or '
                                'complex.')
    n_bits = int(corr.configd['beamformer']['bf_bits_out'])  # bf_cal_n_bits replaced
    bin_pt = int(corr.configd['fengine']['quant_format'].split('.')[1])  # not in the config file
    whole_bits = n_bits-bin_pt
    top = 2**(whole_bits-1)-1
    bottom = -2**(whole_bits-1)
    if max(numpy.real(data)) > top or min(numpy.real(data)) < bottom:
        corr.logger.info('real calibration values out of range, will saturate')
    if max(numpy.imag(data)) > top or min(numpy.imag(data)) < bottom:
        corr.logger.info('imaginary calibration values out of range, will saturate')
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


# TODO smth is missing here
def cal_spectrum_set(corr, beam, antennas=[], frequencies=[],
                     init_coeffs=[], init_poly=[], spead_issue=True):
    """
    Set given beam and antenna calibration settings
    to given co-efficients.
    """
    n_coeffs = corr.config['fengine']['n_chans']
    if init_coeffs == [] and init_poly == []:
        coeffs = cal_default_get(corr, beam=beam, antennas=antennas)
    elif len(init_coeffs) == n_coeffs:
        coeffs = init_coeffs
        cal_default_set(corr, beam, antennas, init_coeffs=coeffs)
    elif len(init_coeffs) > 0:
        raise corr.logger.error('You specified %i coefficients, but there '
                           'are %i cal coefficients required for this design.'
                           % (len(init_coeffs), n_coeffs))
    else:
        coeffs = numpy.polyval(init_poly, range(n_coeffs))
        cal_default_set(corr, beam, antennas, init_poly=init_poly)
    fpga_values = cal_floats2fpga(corr, data=coeffs)
    # write final vector to calibrate block
    bf_write_int(corr, 'calibrate', fpga_values, beams=[beam], antennas=antennas,frequencies=frequencies)
    if spead_issue:
        spead_cal_meta_issue(corr, beam, from_fpga=False)


def spead_initialise(corr):
    """
    creates spead transmitters that will be used by the beams in our system
    :return:
    """
    spead_tx = dict()
    # create a spead transmitter for every beam and store in config
    beams = beams2beams(corr, beams=['i', 'q'])  # hardcoded for now
    for beam in beams:
        ip_str = get_beam_param(corr, beam, 'rx_meta_ip_str')
        port = int(get_beam_param(corr, beam, 'rx_udp_port'))
        spead_tx['bf_spead_tx_beam%i' % beam2index(corr, beam)[0]] = \
            spead.Transmitter(spead.TransportUDPtx(ip_str, port))
        corr.logger.info("Created spead transmitter for beam %s. "
                         "Destination IP = %s, port = %d"
                         % (beam, ip_str, int(port)))


# TODO check
def get_spead_tx(corr, beam):
    """
    :param beam:
    :return:
    """
    # initialise spead first
    beam_index = beam2index(corr, beam)[0]
    spead_tx = corr.spead_tx['bf_spead_tx_beam%i' % beam_index]
    try:
        spead_tx = spead_tx['bf_spead_tx_beam%i' % beam_index]
    except:
        raise corr.logger.error('Error locating SPEAD transmitter for '
                           'beam %s' % beam)
    return spead_tx


# TODO check
def send_spead_heap(corr, beam, ig):
    """
    Sends spead item group via transmitter for beam specified
    :param beam:
    :param ig:
    :return:
    """
    beam = beams2beams(corr, beam)
    spead_tx =get_spead_tx(corr, beam)
    spead_tx.send_heap(ig.get_heap())


# TODO check
def spead_labelling_issue(corr, beams=[]):
    """
    Issues the SPEAD metadata packets describing the labelling/location/connections
    of the system's analogue inputs.
    :param beams:
    :return:
    """
    # beams = self.beams2beams(beams)
    spead_ig = spead.ItemGroup()
    for beam in beams:
        send_spead_heap(corr, beam, spead_ig)
        corr.logger.info("Issued SPEAD metadata describing baseline labelling and input mapping for beam %s" % beam)


# TODO check
def spead_static_meta_issue(corr, beams=[]):
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
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['FxCorrelator']['sample_rate_hz'])
    spead_ig.add_item(name="n_ants",
                      id=0x100A,
                      description="The total number of dual-pol antennas in the system.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['fengine']['n_antennas'])
    spead_ig.add_item(name="n_bengs",
                      id=0x100F,
                      description="The total number of B engines in the system.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['beamformer']['bf_be_per_fpga']*len(get_fpgas(corr)))
    # 1015/1016 are taken (see time_metadata_issue below)
    spead_ig.add_item(name="xeng_acc_len",
                      id=0x101F,
                      description="Number of spectra accumulated inside X engine. Determines minimum integration "
                                  "time and user-configurable integration time stepsize. X-engine correlator "
                                  "internals.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['xengine']['xeng_accumulation_len'])
    spead_ig.add_item(name="requant_bits",
                      id=0x1020,
                      description="Number of bits after requantisation in the F engines (post FFT and any "
                                  "phasing stages).",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['fengine']['sample_bits'])
    spead_ig.add_item(name="feng_pkt_len",
                      id=0x1021,
                      description="Payload size of 10GbE packet exchange between F and X engines in 64 bit words. "
                                  "Usually equal to the number of spectra accumulated inside X engine. F-engine "
                                  "correlator internals.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['fengine']['10gbe_pkt_len'])
    spead_ig.add_item(name="feng_udp_port",
                      id=0x1023,
                      description="Destination UDP port for B engine data exchange.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['fengine']['10gbe_port'])
    spead_ig.add_item(name="feng_start_ip",
                      id=0x1025,
                      description="F engine starting IP address.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['fengine']['10gbe_start_ip'])
    # TODO ADD VERSION INFO!
    spead_ig.add_item(name="b_per_fpga",
                      id=0x1047,
                      description="The number of b-engines per fpga.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['beamformer']['bf_be_per_fpga'])
    spead_ig.add_item(name="adc_bits",
                      id=0x1045,
                      description="ADC quantisation (bits).",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['fengine']['sample_bits'])
    spead_ig.add_item(name="beng_out_bits_per_sample", id=0x1050,
                      description="The number of bits per value in the beng output. Note that this "
                                  "is for a single value, not the combined complex value size.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['beamformer']['bf_bits_out'])
    spead_ig.add_item(name="fft_shift",
                      id=0x101E,
                      description="The FFT bitshift pattern. F-engine correlator internals.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['fengine']['fft_shift'])
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
        send_spead_heap(corr, beam, spead_ig)
        corr.logger.info("Issued static SPEAD metadata for beam %s" % beam)


# TODO check
def spead_destination_meta_issue(corr, beams=[]):
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
                          init_val=get_beam_param(corr, beam, 'rx_udp_port'))
        spead_ig.add_item(name="rx_udp_ip_str",
                          id=0x1024,
                          description="Destination IP address for B engine output UDP packets.",
                          shape=[-1],
                          fmt=spead.STR_FMT,
                          init_val=get_beam_param(corr, beam, 'rx_udp_ip_str'))
        corr.logger.info("Issued destination SPEAD metadata for beam %s" % beam)


# TODO check
def spead_passband_meta_issue(corr, beams=[]):
    """
    Issues a SPEAD packet to notify the receiver of changes to passband parameters
    :param beams:
    :return:
    """
    # beams = self.beams2beams(beams)
    for beam in beams:
        spead_ig = spead.ItemGroup()
        cf, bw = get_passband(corr, beam)
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
                          init_val=get_n_chans(corr, beam))
        # data item
        beam_index = beam2index(corr, beam)[0]
        # id is 0xB + 12 least sig bits id of each beam
        beam_data_id = 0xB000 | (beam_index & 0x00000FFF)
        spead_ig.add_item(name=beam,
                          id=beam_data_id,
                          description="Raw data for bengines in the system. Frequencies are assembled from "
                                      "lowest frequency to highest frequency. Frequencies come in blocks of "
                                      "values in time order where the number of samples in a block is given "
                                      "by xeng_acc_len (id 0x101F). Each value is a complex number -- "
                                      "two (real and imaginary) signed integers.",
                          ndarray=numpy.ndarray(shape=(get_n_chans(corr, beam),
                                                       int(corr.configd['xengine']['xeng_accumulation_len']), 2),
                                                dtype=numpy.int8))
        send_spead_heap(corr, beam, spead_ig)
        corr.logger.info("Issued passband SPEAD metadata for beam %s" % beam)


# TODO check
def spead_time_meta_issue(corr, beams=[]):
    """
    Issues a SPEAD packet to notify the receiver that we've resync'd the system, acc len has changed etc.
    :param beams:
    :return:
    """
    # beams = self.beams2beams(beams)
    spead_ig = spead.ItemGroup()
    # sync time
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
        send_spead_heap(corr, beam, ig)
        corr.logger.info("Issued SPEAD timing metadata for beam %s" % beam)


# TODO check this eq_spectrum_get
def spead_eq_meta_issue(corr, beams=[], antennas=[]):
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
            vals = [[numpy.real(coeff), numpy.imag(coeff)] for coeff in eq_spectrum_get(corr, antennas)]
            spead_ig.add_item(name="eq_coef_%s" % antennas[in_n],
                              id=0x1400+in_n,
                              description="The unitless per-channel digital scaling factors implemented "
                                          "prior to requantisation, post-FFT, for input %s. Complex number "
                                          "real, imag 32 bit integers." % antennas[in_n],
                              shape=[corr.configd['fengine']['n_chans'], 2],
                              fmt=spead.mkfmt(('u', 32)),
                              init_val=vals)
            send_spead_heap(corr, beam, spead_ig)
            corr.logger.info("Issued SPEAD EQ and RF metadata for beam %s" % beam)


# TODO don't know if this is still the case
def eq_spectrum_get(corr, ant_str):
    """Retrieves the equaliser settings currently programmed
    in an F engine for the given antenna. Assumes equaliser
    of 16 bits. Returns an array of length n_chans."""
    ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_str_location(ant_str)
    register_name='eq%i'%(feng_input)
    n_coeffs = self.config['n_chans']/self.config['eq_decimation']

    if self.config['eq_type'] == 'scalar':
        bd=self.ffpgas[ffpga_n].read(register_name,n_coeffs*2)
        coeffs=numpy.array(struct.unpack('>%ih'%n_coeffs,bd))
        nacexp=(numpy.reshape(coeffs,(n_coeffs,1))*numpy.ones((1, self.config['eq_decimation']))).reshape(self.config['n_chans'])
        return nacexp

    elif self.config['eq_type'] == 'complex':
        bd=self.ffpgas[ffpga_n].read(register_name,n_coeffs*4)
        coeffs=struct.unpack('>%ih'%(n_coeffs*2),bd)
        na=numpy.array(coeffs,dtype=numpy.float64)
        nac=na.view(dtype=numpy.complex128)
        nacexp=(numpy.reshape(nac,(n_coeffs,1))*numpy.ones((1,self.config['eq_decimation']))).reshape(self.config['n_chans'])
        return nacexp

    else:
        log_runtimeerror(self.syslogger, "Unable to interpret eq_type from config file. Expecting scalar or complex.")


# TODO check
def spead_cal_meta_issue(corr, beams=[], antennas=[],
                         frequencies=[], from_fpga=True):
    """
    Issues a SPEAD heap for the RF gain, EQ settings and calibration settings.
    :param beams:
    :param from_fpga:
    :return:
    """
    # beams = self.beams2beams(beams)
    spead_ig = spead.ItemGroup()
    # override if simulating
    for beam in beams:
        ig = spead_ig
        # calibration settings
        for in_n in range(len(ants2ants(corr, beam, antennas))):
            vals = [[numpy.real(coeff), numpy.imag(coeff)] for coeff in
                    cal_spectrum_get(corr, beam, antennas, from_fpga)]
            ig.add_item(name="beamweight_input%s" % antennas[in_n],
                        id=0x2000+in_n,
                        description="The unitless per-channel digital scaling "
                                    "factors implemented prior to "
                                    "combining antenna signals during beamforming "
                                    "for input %s. Complex number "
                                    "real,imag 64 bit floats." % antennas[in_n],
                        shape=[corr.configd['fengine']['n_chans'], 2],
                        fmt=spead.mkfmt(('f', 64)),
                        init_val=vals)
        send_spead_heap(corr, beam, ig)
        corr.logger.info("Issued SPEAD EQ metadata for beam %s" % beam)


# TODO check
def spead_issue_all(corr, beams=[], from_fpga=True):
    """
    Issues all SPEAD metadata.
    :param beams:
    :param from_fpga:
    :return:
    """
    spead_static_meta_issue(corr, beams=beams)  # fxcorrelator.spead_issue_meta
    spead_passband_meta_issue(corr, beams=beams)
    spead_destination_meta_issue(corr, beams=beams)  # fxcorrelator.spead_issue_meta
    spead_time_meta_issue(corr, beams=beams)  # fxcorrelator.spead_issue_meta
    spead_eq_meta_issue(corr, beams=beams)  # fxcorrelator.spead_issue_meta
    spead_cal_meta_issue(corr, beams=beams, from_fpga=from_fpga)  # fxcorrelator.spead_issue_meta
    spead_labelling_issue(corr, beams=beams)  # fxcorrelator.spead_issue_meta

    # def read_int_bf_control(self, device_name):
    #     """
    #     Reads data from all devices on all bfs in all fpgas associated with the frequencies specified
    #     (config)
    #     :param device_name: 'antenna' 'beng' 'frequency' 'read_destination' 'stream' 'write_destination'
    #     :return: values
    #     """
    #     values = []
    #     # get all unique fpgas
    #     name = '%s_control_%s' % (self.config['beamformer']['bf_register_prefix'], device_name)
    #         # pretend to read if no FPGA
    #     if self.simulate == True:
    #         print 'dummy read from %s:%s offset %i' % name
    #     else:
    #         try:
    #             values = self.read_bf_control(param=device_name)
    #         except:
    #             raise LOGGER.error('Error reading from %s' % name,
    #                                'function %s, line no %s\n' % (
    #                                    __name__, inspect.currentframe().f_lineno),
    #                                LOGGER)
    #     return values

    # def read_int_bf_config(self, device_name):
    #     """
    #     Reads data from all devices on all bfs in all fpgas associated with the frequencies specified
    #     (config)
    #     :param device_name: 'data_id', 'time_id'
    #     :return: values
    #     """
    #     values = []
    #     # get all unique fpgas
    #     name = '%s_config_%s' % (self.config['beamformer']['bf_register_prefix'], device_name)
    #         # pretend to read if no FPGA
    #     if self.simulate == True:
    #         print 'dummy read from %s:%s offset %i' % name
    #     else:
    #         try:
    #             values = self.read_bf_config()
    #         except:
    #             raise LOGGER.error('Error reading from %s' % name,
    #                                'function %s, line no %s\n'
    #                                % (__name__, inspect.currentframe().f_lineno),
    #                                LOGGER)
    #     return values
