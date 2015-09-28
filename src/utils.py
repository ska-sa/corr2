import logging
import os
import numpy as np
from ConfigParser import SafeConfigParser
import Queue
import threading

from casperfpga.memory import bin2fp

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
        :param list_w64: a list of 64-bit words, typically straight from the 10gbe
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


def parse_ini_file(ini_file='', required_sections=None):
    """
    Parse an ini file into a dictionary. No checking done at all.
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
                'The config file does not seem to have the required %s section?' % (
                    check_section,))
    config = {}
    for section in parser.sections():
        config[section] = {}
        for items in parser.items(section):
            config[section][items[0]] = items[1]
    return config


def hosts_from_config_dict(config_dict, section=None):
    assert hasattr(config_dict, 'keys')
    host_list = []
    for sectionkey in config_dict.keys():
        if (section is None) or (section == sectionkey):
            if 'hosts' in config_dict[sectionkey].keys():
                hosts = config_dict[sectionkey]['hosts'].split(',')
                for ctr, host_ in enumerate(hosts):
                    hosts[ctr] = host_.strip()
                host_list.extend(hosts)
    return host_list


def hosts_from_config_file(config_file, section=None):
    """
    Make lists of hosts from a given correlator config file.
    :return: a dictionary of hosts, by type
    """
    config = parse_ini_file(config_file)
    return hosts_from_config_dict(config, section=section)


def parse_hosts(str_file_dict, section=None):
    """
    Make a list of hosts from the argument given to a script.
    :param str_file_dict: a string, file or dictionary where hosts may be found
    :param section: the config section from which to take hosts, if applicable
    :return: a list of hosts, if no section was given, the list is all sections
    """
    # issit a config dict?
    if hasattr(str_file_dict, 'keys'):
        host_list = hosts_from_config_dict(str_file_dict, section=section)
    else:
        try:
            # it's a file
            host_list = hosts_from_config_file(str_file_dict, section=section)
        except IOError:
            # it's a string
            hosts = str_file_dict.strip().split(',')
            for ctr, host_ in enumerate(hosts):
                hosts[ctr] = host_.strip()
            host_list = hosts
    num_hosts = len(host_list)
    LOGGER.debug('Ended up with %i hosts.' % num_hosts)
    return host_list


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
            # WARNING (NM, 2015-05-29): Stuff stolen from simonr, now idea how he
            # determined the various hard-coded constants below, though I assume it
            # involved studying the structure of a SPEAD packet.
            enc = pkt.encode('hex_codec')
            header_line = enc[84:228]
            bs = bitstring.BitString(hex='0x' + header_line[22:32])
            timestamp = bs.unpack('uint:40')[0]
            data_line = enc[228:]
            if len(data_line) != 10240:
                LOGGER.warn("Error reading packet for ts {}. Expected 10240 but "
                            "got {}.".format(timestamp, len(data_line)))
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
        LOGGER.info('One or more test_ devices were removed. Just so you know.')


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
        print returnval
        raise RuntimeError('Given %d FPGAs, only got %d results, must '
                           'have timed out.' % (num_funcs, len(returnval)))
    return returnval
