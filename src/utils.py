__author__ = 'paulp'

from ConfigParser import SafeConfigParser
import logging

LOGGER = logging.getLogger(__name__)


def parse_ini_file(ini_file, required_sections=None):
    """
    Parse an ini file into a dictionary. No checking done at all.
    :return: a dictionary containing the configuration
    """
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


def hosts_from_config_file(config_file, section=None):
    """
    Make lists of hosts from a given correlator config file.
    :return: a dictionary of hosts, by type
    """
    config = parse_ini_file(config_file)
    rv = {}
    for sectionkey in config.keys():
        if (section is None) or (section == sectionkey):
            if 'hosts' in config[sectionkey].keys():
                hosts = config[sectionkey]['hosts'].split(',')
                for ctr, host_ in enumerate(hosts):
                    hosts[ctr] = host_.strip()
                rv[sectionkey] = hosts
    return rv


def parse_hosts(list_or_file, section=None):
    """
    Make a list of hosts from the argument given to a script.
    :param list_or_file:
    :return:
    """
    hosts = list_or_file.strip().replace(' ', '').split(',')
    if len(hosts) == 1:  # check to see it it's a file
        try:
            hostsfromfile = hosts_from_config_file(hosts[0], section=section)
            hosts = []
            for hostlist in hostsfromfile.values():
                hosts.extend(hostlist)
        except IOError:
            # it's not a file so carry on
            pass
    return hosts
