__author__ = 'paulp'

from ConfigParser import SafeConfigParser
import logging
import os

LOGGER = logging.getLogger(__name__)


def parse_ini_file(ini_file='', required_sections=None):
    """
    Parse an ini file into a dictionary. No checking done at all.
    :return: a dictionary containing the configuration
    """
    if (ini_file == '') and ('CORR2INI' in os.environ.keys()):
        ini_file = os.environ['CORR2INI']
        LOGGER.info('Defaulting to config env var $CORR2INI=%s', ini_file)
    if required_sections is None:
        required_sections = []
    parser = SafeConfigParser()
    files = parser.read(ini_file)
    if len(files) == 0:
        raise IOError('Could not read the config file, %s' % ini_file)
    for check_section in required_sections:
        if not parser.has_section(check_section):
            raise ValueError('The config file does not seem to have the required %s section?' % check_section)
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
