#!/usr/bin/env python

import logging
import time
import argparse
import os

from casperfpga import skarab_fpga

def_txhost = '' if 'TUT2_TXHOST' not in os.environ else \
    os.environ['TUT2_TXHOST']
def_rxhost = '' if 'TUT2_RXHOST' not in os.environ else \
    os.environ['TUT2_RXHOST']
def_txfpg = '' if 'TUT2_TXFPG' not in os.environ else os.environ['TUT2_TXFPG']
def_rxfpg = '' if 'TUT2_RXFPG' not in os.environ else os.environ['TUT2_RXFPG']

parser = argparse.ArgumentParser(
    description='Script and classes for SKARAB Tutorial 2',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--txhost', dest='txhost', type=str, action='store',
                    default=def_txhost,
                    help='Hostname or IP for the TX SKARAB.')
parser.add_argument('--rxhost', dest='rxhost', type=str, action='store',
                    default=def_rxhost,
                    help='Hostname or IP for the RX SKARAB.')
parser.add_argument('--txfpg', dest='txfpg', type=str, action='store',
                    default=def_txfpg,
                    help='Programming file for the TX SKARAB.')
parser.add_argument('--rxfpg', dest='rxfpg', type=str, action='store',
                    default=def_rxfpg,
                    help='Programming file for the RX SKARAB.')
parser.add_argument('--pktsize', dest='pktsize', type=int, action='store',
                    default=160, help='Packet length to send (in words).')
parser.add_argument('-p', '--program', dest='program', action='store_true',
                    default=False, help='Program the SKARABs')
parser.add_argument('--loglevel', dest='log_level', action='store',
                    default='INFO', help='log level to use, default None, '
                                         'options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

# tx_host = '10.99.45.171'
# tx_fpg = '/home/paulp/bofs/tut2_tx_2017-4-14_1120.fpg'
# rx_host = '10.99.37.5'
# rx_fpg = '/home/paulp/bofs/tut2_rx_2017-4-14_1024.fpg'


def print_txsnap(numlines=-1):
    """
    
    :param numlines: 
    :return: 
    """
    ftx.registers.control.write(snap_arm=0)
    ftx.snapshots.txsnap0_ss.arm()
    ftx.snapshots.txsnap1_ss.arm()
    ftx.registers.control.write(snap_arm=1)
    d = ftx.snapshots.txsnap0_ss.read(arm=False)['data']
    d1 = ftx.snapshots.txsnap1_ss.read(arm=False)['data']
    d.update(d1)
    if numlines < 1:
        numlines = len(d['eof'])
    for ctr in range(numlines):
        print('%04i' % ctr, 'pkt_ctr(%015i)' % d['pkt_ctr'][ctr], \
            'ramp(%05i)' % d['ramp'][ctr], \
            'walking(%s)' % format(d['walking'][ctr], '#066b'),
        if d['eof'][ctr] == 1:
            print('EOF'
        else:
            print(''


def print_rxsnap(numlines=-1):
    """
    
    :param numlines: 
    :return: 
    """
    frx.registers.control.write(snap_arm=0)
    frx.snapshots.d0_ss.arm()
    frx.snapshots.d1_ss.arm()
    frx.snapshots.d2_ss.arm()
    frx.registers.control.write(snap_arm=1)
    time.sleep(1)
    d0 = frx.snapshots.d0_ss.read(arm=False)['data']
    d1 = frx.snapshots.d1_ss.read(arm=False)['data']
    d2 = frx.snapshots.d2_ss.read(arm=False)['data']
    d0.update(d1)
    d0.update(d2)
    ip = d0['src_ip'][0]
    port = d0['src_port'][0]
    if numlines < 1:
        numlines = len(d0['src_ip'])
    for ctr in range(numlines):
        print('%04i' % ctr,
        print('pkt_ctr(%015i)' % d0['ctr0'][ctr],
        print('ramp(%05i)' % d0['ramp0'][ctr],
        print('walk(%s)' % format(d0['walking0'][ctr], '#066b'),
        if d0['ctr0'][ctr] != d0['ctr1'][ctr]:
            print('PKTCTR_ERROR',
        if d0['ramp0'][ctr] != d0['ramp1'][ctr]:
            print('RAMP_ERROR',
        if d0['walking0'][ctr] != d0['walking1'][ctr]:
            print('WALK_ERROR',
        if d0['overrun'][ctr] != 0:
            print('OVERRUN',
        if d0['badframe'][ctr] != 0:
            print('BADFRAME',
        if d0['src_ip'][ctr] != ip:
            print('IP_ERROR',
        if d0['src_port'][ctr] != port:
            print('PORT_ERROR',
        if ctr == 0:
            last_pkt = d0['ctr0'][0]
            last_ramp = -1
            last_walk = d0['walking0'][1] / 2
        if d0['eof'][ctr] == 1:
            print('EOF'
        else:
            print(''

if __name__ == '__main__':

    logging.info('Connecting to SKARABs.')
    ftx = skarab_fpga.SkarabFpga(args.txhost)
    frx = skarab_fpga.SkarabFpga(args.rxhost)

    if args.program:
        logging.info('Programming SKARABs.')
        res = ftx.upload_to_ram_and_program(args.txfpg)
        if not res:
            logging.error('Could not program TX SKARAB: %s' % args.txhost)
        logging.info('\tDone programming TXer.')
        res = frx.upload_to_ram_and_program(args.rxfpg)
        if not res:
            logging.error('Could not program RX SKARAB: %s' % args.rxhost)
        logging.info('\tDone programming RXer.')
    else:
        ftx.get_system_information(args.txfpg)
        frx.get_system_information(args.rxfpg)
        logging.info('Stopping TX.')
        ftx.registers.control.write(tx_en=0, pkt_rst='pulse')
        frx.registers.control.write(snap_arm=0)

    # set up TX
    logging.info('Setting TX destination.')
    ftx.registers.tx_ip = int(frx.gbes[0].get_ip())
    ftx.registers.tx_port = 7779
    ftx.registers.control.write(pkt_len=args.pktsize)

    # set up RX
    logging.info('Setting RX port.')
    frx.gbes[0].set_port(7779)
    frx.registers.control.write(gbe_rst='pulse')

    # enable tx
    logging.info('Starting TX.')
    ftx.registers.control.write(tx_en=1, pkt_rst='pulse')

    time.sleep(1)

    logging.info('Some RX stats:')
    logging.info('\tvalid: %s' % frx.registers.rx_valid.read()['data']['reg'])
    logging.info('\teof: %s' % frx.registers.rx_eof.read()['data']['reg'])
    logging.info('\tbadframe: %s' %
                 frx.registers.rx_badframe.read()['data']['reg'])
    logging.info('\toverrun: %s'
                 % frx.registers.rx_overrun.read()['data']['reg'])

    print_txsnap(int(args.pktsize * 2.5))
    print(''
    print_rxsnap(int(args.pktsize* 2.5))

    import IPython
    IPython.embed()

# end
