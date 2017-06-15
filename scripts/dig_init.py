from __future__ import print_function
import time
import sys
import logging
import argparse


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

sys.path.insert(0, '/home/paulp/code/corr2.ska.github/src')

from corr2.digitiser import Digitiser
from casperfpga import network

parser = argparse.ArgumentParser(description='Debug the deng-feng connection.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-p', '--program', dest='program',
                    action='store_true', default=False,
                    help='should we program the fpgas')
parser.add_argument('-s', '--setup_gbe', dest='setupgbe', action='store_true',
                    default=False,
                    help='set up the 10gbe system')
parser.add_argument('-r', '--restart', dest='restart', action='store_true',
                    default=False,
                    help='restart all the roaches')
parser.add_argument('-d', '--deprogram', dest='deprogram', action='store_true',
                    default=False,
                    help='deprogram all the roaches')
parser.add_argument('-u', '--unicast', dest='unicast', action='store_true',
                    default=False,
                    help='transmit unicast to the first F-engine, not multicast to all of them')
args = parser.parse_args()

bitstream = '/srv/bofs/deng/r2_deng_tvg_2014_Jul_21_0838.fpg'
dhost = 'roach020959'
ip_start = '10.0.0.70'
mac_start = '02:02:00:00:00:01'

fdig = Digitiser(dhost)
all_fpgas = [fdig]

if args.deprogram:
    try:
        fdig.deprogram()
        fdig.disconnect()
    except:
        pass
    sys.exit()

if args.restart:
    fdig.katcprequest(name='restart', require_ok=False)
    fdig.disconnect()
    sys.exit()

program = args.program
setup_gbe = args.setupgbe

if program:
    setup_gbe = True
    fdig.deprogram()
    stime = time.time()
    print('Programming: ', end='')
    sys.stdout.flush()
    fdig.upload_to_ram_and_program(bitstream)
    print(time.time() - stime)

fdig.test_connection()
fdig.get_system_information()

if setup_gbe:
    # stop sending data
    fdig.registers.control.write(gbe_txen=False)

    # start the local timer on the test d-engine - mrst, then a fake sync
    fdig.registers.control.write(mrst='pulse')
    fdig.registers.control.write(msync='pulse')

    # the all_fpgas have gbe cores, so set them up
    ip_bits = ip_start.split('.')
    ipbase = int(ip_bits[3])
    mac_bits = mac_start.split(':')
    macbase = int(mac_bits[5])
    num_gbes = len(fdig.gbes)
    if num_gbes < 1:
        raise RuntimeError('D-engine with no 10gbe cores %s' % fdig.host)
    for ctr in range(num_gbes):
        mac = '%s:%s:%s:%s:%s:%d' % (mac_bits[0], mac_bits[1], mac_bits[2],
                                     mac_bits[3], mac_bits[4], macbase + ctr)
        ip = '%s.%s.%s.%d' % (ip_bits[0], ip_bits[1], ip_bits[2], ipbase + ctr)
        fdig.gbes['gbe%d' % ctr].setup(mac=mac, ipaddress=ip, port=7777)

    for gbe in fdig.gbes:
        gbe.tap_start(True)

    # set the destination IP and port for the tx
    if not args.unicast:
        fdig.write_int('gbe_iptx0', network.str2ip('239.2.0.64'))
        fdig.write_int('gbe_iptx1', network.str2ip('239.2.0.65'))
        fdig.write_int('gbe_iptx2', network.str2ip('239.2.0.66'))
        fdig.write_int('gbe_iptx3', network.str2ip('239.2.0.67'))
    else:
        fdig.write_int('gbe_iptx0', network.str2ip('10.0.0.90'))
        fdig.write_int('gbe_iptx1', network.str2ip('10.0.0.91'))
        fdig.write_int('gbe_iptx2', network.str2ip('10.0.0.92'))
        fdig.write_int('gbe_iptx3', network.str2ip('10.0.0.93'))
    fdig.write_int('gbe_porttx', 7777)

    fdig.registers.control.write(gbe_rst=False)

    # enable the tvg on the digitiser and set up the pol id bits
    fdig.registers.control.write(tvg_select0=True)
    fdig.registers.control.write(tvg_select1=True)
    fdig.registers.id2.write(pol1_id=1)

    # start tx
    print('Starting TX...', end='')
    sys.stdout.flush()
    fdig.registers.control.write(gbe_txen=True)
    print('done.')

fdig.disconnect()
