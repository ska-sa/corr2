__author__ = 'paulp'

import time
import casperfpga
from ConfigParser import SafeConfigParser


def parse_ini_file(ini_file, required_sections=None):
        """
        Parse an ini file into a dictionary. No checking done at all.
        :return:
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


def program_fpgas(progfile, fpgas, timeout=10):
    """Program more than one FPGA at the same time.
    :param progfile: the file to use to program the FPGAs
    :param fpgas: a list of host names for the FPGAs to be programmed
    :return: True if all went well, False if not
    """
    for fpga in fpgas:
        if not isinstance(fpga, casperfpga.KatcpClientFpga):
            raise TypeError('This function only runs on CASPER FGPAs.')
    waiting = []
    for fpga in fpgas:
        fpga = casperfpga.KatcpClientFpga()
        fpga.upload_to_ram_and_program(progfile, wait_complete=False)
        waiting.append(fpga)
    starttime = time.time()
    while (len(waiting) > 0) and (time.time()-starttime < timeout):
        for fpga in waiting:
            if fpga.is_running():
                waiting.pop(waiting.index(fpga))
    if len(waiting) > 0:
        return False
    return True

# end