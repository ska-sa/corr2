#!/usr/bin/env python
"""
Start or stop transmission from one or more ROACHs.

@author: paulp
"""
import sys
import logging
import time
import argparse


#allhosts = roach020958,roach02091b,roach020914,roach020922,roach020921,roach020927,roach020919,roach020925,roach02091a,roach02091e,roach020923,roach020924

def load_hosts_from_config(configfile):
    return []

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR)

from casperfpga import KatcpClientFpga

parser = argparse.ArgumentParser(description='Start or stop 10gbe transmission on a CASPER device',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='hosts', type=str, action='store',
                    help='comma-delimited list of devices')
parser.add_argument('--start', dest='start', action='store_true', default=False,
                    help='start TX')
parser.add_argument('--stop', dest='stop', action='store_true', default=False,
                    help='stop TX')
parser.add_argument('--config', dest='config', action='store', default='',
                    help='read hosts from a correlator config file instead')
args = parser.parse_args()

if args.config != '':
    hosts = load_hosts_from_config(args.config)
else:
    hosts = args.hosts.lstrip().rstrip().replace(' ', '').split(',')

# create the devices and start/stop tx
fpgas = []
for host_ in hosts:
    fpga = KatcpClientFpga(host_)
    time.sleep(0.3)
    if not fpga.is_connected():
        fpga.connect()
    try:
        fpga.get_system_information()
    except:
        logging.error('%s not running', fpga.host)
    else:
        # stop
        if args.stop:
            print 'Stopping tx on host %s' % fpga.host
            try:
                fpga.registers.control.write(gbe_out_en=False)
            except:
                print 'Not ultimate registers'
            try:
                fpga.registers.control.write(gbe_txen=False)
            except:
                print 'No sim fengine'
            try:
                fpga.registers.control.write(comms_en=False)
            except:
                print 'No fengine'
            try:
                fpga.registers.ctrl.write(comms_en=False)
            except:
                print 'Not old registers'
                logger.error('Could not find the correct registers on host %s', fpga.host)

        # start
        if args.start:
            print 'Starting tx on host %s' % fpga.host
            try:
                fpga.registers.control.write(gbe_out_en=True)
            except:
                print 'Not ultimate registers'
            try:
                fpga.registers.control.write(gbe_txen=True)
            except:
                print 'No sim fengine'
            try:
                fpga.registers.control.write(comms_en=True)
            except:
                print 'No fengine'
            try:
                fpga.registers.ctrl.write(comms_en=True)
            except:
                print 'Not old registers'
                logger.error('Could not find the correct registers on host %s', fpga.host)

# end
