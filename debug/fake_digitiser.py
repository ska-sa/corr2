__author__ = 'paulp'

import argparse
import sys
import time

from casperfpga.katcp_fpga import KatcpFpga
from casperfpga import tengbe

parser = argparse.ArgumentParser(description='Start/stop the fake digitiser.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
# parser.add_argument(dest='config', type=str, action='store',
#                     help='corr2 config file')
parser.add_argument('--program', dest='program', action='store_true', default=False,
                    help='(re)program the fake digitiser')
parser.add_argument('--deprogram', dest='deprogram', action='store_true', default=False,
                    help='deprogram the fake digitiser')
parser.add_argument('--start', dest='start', action='store_true', default=False,
                    help='start the fake digitiser transmission')
parser.add_argument('--stop', dest='stop', action='store_true', default=False,
                    help='stop the fake digitiser transmission')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

#dbof = '/srv/bofs/deng/r2_deng_tvg_2014_Jul_21_0838.fpg'
#dbof = '/srv/bofs/deng/r2_deng_tvg_2014_Aug_27_1619.fpg'
DIG_BOF = '/home/paulp/r2_deng_tvg_2014_Sep_11_1230.fpg'
DIG_HOST = 'roach020922'
DIG_IP_START = '10.100.0.70'
DIG_MAC_START = '02:02:00:00:00:01'

DIG_TX_PORT = 8888
DIG_TX_IP_START = '239.0.0.68'

if args.start and args.stop:
    raise RuntimeError('Start and stop?')

# make the fpga host
fdig = KatcpFpga(DIG_HOST)
print 'Connected to %s.' % fdig.host

if args.program:
    stime = time.time()
    fdig.upload_to_ram_and_program(DIG_BOF)
    print 'Programmed %s in %.2f seconds.' % (fdig.host, time.time() - stime)
    # stop sending data
    fdig.registers.control.write(gbe_txen=False)
    # start the local timer on the test d-engine - mrst, then a fake sync
    fdig.registers.control.write(mrst='pulse')
    fdig.registers.control.write(msync='pulse')
    # the all_fpgas have tengbe cores, so set them up
    ip_bits = DIG_IP_START.split('.')
    ipbase = int(ip_bits[3])
    mac_bits = DIG_MAC_START.split(':')
    macbase = int(mac_bits[5])
    for ctr in range(0, 4):
        mac = '%s:%s:%s:%s:%s:%d' % (mac_bits[0], mac_bits[1], mac_bits[2], mac_bits[3], mac_bits[4], macbase + ctr)
        ip = '%s.%s.%s.%d' % (ip_bits[0], ip_bits[1], ip_bits[2], ipbase + ctr)
        fdig.tengbes['gbe%d' % ctr].setup(mac=mac, ipaddress=ip, port=DIG_TX_PORT)
    for gbe in fdig.tengbes:
        gbe.tap_start(True)
    # set the destination IP and port for the tx
    txaddr = DIG_TX_IP_START
    txaddr_bits = txaddr.split('.')
    txaddr_base = int(txaddr_bits[3])
    txaddr_prefix = '%s.%s.%s.' % (txaddr_bits[0], txaddr_bits[1], txaddr_bits[2])
    for ctr in range(0, 4):
        txip = txaddr_base + ctr
        print '%s sending to: %s%d port %d' % (fdig.host, txaddr_prefix, txip, DIG_TX_PORT)
        fdig.write_int('gbe_iptx%i' % ctr, tengbe.str2ip('%s%d' % (txaddr_prefix, txip)))
    fdig.write_int('gbe_porttx', DIG_TX_PORT)
    fdig.registers.control.write(gbe_rst=False)
    # enable the tvg on the digitiser and set up the pol id bits
    fdig.registers.control.write(tvg_select0=1)
    fdig.registers.control.write(tvg_select1=1)
    fdig.registers.id2.write(pol1_id=1)
else:
    fdig.get_system_information()

if args.deprogram:
    fdig.deprogram()
    print 'Deprogrammed %s.' % fdig.host

if args.stop:
    fdig.registers.control.write(gbe_txen=False)
    print 'Stopped transmission on %s.' % fdig.host

if args.start:
    # start tx
    print 'Starting TX on %s' % fdig.host,
    sys.stdout.flush()
    fdig.registers.control.write(gbe_txen=True)
    print 'done.'
    sys.stdout.flush()

fdig.disconnect()
