__author__ = 'paulp'

bitfile = '/home/paulp/r2_deng_tvg_2015_Jan_28_1615.fpg'

import argparse
import sys
import signal

from casperfpga import katcp_fpga, tengbe


class DengTvg(katcp_fpga.KatcpFpga):
    def setup_tengbes(self, ip_and_port, base_mac):
        ip, port = ip_and_port.split(':')
        port = int(port)
        ip_octets = [int(bit) for bit in ip.split('.')]
        assert len(ip_octets) == 4, 'That\'s an odd IP address...'
        ip_base = ip_octets[3]
        ip_prefix = '%d.%d.%d.' % (ip_octets[0], ip_octets[1], ip_octets[2])
        macprefix = base_mac[0:base_mac.rfind(':')+1]
        assert macprefix.count(':') == 5, 'That\'s an odd MAC address...'
        macbase = int(base_mac[base_mac.rfind(':')+1:])
        for gbe in self.tengbes:
            this_mac = '%s%02x' % (macprefix, macbase)
            this_ip = '%s%d' % (ip_prefix, ip_base)
            gbe.setup(mac=this_mac, ipaddress=this_ip, port=port)
            LOGGER.info('gbe(%s) MAC(%s) IP(%s) port(%i)' %
                        (gbe.name, this_mac, this_ip, port))
            macbase += 1
            ip_base += 1

    def set_destination(self, ip_and_port):
        ip, port = ip_and_port.split(':')
        port = int(port)
        ip_octets = [int(bit) for bit in ip.split('.')]
        assert len(ip_octets) == 4, 'That\'s an odd IP address...'
        ip_base = ip_octets[3]
        ip_prefix = '%d.%d.%d.' % (ip_octets[0], ip_octets[1], ip_octets[2])
        for gbectr, gbe in enumerate(self.tengbes):
            this_ip = tengbe.str2ip('%s%d' % (ip_prefix, ip_base))
            self.registers['gbe_iptx%i' % gbectr].write(reg=this_ip)
            LOGGER.info('gbe(%s) sending to IP(%s) port(%i)' %
                        (gbe.name, tengbe.ip2str(this_ip), port))
            ip_base += 1
        self.registers.gbe_porttx.write(reg=port)

    def start_tap(self):
        for gbe in self.tengbes:
            gbe.tap_start(True)

parser = argparse.ArgumentParser(description='Set up a TVG digitiser on a ROACH2.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='host', type=str, action='store', default='', help='the host to use')
parser.add_argument('--ip', dest='ip', action='store', default='10.100.0.200:8888',
                    help='digitiser 10GBE core IP address start')
parser.add_argument('--mac', dest='mac', action='store', default='02:02:00:00:03:01',
                    help='digitiser 10GBE core MAC start')
parser.add_argument('--dest_ip', dest='destip', action='store', default='239.2.0.10:8888',
                    help='where should the digitiser data go?')
parser.add_argument('--no_program', dest='no_program', action='store_true', default=False,
                    help='do not program the FPGA')
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
    LOGGER = logging.getLogger(__name__)

def exit_gracefully(signal, frame):
    fpga.disconnect()
    sys.exit(0)
signal.signal(signal.SIGINT, exit_gracefully)

# make the fake dig
fpga = DengTvg(args.host)
if not args.no_program:
    fpga.upload_to_ram_and_program(bitfile)
else:
    fpga.get_system_information()
fpga.setup_tengbes(args.ip, args.mac)
fpga.set_destination(args.destip)

LOGGER.info('Pulsing sync line')
fpga.registers.control.write(msync='pulse')

LOGGER.info('Enabling output')
fpga.registers.control_output.write(load_en_time='pulse')

import time
stime = (fpga.registers.local_time_msw.read()['data']['reg'] << 32) | \
        fpga.registers.local_time_lsw.read()['data']['reg']
time.sleep(1)
etime = (fpga.registers.local_time_msw.read()['data']['reg'] << 32) | \
        fpga.registers.local_time_lsw.read()['data']['reg']
LOGGER.info('Deng clock @ %.2fMhz, give or take a few Mhz' % ((etime - stime) / 1000000.0))

LOGGER.info('Starting tap')
fpga.start_tap()

LOGGER.info('Enabling 10gbe output')
fpga.registers.control.write(clr_status='pulse', gbe_txen=1)
