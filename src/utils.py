__author__ = 'paulp'

import time
from ConfigParser import SafeConfigParser


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


def get_information_threaded(fpgas):
    """
    Get system information from running Fpga hosts, threaded to go quicker.
    :param fpgas: A list of FPGA hosts.
    :return: <nothing>
    """
    return True


def program_fpgas(progfile, fpgas, timeout=10):
    """Program more than one FPGA at the same time.
    :param progfile: string, the filename of the file to use to program the FPGAs
    :param fpgas: a list of objects for the FPGAs to be programmed
    :return: True if all went well, False if not
    """
    chilltime = 0.1
    waiting = []
    for fpga in fpgas:
        try:
            len(fpga)
        except TypeError:
            fpga.upload_to_ram_and_program(progfile, wait_complete=False)
            waiting.append(fpga)
        else:
            fpga[0].upload_to_ram_and_program(fpga[1], wait_complete=False)
            waiting.append(fpga[0])
    starttime = time.time()
    while (len(waiting) > 0) and (time.time() - starttime < timeout):
        for fpga in waiting:
            if fpga.is_running():
                waiting.pop(waiting.index(fpga))
        time.sleep(chilltime)
    if len(waiting) > 0:
        return False
    return True

# end