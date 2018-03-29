#!/usr/bin/python
# -*- coding: utf-8 -*-

import casperfpga
import argparse

parser = argparse.ArgumentParser(
    description='Set up and run a fake spectrometer - data is just a ramp of'
                '64-bit integers.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('--host', dest='host', type=str, action='store',
                    required=True,
                    default='roach02064a', help='the host to use')

parser.add_argument('-p', '--program', dest='program', action='store_true',
                    default=False, help='program the FPGA')
parser.add_argument('--fpg', dest='fpg', type=str, action='store',
                    default='/tmp/fake_spec_2016_Apr_12_1332.fpg',
                    help='path to fpga binary')

parser.add_argument('--ip', dest='host_ip', type=str, action='store',
                    default='10.100.0.110', help='host IP')
parser.add_argument('--mac', dest='host_mac', type=str, action='store',
                    default='02:02:00:00:02:10', help='host MAC')
parser.add_argument('--port', dest='host_port', type=int, action='store',
                    default=9999, help='host port')

parser.add_argument('--tx_ip', dest='tx_ip', type=str, action='store',
                    default='10.100.201.1', help='destination IP')
parser.add_argument('--tx_port', dest='tx_port', type=int, action='store',
                    default=9876, help='destination port')

parser.add_argument('--pkt_rate', dest='pkt_rate', type=int, action='store',
                    default=2**22, help='send one packet (not heap) every X '
                                        'fpga clock cycles')

parser.add_argument('--txen', dest='tx_enable', action='store_true',
                    default=False, help='enable transmission')
parser.add_argument('--txstop', dest='tx_disable', action='store_true',
                    default=False, help='stop transmission')
parser.add_argument('--reset_pkt', dest='reset_tvg', action='store_true',
                    default=False, help='reset packet transmission')

parser.add_argument('--loglevel', dest='log_level', action='store',
                    default='INFO',
                    help='log level to use, default None, options INFO, '
                         'DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

# make the fpga
f = casperfpga.KatcpFpga(args.host)
if args.program:
    logging.info('Programming FPGA')
    f.upload_to_ram_and_program(args.fpg)
else:
    f.get_system_information()

# set the packet-rate
if args.program:
    logging.info('Setting packet rate to {}'.format(args.pkt_rate))
    f.registers.pkt_rate.write(rate=args.pkt_rate)

# set the tx ip and core
if args.program:
    logging.info('Setting up destination registers, {}:{}'.format(
        args.tx_ip, args.tx_port
    ))
    _ip_int = casperfpga.tengbe.IpAddress.str2ip(args.tx_ip)
    f.registers.ip.write(ip=_ip_int)
    f.registers.port.write(port=args.tx_port)

# set up the tengbe core
if args.program:
    f.registers.ctrl.write(data_en=False, gbe_rst=True)
    f.tengbes.gbe0.setup(mac=args.host_mac, ipaddress=args.host_ip,
                         port=args.host_port)
    f.tengbes.gbe0.dhcp_start()
    f.registers.ctrl.write(gbe_rst=False)
    logging.info('Set up tengbe core: %s' % f.tengbes.gbe0)

# reset the data gen
if args.program or args.reset_tvg:
    logging.info('Resetting data gen')
    f.registers.ctrl.write(rst='pulse')

# enable the data to the core
if args.tx_enable:
    logging.info('Enabling data transmission')
    f.registers.ctrl.write(data_en=True)
if args.tx_disable:
    logging.info('Stopping data transmission')
    f.registers.ctrl.write(data_en=False)

# done
