import numpy

from casperfpga import tengbe
from casperfpga import utils as fpgautils

import spead64_48 as spead

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


# TODO calibrate to 'apply_beam_weights'
def bf_control_lookup(destination):
    """
    Return write/read destination
    :param destination:
    :return: id
    """
    if destination == 'duplicate':
        return 0
    elif destination == 'calibrate':
        return 1
    elif destination == 'steer':
        return 2
    elif destination == 'combine':
        return 3
    elif destination == 'visibility':
        return 4
    elif destination == 'accumulate':
        return 5
    elif destination == 'requantise':
        return 6
    elif destination == 'filter':
        return 7
    else:
        raise('Invalid destination %s' % destination)


def bf_control_shift(id_control):
    control = 0
    control |= (0x00000001 << id_control)
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
    all_bfs = range(int(corr.configd['bengine']['bf_be_per_fpga']))
    return all_bfs


def get_beams(corr):
    """
    get a list of beam names in system (same for all antennas)
    :return: all_beams
    """
    all_beams = []
    # number of beams per beamformer
    n_beams = int(corr.configd['bengine']['bf_n_beams'])
    for beam_index in range(n_beams):
        all_beams.append(corr.configd['bengine']['bf_name_beam%i' % beam_index])
    return all_beams


def fft_bin2frequency(corr, fft_bins):
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
            raise corr.logger.error('fft_bins out of range 0 -> %d' % (n_chans-1))
        bandwidth = int(corr.configd['fengine']['bandwidth'])
        for fft_bin in fft_bins:
            frequencies.append((float(fft_bin)/n_chans)*bandwidth)
        return frequencies


def frequency2fft_bin(corr, frequencies):
    """
    returns fft bin associated with specified frequencies
    :param frequencies:
    :return: fft_bins
    """
    fft_bins = []
    n_chans = int(corr.configd['fengine']['n_chans'])
    if frequencies is None:
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


def map_ant_to_input(corr, beam, antennas):
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


def ants2ants(corr, beam, antennas):
    """
    From antenna+polarisation list extract only the str for the beam
    (expands all, None etc into valid antenna strings. Checks for valid antenna strings)
    :param beam: string
    :param ant_strs:
    :return: ants
    """
    if antennas is None:
        return []
    beam_ants = []
    beam_idx = beam2index(corr, beam)[0]
    for ant_str in antennas:
        if ord(ant_str[-1]) == beam_idx:
            beam_ants.append(ant_str)
    return beam_ants


def beam2index(corr, beams):
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


def input2ants(corr, beam, antennas):
    """
    :param beam:
    :param antennas:
    :return:
    """
    if antennas is None:
        return []
    beam = beams2beams(corr, beams=beam)[0]
    beam_ants = []
    beam_idx = beam2index(corr, beam)[0]
    for ant_str in antennas:
        if ord(ant_str[-1]) == beam_idx:
            beam_ants.append(int(ant_str[0]))
    return beam_ants


def beams2beams(corr, beams):
    """
    expands all, None etc into valid beam names.
    Checks for valid beam names
    :param beams: ['i', 'q']
    :return: new_beams
    """
    new_beams = []
    if beams is None:
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
                raise corr.logger.error('%s not found in our system' % beam)
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


def beam2location(corr, beams):
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
    if beam_indices is None:
        raise corr.logger.error('Error locating beams function')
    for beam_index in beam_indices:
        values.append(corr.configd['bengine']['bf_%s_beam%d' % (param, beam_index)])
    # for single item
    if len(values) == 1:
        values = values[0]
    return values


def antenna2antenna_indices(corr, beam, antennas):
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


def bf_read_int(corr, beam, destination, antennas=None):
    """
    read from destination in the bf block for a particular beam
    :param beam:
    :param destination: 'calibrate' 'requantise' 'duplicate' 'filter'
    :param antennas:
    :return: single value
    """
    if destination == 'calibrate':
        if antennas is None:
            raise corr.logger.error('Need to specify an antenna when writing to calibrate block function')
    if destination == 'requantise':
        if antennas is not None:
            raise corr.logger.error('Can''t specify antenna for requantise block function')
    # loop over fpgas and set the registers
    # get beam location
    location = int(beam2location(corr, beams=beam)[0])
    # set beam (stream) based on location
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_stream', [int(location)]))
    # set read/write destination
    id_control = bf_control_lookup(destination)
    control = bf_control_shift(id_control)
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_write_destination', [control]))
    # set antenna if needed
    if antennas != None and len(antennas) == 1:
        # check if ant string is correct
        if ants2ants(corr, beam=beam, antennas=antennas) != []:
            ant_n = input2ants(corr, beam, antennas=[antennas])
            if len(ant_n) == 1:
                THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_antenna', [ant_n[0]]))
            else:
                raise corr.logger.error('Need to specify a single antenna. Got many')
        else:
            raise corr.logger.error('Need to specify a single antenna. Got many')
    # loop over b-engs
    beng_data = []
    for beng in get_bfs(corr):
        # set beng
        THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beng', [beng]))
        # triggering write
        THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_read_destination', [id_control]))
        # read value out
        read_bf = THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('read_value_out', ))
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


def bf_write_int(corr, destination, data, beams=None,
                 antennas=None):
    """
    write to various destinations in the bf block for a particular beam
    :param destination: 'calibrate', 'filter'
    :param data:
    :param beams:
    :param antennas:
    :return:
    """
    if destination == 'calibrate':
        if antennas is None:
            raise corr.logger.error('Need to specify an antenna when writing to calibrate block')
    if destination == 'requantise':
        if antennas is not None:
            raise corr.logger.error('Can''t specify antenna for requantise block')
    # loop over fpgas and set the registers
    location = int(beam2location(corr, beams=beams)[0])
    # set beam (stream) based on location
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_stream', [int(location)]))
    # set read/write destination
    id_control = bf_control_lookup(destination)
    control = bf_control_shift(id_control)
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_write_destination', [control]))
    # set antenna if needed
    if destination == 'calibrate':
        # check if ant string is correct
        if len(ants2ants(corr, beam=beams, antennas=antennas)) == 0:
            ant_n = input2ants(corr, beams, antennas=[antennas])
            THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_antenna', [ant_n[0]]))
            THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_value_in', [data]))
        else:
            raise corr.logger.error('Need to specify a single antenna. Got many.')
    elif destination == 'duplicate' or destination == 'filter' or destination == 'requantise':
        THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_value_in', [data]))
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


def frequency2bf_index(corr, frequencies, fft_bins, unique=False):
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
        raise corr.logger.error('FFT bin/s out of range')
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


def beng_initialise(corr, beams, config_output=True,
                    send_spead=True, set_weights=True):
    """
    Initialises the b-engines and checks for errors.
    :param corr: correlator
    :param beams: strings
    :param config_output: bool
    :param send_spead: bool
    :param set_weights: bool
    :return: <nothing>
    """
    n_beng = int(corr.configd['bengine']['bf_be_per_fpga'])
    beam_offset_idx = range(0, n_beng*len(corr.xhosts), n_beng)
    beam_idx = beam2index(corr, beams=beams)

    # disable all beams that are transmitting
    for beam in beams:
        if bf_tx_status_get(corr, beam):
            bf_tx_stop(corr, beam)
            corr.logger.info('Stopped beamformer %s' % beam)

    # Give control register a known state.
    # Set bf_control and bf_config to zero for now
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                       target_function=('write_bf_control', (None,)),)
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                       target_function=('write_bf_config', (None,)),)

    # TODO
    # Set up default destination ip and port
    # do we increment?
    # config_meta_output(corr, beams, dest_ip_str=None,
    #                    dest_port=None, issue_spead=True)
    # config_udp_output(corr, beams, frequencies,
    #                       dest_ip_str=None, dest_port=None, issue_spead=True)

    # Set default beam config and beam IP
    # n_partitions = 32 (new register)
    # beam_id ?? (256 possible)
    for beam in beam_idx:
        THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                           target_function=('write_beam_config',
                                            ({'rst': 1, 'beam_id': 0,
                                              'n_partitions': 16}, beam)),)

    # for each beam assign which part of the band is used
    idx = 0
    for host in corr.xhosts:  # slow need improvement
        for beam in beam_idx:
            host.write_beam_offset(value=beam_offset_idx[idx],
                                   beam=beam)
        idx += 1

    if set_weights:  # set defaults, what about the antenna?
        for beam in beams:
            weights_set(corr, beam, antenna=0, coeffs=None,
                        spead_issue=False)
    else:
        corr.logger.info('Skipped applying weights config '
                         'of beamformer.')

    # configure spead_meta data transmitter and spead data destination,
    # don't issue related spead meta-data
    # TODO missing registers
    if config_output:
        config_udp_output(corr, beams, issue_spead=False)
        config_meta_output(corr, beams, issue_spead=False)
    else:
        corr.logger.info('Skipped output configuration of beamformer.')
    if send_spead:
        spead_bf_issue_all(corr, beams=beams)
    else:
        corr.logger.info('Skipped issue of spead meta data.')
    corr.logger.info("Beamformer initialisation complete.")


def tx_start(corr, beams):
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
        THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beam_config', (value, index, True)))
        for beng in range(int(corr.configd['bengine']['bf_be_per_fpga'])):
            THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beam_offset', (0, index, beng)))
        bf_write_int(corr, destination='filter', data=1, beams=beams[index], antennas=None)  # enables output
        corr.logger.info('Output for beam %i started' % index)


# TODO does it stop only bf?
def bf_tx_stop(corr, beams, spead_stop=True):
    """
    Stops outputting SPEAD data over 10GbE links for specified beams.
    Sends SPEAD packets indicating end of stream if required
    :param beams:
    :param spead_stop:
    :return:
    """
    for beam in beams:
        # disable all bf outputs
        bf_write_int(corr, 'filter', 0, beams=beam, antennas=None)
        corr.logger.info("Beamformer output paused for beam %s" % beam)
        if spead_stop:
            corr.spead_tx.send_halt()  # this doesn't stop only bf?
            corr.logger.info("Sent SPEAD end-of-stream notification for beam %s" % beam)
        else:
            corr.logger.info("Did not send SPEAD end-of-stream notification for beam %s" % beam)


def bf_tx_status_get(corr, beam):
    """
    Returns boolean true/false if the beamformer is currently outputting data.
    :param beam:
    :return: True/False
    """
    rv = True
    mask = [bf_read_int(corr, beam=beam, destination='filter', antennas=None)]
    # look to see if any portion in enabled
    if mask.count(1) != 0:
        rv = rv
    else:
        rv = False
    return rv


# TODO no registers
def config_meta_output(corr, beams, dest_ip_str=None,
                       dest_port=None, issue_spead=True):
    """
    Configures the destination IP and port for SPEAD
    meta-data outputs. dest_port and dest_ip are
    optional parameters to override the config file
    defaults.
    :param beams:
    :param dest_ip_str:
    :param dest_port:
    :param issue_spead:
    :return:
    """
    for beam in beams:
        if dest_ip_str is None:
            rx_meta_ip_str = get_beam_param(corr, beam, 'rx_meta_ip_str')
        else:
            rx_meta_ip_str = dest_ip_str
        if dest_port is None:
            rx_meta_port = int(get_beam_param(corr, beam, 'rx_udp_port'))
        else:
            rx_meta_port = dest_port
        corr.logger.info("Destination for SPEAD meta data transmitter "
                         "for beam %s changed. New destination "
                         "IP = %s, port = %d"
                         % (beam, rx_meta_ip_str, int(rx_meta_port)))
        # reissue all SPEAD meta-data to new receiver
        if issue_spead:
            spead_bf_issue_all(corr, beam)


# TODO no destination register
def config_udp_output(corr, beams, dest_ip_str=None, dest_port=None, issue_spead=True):
        """
        Configures the destination IP and port for B
        engine data outputs. dest_port and dest_ip
        are optional parameters to override the config
        file defaults.
        :param beams: str
        :param dest_ip_str:
        :param dest_port:
        :param issue_spead: bool
        :return: <nothing>
        """
        for beam in beams:
            beam_idx = beam2index(corr, beams=beam)
            if dest_ip_str is None:
                rx_udp_ip_str = get_beam_param(corr, beam, 'rx_udp_ip_str')
            else:
                rx_udp_ip_str = dest_ip_str
            if dest_port is None:
                rx_udp_port = get_beam_param(corr, beam, 'rx_udp_port')
            else:
                rx_udp_port = dest_port
            dest_ip = tengbe.IpAddress.str2ip(corr.configd['bengine']
                                              ['bf_rx_meta_ip_str_beam%i' % beam_idx[0]])

            # restart if currently transmitting
            restart = bf_tx_status_get(corr, beam)
            if restart:
                bf_tx_stop(corr, beam)

            # write ip/port
            THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beam_port', (rx_udp_port, beam)),)
            THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function=('write_beam_ip', (dest_ip, beam)),)

            # each beam output from each beamformer group can be configured differently
            corr.logging.info("Beam %s configured to output to %s:%i." % (beam, rx_udp_ip_str, int(rx_udp_port)))
            if issue_spead:
                spead_destination_meta_issue(corr, beam)
            if restart:
                tx_start(corr, beam)


# TODO might be obsolete
def set_passband(corr, beams, centre_frequency=None,
                 bandwidth=None):
    """
    sets the centre frequency and/or bandwidth for the specified beams
    :param beams:
    :param centre_frequency:
    :param bandwidth:
    :param spead_issue:
    :return:
    """
    for beam in beams:
        # parameter checking
        if centre_frequency is None:
            cf = float(get_beam_param(corr, beam, 'centre_frequency'))
        else:
            cf = centre_frequency
        if bandwidth is None:
            b = float(get_beam_param(corr, beam, 'bandwidth'))
        else:
            b = bandwidth
        cf_actual, b_actual = cf_bw2cf_bw(corr, cf, b)
        if centre_frequency is not None:
            corr.logger.info('Centre frequency for beam %s set to %i Hz' % (beam, cf_actual))
        if bandwidth is not None:
            corr.logger.info('Bandwidth for beam %s set to %i Hz' % (beam, b_actual))
        if centre_frequency is not None or bandwidth is not None:
            # restart if currently transmitting
            restart = bf_tx_status_get(corr, beam)
            if restart:
                bf_tx_stop(corr, beam)
            # issue related spead meta data
            if restart:
                corr.logger.info('Restarting beam %s with new passband parameters' % beam)
                tx_start(corr, beam)


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


def weights_default_get(corr, beams, antennas):
    """
    Fetches the default weights configuration from the config file and returns
    a list of the weights for a given beam and antenna.
    :param beams: strings
    :param antennas:
    :return: dictionary with beam%i_ant%i keys
    """
    weight_default = corr.configd['bengine']['bf_weights_default']
    weights = dict()
    if weight_default == 'coef':
        for beam in beams:
            beam_idx = beam2index(corr, beam)[0]
            for ant in antennas:
                weight = get_beam_param(corr, beam, 'weight_ant%i' % ant)
                weights.update({'beam%i_ant%i' % (beam_idx, ant): int(weight)})
    else:
        raise corr.logger.error('Your default beamformer calibration '
                                'type, %s, is not understood.'
                                % weight_default)
    return weights


def weights_default_set(corr, beam, antenna=0):
    """
    Set the default weights configuration from the config file
    :param beam: for single beam in str form
    :param ant_str: for single antenna in int form
    :return:
    """
    beam_idx = beam2index(corr, beam)[0]
    weights = weights_default_get(corr, beams=[beam],
                                  antennas=[antenna])
    # set the antenna
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                       target_function=('write_antenna', [antenna]))
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                       target_function=('write_value_in',
                                        [weights['beam%i_ant%i'
                                                 % (beam_idx, antenna)]]))


def weights_get(corr, beams, antennas, default=True):
    """
    Retrieves the calibration settings currently programmed
    in all b-engines for the given beam and antenna or
    retrieves from config file.
    :param beam: for single beam in str form
    :param antenna: for single antenna in int form
    :param default: True for default False for
                   current weights
    :return:
    """
    if default is True:
        weights = weights_default_get(corr, beams=[beams],
                                      antennas=antennas)
    else:
        weights = dict()
        for beam in beams:
            for ant in antennas:
                beam_char = beam2index(corr, beams=beam)[0]
                beam_idx = beam2index(corr, beam)[0]
                ant_char = '%i%c' % (ant, beam_char)
                weight = bf_read_int(corr, beam,
                                     destination='calibrate',
                                     antennas=ant_char)
                weights.update({'beam%i_ant%i'
                                % (beam_idx, ant): int(weight)})
    return weights


def weights_set(corr, beam, antenna=0, coeffs=None,
                spead_issue=True):
    """
    Set given beam and antenna calibration settings
    to given co-efficients.
    :param corr:
    :param beam:
    :param antennas:
    :param coeffs:
    :param spead_issue:
    :return:
    """
    if coeffs is None:
        weights_default_set(corr, beam, antenna=antenna)
    elif len(coeffs) == 1:  # we set a single value
        # write final vector to calibrate block
        # set the antenna
        beam_char = beam2index(corr, beams=beam)[0]
        ant = '%i%c' % (antenna, beam_char)
        bf_write_int(corr, 'calibrate', coeffs[0], beams=beam, antennas=ant)
    else:
        corr.logger.error('Your coefficient %s is not recognised.' % coeffs)
    if spead_issue:
        spead_weights_meta_issue(corr, beam)


def spead_bf_meta_issue(corr, beams):
    """
    Issues the SPEAD metadata packets containing the payload
    and options descriptors and unpack sequences.
    :param beams:
    :return:
    """
    #  check if SPEAD transmitter was created
    if corr.meta_destination is None:
            corr.logger.info('SPEAD meta destination is still unset, '
                             'NOT sending metadata at this time.')
            return
    # SPEAD stuff that does not care about beam
    spead_ig = spead.ItemGroup()
    spead_ig.add_item(name="n_bengs",
                      id=0x100F,
                      description="The total number of B engines in the system.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['bengine']['bf_be_per_fpga']*len(corr.xhosts))
    spead_ig.add_item(name="b_per_fpga",
                      id=0x1047,
                      description="The number of b-engines per fpga.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['bengine']['bf_be_per_fpga'])
    spead_ig.add_item(name="beng_out_bits_per_sample",
                      id=0x1050,
                      description="The number of bits per value in the beng output. Note that this "
                                  "is for a single value, not the combined complex value size.",
                      shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)),
                      init_val=corr.configd['bengine']['bf_bits_out'])
    for beam in beams:
        beam_index = beam2index(corr, beam)[0]
        # id is 0xB + 12 least sig bits id of each beam
        beam_data_id = 0xB000 + beam_index
        spead_ig.add_item(name=beam,
                          id=beam_data_id,
                          description="Raw data for bengines in the system. Frequencies are assembled from "
                                      "lowest frequency to highest frequency. Frequencies come in blocks of "
                                      "values in time order where the number of samples in a block is given "
                                      "by xeng_acc_len (id 0x101F). Each value is a complex number -- "
                                      "two (real and imaginary) signed integers.",
                          ndarray=numpy.ndarray(shape=(int(corr.configd['fengine']['n_chans']),
                                                       int(corr.configd['xengine']['xeng_accumulation_len']), 2),
                                                dtype=numpy.int8))
        corr.logger.info("Issued static SPEAD metadata for beam %s" % beam)
    corr.spead_tx.send_heap(corr.spead_meta_ig.get_heap())


def spead_destination_meta_issue(corr, beams):
    """
    Issues a SPEAD packet to notify the receiver of changes to destination
    :param beams:
    :return:
    """
    #  check if SPEAD transmitter was created
    if corr.meta_destination is None:
            corr.logger.info('SPEAD meta destination is still unset, '
                             'NOT sending metadata at this time.')
            return
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
        corr.spead_tx.send_heap(corr.spead_meta_ig.get_heap())


def spead_weights_meta_issue(corr, beams):
    """
    Issues a SPEAD heap for the weights settings.
    :param beams:
    :param from_fpga:
    :return:
    """
    #  check if SPEAD transmitter was created
    if corr.meta_destination is None:
            corr.logger.info('SPEAD meta destination is still unset, '
                             'NOT sending metadata at this time.')
            return
    spead_ig = spead.ItemGroup()
    for beam in beams:
        ig = spead_ig
        # weights settings
        for in_n in range(int(corr.configd['fengine']['n_antennas'])):
            beam_char = beam2index(corr, beams=beam)[0]
            val = weights_get(corr, beam, antennas=[in_n], default=False)
            ig.add_item(name="beam%i_ant%i" % (beam_char, in_n),
                        id=0x2000+in_n,
                        description="The unitless per-channel digital scaling "
                                    "factors implemented prior to "
                                    "combining antenna signals during beamforming "
                                    "for input beam%i_ant%i. Complex number "
                                    "real 32 bit floats." % (beam_char, in_n),
                        shape=[],
                        fmt=spead.mkfmt(('f', 32)),
                        init_val=val)
        corr.logger.info("Issued SPEAD EQ metadata for beam %s" % beam)
        corr.spead_tx.send_heap(corr.spead_meta_ig.get_heap())


def spead_bf_issue_all(corr, beams):
    """
    Issues all SPEAD metadata.
    :param beams:
    :param from_fpga:
    :return:
    """
    spead_bf_meta_issue(corr, beams=beams)
    spead_destination_meta_issue(corr, beams=beams)
    spead_weights_meta_issue(corr, beams=beams)
