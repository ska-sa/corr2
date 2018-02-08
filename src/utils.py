import logging
import os
import numpy as np
from ConfigParser import SafeConfigParser
import Queue
import threading
import time

from casperfpga.memory import bin2fp
import casperfpga.utils as fpgautils

from data_stream import StreamAddress
from casperfpga import CasperFpga

LOGGER = logging.getLogger(__name__)


class AdcData(object):

    @staticmethod
    def eighty_to_ten(list_w80):
        """
        Convert a list of 80-bit words to 10-bit adc samples
        :param list_w80: a list of 80-bit words, each with eight 10-bit adc samples
        :return: a list of ten-bit ADC samples
        """
        ten_bit_samples = []
        for word80 in list_w80:
            for ctr in range(70, -1, -10):
                tenbit = (word80 >> ctr) & 1023
                tbsigned = bin2fp(tenbit, 10, 9, True)
                ten_bit_samples.append(tbsigned)
        return ten_bit_samples

    @staticmethod
    def sixty_four_to_eighty(list_w64):
        """
        Convert a list of 64-bit words to 80-bit words from the ADC
        :param list_w64: a list of 64-bit words, typically straight from the gbe
        :return: a list of 80-bit words, as rxd from the ADC
        """
        words80 = []
        for wordctr in range(0, len(list_w64), 5):
            word64_0 = list_w64[wordctr + 0]
            word64_1 = list_w64[wordctr + 1]
            word64_2 = list_w64[wordctr + 2]
            word64_3 = list_w64[wordctr + 3]
            word64_4 = list_w64[wordctr + 4]
            word80_0 = (((word64_1 & 0x000000000000ffff) << 64) |
                        ((word64_0 & 0xffffffffffffffff) << 0))
            word80_1 = (((word64_2 & 0x00000000ffffffff) << 48) |
                        ((word64_1 & 0xffffffffffff0000) >> 16))
            word80_2 = (((word64_3 & 0x0000ffffffffffff) << 32) |
                        ((word64_2 & 0xffffffff00000000) >> 32))
            word80_3 = (((word64_4 & 0xffffffffffffffff) << 16) |
                        ((word64_3 & 0xffff000000000000) >> 48))
            words80.append(word80_0)
            words80.append(word80_1)
            words80.append(word80_2)
            words80.append(word80_3)
        return words80

    @staticmethod
    def sixty_four_to_eighty_skarab(list_w64):
        """
        Convert a list of 64-bit words to 80-bit words from the ADC
        :param list_w64: a list of 64-bit words, typically straight from the gbe
        :return: a list of 80-bit words, as rxd from the ADC
        """
        words80 = []
        for wordctr in range(0, len(list_w64), 5):
            word64_0 = list_w64[wordctr + 0]
            word64_1 = list_w64[wordctr + 1]
            word64_2 = list_w64[wordctr + 2]
            word64_3 = list_w64[wordctr + 3]
            word64_4 = list_w64[wordctr + 4]
            word80_0 = (((word64_0 & 0xffffffffffffffff) << 16) +
                        ((word64_1 & 0xffff000000000000) >> 48))
            word80_1 = (((word64_1 & 0x0000ffffffffffff) << 32) +
                        ((word64_2 & 0xffffffff00000000) >> 32))
            word80_2 = (((word64_2 & 0x00000000ffffffff) << 48) +
                        ((word64_3 & 0xffffffffffff0000) >> 16))
            word80_3 = (((word64_3 & 0x000000000000ffff) << 64) +
                        ((word64_4 & 0xffffffffffffffff) >> 0))
            words80.append(word80_0)
            words80.append(word80_1)
            words80.append(word80_2)
            words80.append(word80_3)
        return words80


def parse_slx_params(string):
    """
    Given a Matlab Simulink parameter field, return its contents
    as a list
    :param string:
    :return: list
    """
    string = string.replace('[', '').replace(']', '')
    string = string.replace(', ', ' ').replace('  ', ' ')
    return string.split()


def parse_ini_file(ini_file='', required_sections=None):
    """
    Parse an ini file into a dictionary. No checking done at all.
    :param ini_file: the ini file to process
    :param required_sections: sections that MUST be included
    :return: a dictionary containing the configuration
    """
    if (ini_file == '') and ('CORR2INI' in os.environ.keys()):
        ini_file = os.environ['CORR2INI']
        LOGGER.info('Defaulting to config env var $CORR2INI=%s' % ini_file)
    if required_sections is None:
        required_sections = []
    parser = SafeConfigParser()
    files = parser.read(ini_file)
    if len(files) == 0:
        raise IOError('Could not read the config file, %s' % ini_file)
    for check_section in required_sections:
        if not parser.has_section(check_section):
            raise ValueError(
                'The config file does not seem to have the required %s '
                'section?' % (check_section,))
    config = {}
    for section in parser.sections():
        config[section] = {}
        for items in parser.items(section):
            config[section][items[0]] = items[1]
    return config


# def parse_hosts(str_file_dict, section=None):
#     """
#     Make a list of hosts from the argument given to a script.
#     :param str_file_dict: a string, file or dictionary where hosts may be found
#     :param section: the config section from which to take hosts, if applicable
#     :return: a list: [(section, hosts, bitstreams), ...]
#     """
#     # is is just a string, a comma-seperated list of hosts?
#     if hasattr(str_file_dict, 'islower'):
#         return [
#             (None, [host.strip() for host in str_file_dict.split(',')], None)
#         ]
#     if hasattr(str_file_dict, 'keys'):
#         config, config_file = str_file_dict, None
#     else:
#         config, config_file = None, str_file_dict
#     return hosts_and_bitstreams_from_config(
#         config_file=config_file, config=config, section=section
#     )


def hosts_and_bitstreams_from_config(config_file=None, config=None,
                                     section=None):
    """
    Make lists of hosts and their corresponding bitstream from a given 
    correlator config file or config dictionary.
    :param config_file: a corr2 config file
    :param config: a corr2 config dictionary
    :param section: 'fengine', 'xengine', etc
    :return: a list: [(section, hosts, bitstreams), ...]
    """
    config = config or parse_ini_file(config_file)
    hosts_by_section = []
    for section_name, cfg_section in config.items():
        host_or_hosts = 'hosts' in cfg_section or 'host' in cfg_section
        if (not host_or_hosts) or ('bitstream' not in cfg_section):
            continue
        if 'hosts' in cfg_section:
            host_list = [
                host.strip() for host in cfg_section['hosts'].split(',')
            ]
        else:
            host_list = [cfg_section['host'].strip()]
        hosts_by_section.append(
            (section_name, host_list, cfg_section['bitstream'])
        )
    if section is not None:
        rv = []
        if not hasattr(section, 'pop'):
            section = [section]
        for val in hosts_by_section:
            if val[0] in section:
                rv.append(val)
        if not rv:
            raise RuntimeError('Could not find section \'%s\'.' % section)
        return config, rv
    return config, hosts_by_section


def _script_get_hosts(cmdline_args, host_type=None):
    """
    Given command line arguments, find hosts
    :param cmdline_args: the parsed args object from the script
    :param host_type: 'fengine', 'xengine', etc
    :return: the config dict and a list: [(host_type, hosts, bitstreams), ...]
    """
    # looks for a hosts keyword in the cmdline args
    if hasattr(cmdline_args, 'hosts'):
        if cmdline_args.hosts.strip() != '':
            try:
                bitstream_def = cmdline_args.bitstream.strip()
            except AttributeError:
                bitstream_def = None
            host_list = [host.strip() for host in cmdline_args.hosts.split(',')]
            return [(None, host_list, bitstream_def)]
    config_def = None
    if hasattr(cmdline_args, 'config') and (cmdline_args.config is not None):
        config_def = cmdline_args.config.strip()
    elif 'CORR2INI' in os.environ.keys():
        config_def = os.environ['CORR2INI']
    else:
        raise RuntimeError('Could not get host information '
                           'from provided arguments.')
    config, host_detail = hosts_and_bitstreams_from_config(
        config_file=config_def, section=host_type)
    return config, host_detail


def feng_script_get_fpgas(cmdline_args):
    from fhost_fpga import FpgaFHost
    return script_get_fpgas(cmdline_args, 'fengine', FpgaFHost)


def feng_script_get_fpga(cmdline_args):
    from fhost_fpga import FpgaFHost
    return script_get_fpga(cmdline_args, host_type='fengine',
                           fpga_class=FpgaFHost)


def xeng_script_get_fpgas(cmdline_args):
    from xhost_fpga import FpgaXHost
    return script_get_fpgas(cmdline_args, 'xengine', FpgaXHost)


def xeng_script_get_fpga(cmdline_args):
    from xhost_fpga import FpgaXHost
    return script_get_fpga(cmdline_args, host_type='xengine',
                           fpga_class=FpgaXHost)


def script_get_fpgas(cmdline_args, host_type=None, fpga_class=CasperFpga):
    """
    Given command line arguments, return CASPER FPGA objects
    :param cmdline_args: the parsed args object from the script
    :param host_type: 'fengine', 'xengine', etc
    :param fpga_class: a specific CasperFpga (sub)class, if required
    :return: a list of CasperFpga objects
    """
    config, host_details = _script_get_hosts(cmdline_args, host_type)
    fpgas = []
    for val in host_details:
        fhosts = fpgautils.threaded_create_fpgas_from_hosts(val[1], fpga_class)
        if hasattr(fhosts[0].transport, 'katcprequest'):
            gsi_args = []
        else:
            gsi_args = [val[2]]
        fpgautils.threaded_fpga_function(
            fpga_list=fhosts, timeout=15,
            target_function=('get_system_information', gsi_args, {}))
        fpgas.extend(fhosts)
    return fpgas


def script_get_fpga(cmdline_args, host_name=None, host_index=-1,
                    host_type=None, fpga_class=CasperFpga):
    """
    Given command line arguments, return a CasperFpga object specified by the
    argument 'host'
    :param cmdline_args: the parsed args object from the script
    :param host_name: the hostname of the FPGA to return
    :param host_index: the index of the FPGA to return
    :param host_type: 'fengine', 'xengine', etc
    :param fpga_class: a specific CasperFpga (sub)class, if required
    :return: a CasperFpga objects
    """
    if host_name is not None:
        pass
    elif host_index > -1:
        pass
    elif hasattr(cmdline_args, 'host'):
        try:
            host_index, host_name = int(cmdline_args.host.strip()), ''
        except ValueError:
            host_index, host_name = -1, cmdline_args.host.strip()
    else:
        raise RuntimeError('No host index or name given.')
    config, host_details = _script_get_hosts(cmdline_args, host_type)
    host_ctr = 0
    host_fpga = None
    bitstream = None
    for val in host_details:
        for host in val[1]:
            if host_ctr == host_index:
                host_fpga = host
                bitstream = val[2]
                break
            elif host == host_name:
                host_fpga = host
                bitstream = val[2]
                break
            host_ctr += 1
        if host_fpga is not None:
            break
    if host_fpga is None:
        raise RuntimeError('Could not find host: \'%s,%s\'' % (
            str(host_name), str(host_index)))
    fpga = fpga_class(host_fpga)
    if hasattr(fpga.transport, 'katcprequest'):
        fpga.get_system_information()
    else:
        fpga.get_system_information(bitstream)
    return fpga


def sources_from_config(config_file=None, config=None):
    """
    Get a list of the sources given by the config
    :param config_file: a corr2 config file
    :param config: a corr2 config dictionary
    :return:
    """
    config = config or parse_ini_file(config_file)
    sources = config['fengine']['source_names'].split(',')
    for ctr, src in enumerate(sources):
        sources[ctr] = src.strip()
    return sources


def host_to_sources(hosts, config_file=None, config=None):
    """
    Get sources related to a host
    :param hosts: a list of hosts
    :param config_file: a corr2 config file
    :param config: a corr2 config dictionary
    :return:
    """
    config = config or parse_ini_file(config_file)
    f_per_fpga = int(config['fengine']['f_per_fpga'])
    cfg, host_detail = hosts_and_bitstreams_from_config(
        config=config, section='fengine')
    fhosts = host_detail[0][1]
    sources = sources_from_config(config=config)
    if len(sources) != len(fhosts) * f_per_fpga:
        raise RuntimeError('%i hosts, %i per fpga_host, expected %i '
                           'sources' % (len(fhosts), f_per_fpga, len(sources)))
    ctr = 0
    rv = {}
    for host in fhosts:
        rv[host] = (sources[ctr], sources[ctr+1])
        ctr += 2
    return rv


def source_to_host(sources, config_file=None, config=None):
    """
    Get sources related to a host
    :param sources: a list of sources
    :param config_file: a corr2 config file
    :param config: a corr2 config dictionary
    :return:
    """
    config = config or parse_ini_file(config_file)
    cfg, host_detail = hosts_and_bitstreams_from_config(
        config=config, section='fengine')
    fhosts = host_detail[0][1]
    source_host_dict = host_to_sources(fhosts, config=config)
    ctr = 0
    rv = {}
    for source in sources:
        for host in source_host_dict:
            if source in source_host_dict[host]:
                rv[source] = host
                break
    return rv


def baselines_from_source_list(source_list):
    """
    Get a list of the baselines from a source list.
    :param source_list:
    :return:
    """
    n_antennas = len(source_list) / 2
    order1 = []
    order2 = []
    for ant_ctr in range(n_antennas):
        # print('ant_ctr(%d)' % ant_ctr
        for ctr2 in range(int(n_antennas / 2), -1, -1):
            temp = (ant_ctr - ctr2) % n_antennas
            # print('\tctr2(%d) temp(%d)' % (ctr2, temp)
            if ant_ctr >= temp:
                order1.append((temp, ant_ctr))
            else:
                order2.append((ant_ctr, temp))
    order2 = [order_ for order_ in order2 if order_ not in order1]
    baseline_order = order1 + order2
    source_names = []
    for source in source_list:
        source_names.append(source)
    rv = []
    for baseline in baseline_order:
        rv.append((source_names[baseline[0] * 2],
                   source_names[baseline[1] * 2]))
        rv.append((source_names[baseline[0] * 2 + 1],
                   source_names[baseline[1] * 2 + 1]))
        rv.append((source_names[baseline[0] * 2],
                   source_names[baseline[1] * 2 + 1]))
        rv.append((source_names[baseline[0] * 2 + 1],
                   source_names[baseline[1] * 2]))
    return rv


def baselines_from_config(config_file=None, config=None):
    """
    Get a list of the baselines from a config file.
    :param config_file: a corr2 config file
    :param config: a corr2 config dictionary
    :return:
    """
    config = config or parse_ini_file(config_file)
    sources = sources_from_config(config=config)
    cfg, host_detail = hosts_and_bitstreams_from_config(
        config=config, section='fengine')
    fhosts = host_detail[0][1]
    n_antennas = len(fhosts)
    if len(sources) / 2 != n_antennas:
        raise ValueError('Found {} sources, but {} antennas?'.format(
            len(sources), n_antennas))
    return baselines_from_source_list(sources)
    # order1 = []
    # order2 = []
    # for ant_ctr in range(n_antennas):
    #     # print('ant_ctr(%d)' % ant_ctr
    #     for ctr2 in range(int(n_antennas / 2), -1, -1):
    #         temp = (ant_ctr - ctr2) % n_antennas
    #         # print('\tctr2(%d) temp(%d)' % (ctr2, temp)
    #         if ant_ctr >= temp:
    #             order1.append((temp, ant_ctr))
    #         else:
    #             order2.append((ant_ctr, temp))
    # order2 = [order_ for order_ in order2 if order_ not in order1]
    # baseline_order = order1 + order2
    # source_names = []
    # for source in sources:
    #     source_names.append(source)
    # rv = []
    # for baseline in baseline_order:
    #     rv.append((source_names[baseline[0] * 2],
    #                source_names[baseline[1] * 2]))
    #     rv.append((source_names[baseline[0] * 2 + 1],
    #                source_names[baseline[1] * 2 + 1]))
    #     rv.append((source_names[baseline[0] * 2],
    #                source_names[baseline[1] * 2 + 1]))
    #     rv.append((source_names[baseline[0] * 2 + 1],
    #                source_names[baseline[1] * 2]))
    # return rv


def process_new_eq(eq):
    """
    Handle a new EQ - it could be an int, a string, a polynomial string
    :param eq: the new eq
    :return: a list of complex numbers:
                if the length matches the fft, it's an array, one coeff per channel
                else if it's one, it's a single value for all channels
                else it's a polynomial applied over the channels
    """
    # eq = '300' - this is an eq poly of length one, in string form
    # eq = 300 - this is an eq poly of length one, in int form
    # eq = '10,30,40' - this is an eq poly
    # string or single int?
    try:
        eq = eq.strip()
        if len(eq) == 0:
            raise ValueError('Empty string makes littles sense for EQ values.')
        # could be a polynomial or an array in a string
        try:
            eq.index(',')
            eqlist = eq.split(',')
        except ValueError:
            eqlist = eq.split(' ')
    except AttributeError:
        try:
            len(eq)
            eqlist = eq
        except TypeError:
            eqlist = [eq]
    for ctr, eq in enumerate(eqlist):
        eqlist[ctr] = complex(eq)
    return eqlist


class UnpackDengPacketCapture(object):
    def __init__(self, pcap_file_or_name):
        try:
            import dpkt
        except ImportError:
            raise ImportError("Install optional 'dpkt' and 'bitstring' python "
                              "modules to decode packet streams")
        if isinstance(pcap_file_or_name, basestring):
            self.pcap_file = open(pcap_file_or_name)
        else:
            self.pcap_file = pcap_file_or_name

        self.pcap_reader = dpkt.pcap.Reader(self.pcap_file)

    def decode(self):
        """Decode packets close pcap file

        Return Values
        =============

        (timestamps, voltages) where:
        timestamps : list
            digitiser timestamps at the start of each packet of 4096 samples
        voltages : numpy Float array
            Voltage time-series normalised to between -1 and 1.

        """
        try:
            import bitstring
        except ImportError:
            raise ImportError("Install optional 'dpkt' and 'bitstring' python "
                              "modules to decode packet streams")

        data_blocks = {}                # Data blocks keyed by timestamp
        LOGGER.info('Decoding SPEAD packets')
        for i, (ts, pkt) in enumerate(self.pcap_reader):
            LOGGER.debug('Packet {}'.format(i))
            # WARNING (NM, 2015-05-29): Stuff stolen from simonr, now
            # idea how he determined the various hard-coded constants
            # below, though I assume it involved studying the structure
            # of a SPEAD packet.
            enc = pkt.encode('hex_codec')
            header_line = enc[84:228]
            bs = bitstring.BitString(hex='0x' + header_line[22:32])
            timestamp = bs.unpack('uint:40')[0]
            data_line = enc[228:]
            if len(data_line) != 10240:
                LOGGER.warn("Error reading packet for ts {}. Expected 10240 "
                            "but got {}.".format(timestamp, len(data_line)))
                continue

            datalist = []
            for x in range(0, len(data_line), 16):
                datalist.append(int(data_line[x:x+16], 16))
            words80 = AdcData.sixty_four_to_eighty(datalist)
            words10 = AdcData.eighty_to_ten(words80)

            assert timestamp not in data_blocks
            data_blocks[timestamp] = words10

        LOGGER.info("Ordering packets")
        sorted_time_keys = np.array(sorted(data_blocks.keys()))
        data = np.hstack(data_blocks[ts] for ts in sorted_time_keys)

        LOGGER.info("Checking packets")
        samples_per_pkt = 4096
        time_jumps = sorted_time_keys[1:] - sorted_time_keys[:-1]

        if not np.all(time_jumps == samples_per_pkt):
            LOGGER.info("It looks like gaps exist in captured data -- were "
                        "packets dropped?")

        self.pcap_file.close()
        return sorted_time_keys, data


def disable_test_gbes(corr_instance):
    """
    Disable the 10Gbe fabric by default on test GBE devices.
    :param corr_instance: the correlator object in use
    :return:
    """
    for hosts in (corr_instance.xhosts + corr_instance.fhosts):
        for gbe in hosts.gbes:
            if gbe.name.startswith('test_'):
                corr_instance.logger.info(
                    '%s: disabled fabric on '
                    '%s' % (hosts.host, gbe.name))
                gbe.fabric_disable()


def remove_test_objects(corr_instance):
    """
    Any hardware device whose name starts with test_ must be removed from the
    attribute list.
    :param corr_instance:
    :return:
    """
    from casperfpga import casperfpga as ccasperfpga
    _changes_made = False
    for hosts in [corr_instance.fhosts, corr_instance.xhosts]:
        for host in hosts:
            for container_ in ccasperfpga.CASPER_MEMORY_DEVICES.values():
                    attr_container = getattr(host, container_['container'])
                    for attr_name in attr_container.names():
                        if attr_name.find('test_') == 0:
                            attr_container.remove_attribute(attr_name)
                            _changes_made = True
    if _changes_made:
        corr_instance.logger.info(
            'One or more test_ devices were removed. Just so you know.')


def thread_funcs(timeout, *funcs):
    """
    Run any given functions in seperate threads, return
    the results in a dictionary keyed on function id
    :param timeout:
    :param funcs:
    :return:
    """
    def jobfunc(_func, resultq):
        rv = _func[0](*_func[1], **_func[2])
        resultq.put_nowait((_func[0], rv))
    num_funcs = len(funcs)
    if num_funcs == 0:
        return
    thread_list = []
    result_queue = Queue.Queue(maxsize=num_funcs)
    for func in funcs:
        thread = threading.Thread(target=jobfunc, args=(func, result_queue))
        thread.daemon = True
        thread.start()
        thread_list.append(thread)
    for thread_ in thread_list:
        thread_.join(timeout)
        if thread_.isAlive():
            break
    returnval = {}
    while True:
        try:
            result = result_queue.get_nowait()
            returnval[result[0]] = result[1]
        except Queue.Empty:
            break
    if len(returnval) != num_funcs:
        errmsg = 'Given %d FPGAs, only got %d results, must have timed ' \
                 'out.' % (num_funcs, len(returnval))
        LOGGER.error(errmsg)
        raise RuntimeError(errmsg)
    return returnval


def hosts_from_dhcp_leases(host_pref='roach',
                           leases_file='/var/lib/misc/dnsmasq.leases'):
    """
    Get a list of hosts from a leases file.
    :param host_pref: the prefix of the hosts in which we're interested
    :param leases_file: the file to read
    :return:
    """
    hosts = []
    if not isinstance(host_pref, list):
        host_pref = [host_pref]
    with open(leases_file) as masqfile:
        masqlines = masqfile.readlines()
    for line in masqlines:
        (leasetime, mac, ip, host, mac2) = line.replace('\n', '').split(' ')
        for host_prefix in host_pref:
            if host.startswith(host_prefix):
                hosts.append(host if host != '*' else ip)
                break
    return hosts, leases_file


def parse_output_products(dictionary):
    """
    Parse a config dictionary section for output products and addresses.
    :param dictionary: a dict containing the products and their details
    :return: lists of products and StreamAddresses
    """

    # base_output_destinations

    try:
        prods = dictionary['output_products'].split(',')
    except KeyError:
        raise RuntimeError('The given dictionary does not seem to have '
                           'output_products defined.\n%s' % str(dictionary))
    try:
        addresses = dictionary['output_destinations'].split(',')
    except KeyError:
        try:
            addresses = dictionary['output_destinations_base'].split(',')
        except KeyError:
            raise RuntimeError('The given dictionary does not seem to have '
                               'output_destinations or output_destinations_base'
                               ' defined.\n%s' % str(dictionary))
    if len(prods) != len(addresses):
        raise RuntimeError('Need the same number of output products and '
                           'addresses: %s, %s' % (prods, addresses))
    # process the address strings
    for ctr, addr in enumerate(addresses):
        addresses[ctr] = StreamAddress.from_address_string(addr)
    return prods, addresses


class KatcpStreamHandler(logging.StreamHandler):

    def format(self, record):
        """
        Convert the record message contents to a katcp #log format
        :param record: a logging.LogRecord
        :return:
        """
        level = 'WARN' if record.levelname == 'WARNING' else record.levelname
        level = level.lower()
        msg = record.msg.replace(' ', '\_')
        msg = msg.replace('\t', '\_' * 4)
        return '#log ' + level + ' ' + '%.6f' % time.time() + ' ' + \
               record.filename + ' ' + msg


class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to
    a logger instance.
    From: http://www.electricmonk.nl/log/2011/08/14/redirect-stdout-and-stderr-to-a-logger-in-python/
    """

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())


# end
