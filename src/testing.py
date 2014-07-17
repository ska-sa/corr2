import fengine_fpga
import xengine_fpga
import host_fpga
import utils
from fxcorrelator import FxCorrelator
import sys
import logging

logging.basicConfig(level=logging.INFO)

c = FxCorrelator('rts correlator', config_source='fxcorr.ini')

c.initialise()

for h in c.fhosts:
    for e in h.engines.items():
        print e[1].n_chans

sys.exit()

iniconfig = utils.parse_ini_file('fxcorr.ini')

f = host_fpga.FpgaHost('127.0.0.1', 2000)
f.boffile = '/home/paulp/projects/code/shiny-octo-wookie/mkat/feng/feng_rx_test/bit_files/feng_rx_test_2014_Jun_05_1818.fpg'
f.initialise(program=False, program_port=3333)
e = xengine_fpga.XengineCasperFpga(f, 0, iniconfig)
