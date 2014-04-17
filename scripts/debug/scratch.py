# -*- coding: utf-8 -*-
"""
Created on Mon Mar 31 13:10:05 2014

@author: paulp
"""

import time, sys, logging, argparse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

#sys.path.insert(0, '/home/paulp/code/corr2.ska.github/src')

from corr2.katcp_client_fpga import KatcpClientFpga
from corr2.digitiser import Digitiser
from corr2.fpgadevice import tengbe
import corr2.misc as misc

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
args = parser.parse_args()

dhost = 'roach020958'
fhosts = ['roach02091b', 'roach020914', 'roach020915', 'roach020922']
xhosts = ['roach020921', 'roach020927', 'roach020919', 'roach020925',
          'roach02091a', 'roach02091e', 'roach020923', 'roach020924']

dfpg = '/srv/bofs/deng/r2_deng_tvg_2014_Mar_28_1355.fpg'
ffpg = '/srv/bofs/feng/feng_rx_test_2014_Mar_31_2000.fpg'
xfpg = '/srv/bofs/xeng/r2_2f_4x_4a_4k_r366_2014_Mar_24_1849.fpg'

rts_roaches = ['roach02091b', 'roach020914', 'roach020915', 'roach020922',
               'roach020921', 'roach020927', 'roach020919', 'roach020925',
               'roach02091a', 'roach02091e', 'roach020923', 'roach020924']

rxhosts = ['roach020826', 'roach02070f', 'roach020828', 'roach02082c',
    'roach02064f', 'roach02064a', 'roach020815', 'roach020650',
    'roach02080f', 'roach020813', 'roach020712', 'roach02082d',
    'roach02081c', 'roach020637', 'roach02081e', 'roach02064b',
    'roach02070f', 'roach02082c', 'roach020818', 'roach02070e']

#for host in [dhost]:
#    fpga = KatcpClientFpga(host)
#    fpga.get_system_information()
#    fpga.registers.control.write(cnt_rst='pulse')

for host in fhosts:
    fpga = KatcpClientFpga(host)
    fpga.get_system_information()
    fpga.registers.control.write(cnt_rst='pulse')

for host in xhosts:
    fpga = KatcpClientFpga(host)
    fpga.get_system_information()
    fpga.registers.control.write(cnt_rst='pulse')

sys.exit()

#fpgas = []
#for host in fhosts:
#    fpga = KatcpClientFpga(host)
#    fpga.get_system_information()
#    fpgas.append(fpga)
#
#stime = time.time()
#collected_ips = [[]] * len(fpgas)
#while time.time() - stime < 10:
#    for cnt, fpga in enumerate(fpgas):
#        for register in [fpga.registers.txip0, fpga.registers.txip1, fpga.registers.txip2, fpga.registers.txip3]:
#            ip = register.read()['data']['ip']
#            if ip not in collected_ips[cnt]:
#                collected_ips[cnt].append(ip)
#
#for iplist in collected_ips:
#    iplist.sort()
#    print [tengbe.ip2str(ip) for ip in iplist]
#
#sys.exit()

#for host in rts_roaches:
#    f = KatcpClientFpga(host)
#    time.sleep(0.3)
#    f.upload_to_ram_and_program('/home/paulp/r2_2f_4x_4a_4k_r366_2014_Mar_18_1306.fpg', wait_complete=True)
#    f.test_connection()
#    f.get_system_information()
#    print f.host
#sys.exit()

#fdig = Digitiser(txhost)
#time.sleep(0.3)
#fdig.test_connection()
#fdig.get_system_information()
#numgbes = len(fdig.dev_tengbes)
#print numgbes
#print fdig.get_current_time()
#print fdig.devices['gbe3'].tap_info()
#print fdig.devices['gbe3'].read_counters()
#sys.exit()

#f = KatcpClientFpga('roa       ch020914')
#f.deprogram()
#f.upload_to_ram_and_program('/home/paulp/snap_extraval_2014_Apr_01_1451.fpg', timeout=45)
#f.upload_to_ram_and_program('/srv/bofs/feng/feng_rx_test_2014_Mar_31_1534.fpg', timeout=45)
#f.get_system_information()
#sys.exit()

f = KatcpClientFpga('roach02091b')
f.get_system_information()
#f.registers.snap_control.write(trig_reord_en=True, sel_fifodata=0)
f.registers.control.write(cnt_rst='toggle')

while True:
    print 50*'='
    print f.registers.mcnt_nolock.read()
    print ''
    print f.registers.fifo_of0.read()
    print f.registers.fifo_of1.read()
    print f.registers.fifo_of2.read()
    print f.registers.fifo_of3.read()
    print ''
    print f.registers.fifo_pktof0.read()
    print f.registers.fifo_pktof1.read()
    print f.registers.fifo_pktof2.read()
    print f.registers.fifo_pktof3.read()
    print ''
    print f.registers.spead_err0.read()
    print f.registers.spead_err1.read()
    print f.registers.spead_err2.read()
    print f.registers.spead_err3.read()
    print ''
    print 'CT_SYNC \t', f.registers.ct_synccnt.read()
    print 'CT_valid\t', f.registers.ct_validcnt.read()
    print f.registers.ct_errcnt0.read()
    print f.registers.ct_parity_errcnt0.read()
    print f.registers.ct_errcnt1.read()
    print f.registers.ct_parity_errcnt1.read()
    print ''
    time.sleep(1)


#while True:
#    data = f.snapshots.snapfifo_0_ss.read(man_valid=True, man_trig=True)['data']
#    timestamp_list = []
#    for ctr in range(0, len(data[data.keys()[0]])):
#        thistime = data['timestamp'][ctr]
#        if not thistime in timestamp_list:
#            timestamp_list.append(thistime)
#    for vvvvv in timestamp_list:
#        print vvvvv, ',',
#    print ''
#    time.sleep(1)
#
#sys.exit()

#while True:
#    data = f.snapshots.gbe3_rxs_ss.read()['data']
#    ip_list = []
#    for ctr in range(0, len(data[data.keys()[0]])):
#        ip_address = data['ip_in'][ctr]
#        if not ip_address in ip_list:
#            ip_list.append(ip_address)
#    for vvvvv in ip_list:
#        print tengbe.ip2str(vvvvv), ',',
#    print ''
#    time.sleep(1)
#
#sys.exit()

gotmyshit=False
while not gotmyshit:
    data = f.snapshots.snapreord0_ss.read(man_trig=True)['data']
    for ctr in range(0, len(data[data.keys()[0]])):
        d0 = (data['d20_3'][ctr] >> 10) & 0xff
        d1 = data['d20_3'][ctr] & 0xff
        dx = (data['d20_2'][ctr] << 20) & \
                (data['d20_1'][ctr] << 10) & \
                ((data['d20_0'][ctr] >> 10) & 0xff)
        d7 = data['d20_0'][ctr] & 0xff
        d80 = (data['d20_3'][ctr] << 60) | (data['d20_2'][ctr] << 40) | \
            (data['d20_1'][ctr] << 20) | (data['d20_0'][ctr] << 0)
        timestamp = data['timestamp'][ctr]
#        timestamp = -1
        print timestamp, '-', d0, '-', d1, '-', dx, '-', d7, '-', d80
    gotmyshit = True

#f.snapshots.snapreord0_ss.print_snap()
f.disconnect()
sys.exit()

# end
