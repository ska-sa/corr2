import fengine_fpga
import host_fpga
import utils

import logging
logging.basicConfig(level=logging.INFO)

iniconfig = utils.parse_ini_file('fxcorr.ini')

f = host_fpga.FpgaHost('127.0.0.1', 2000)
f.boffile = '/home/paulp/projects/code/shiny-octo-wookie/mkat/feng/feng_rx_test/bit_files/feng_rx_test_2014_Jun_05_1818.fpg'
f.initialise(program=False)
e = fengine_fpga.FengineCasperFpga(f, 0, 0, iniconfig)
