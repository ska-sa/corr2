# -*- coding: utf-8 -*-
"""
Created on Mon Mar 31 13:10:05 2014

@author: paulp
"""

import threading
import time
import sys

def check_vaccs_okay(arg1, arg2):
    print(arg1, arg2, time.time()
    threading.Timer(5, check_vaccs_okay, [arg1+1], {'arg2': arg2}).start()


threading.Timer(5, check_vaccs_okay, [3], {'arg2': 'sam'}).start()

print('timer is running'

stime = time.time()
while time.time() < stime + 21:
    time.sleep(0.2)

print('all done'
sys.exit(0)

import logging
import sys


logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logging.root.setLevel(logging.DEBUG)

LOGGER = logging.getLogger(__name__)

def emit(self, record):
    record.msg = 'ADDING EXTRA FOO:' + record.msg

LOGGER.addHandler(HostLogHandler())
LOGGER.info('woooo')



sys.exit(0)


hosts = 'roach020958', 'roach02091b', 'roach020914', 'roach020922',\
        'roach020921', 'roach020927', 'roach020919', 'roach020925',\
        'roach02091a', 'roach02091e', 'roach020923', 'roach020924', 'roach020959', 'roach020915'

import corr2.utils as utils
import casperfpga
import time
import Queue
import threading

fpgas = utils.threaded_create_fpgas_from_hosts(hosts)
print(fpgas

stime = time.time()
utils.program_fpgas(fpgas, '/home/paulp/test_2014_Aug_12_1438.fpg')
print('that took %.3f seconds' % (time.time() - stime)

print(utils.threaded_fpga_function(fpgas, 10, 'listdev')

print(utils.threaded_fpga_function(fpgas, 10, 'deprogram')

print(utils.threaded_fpga_function(fpgas, 10, 'disconnect')

sys.exit()

def countlettersinstrings(strings, funcname, *args):
    for word in strings:
        print(eval('word.%s' % funcname)(*args)

a = ['asddasdasdasd', 'bnmbnmbnmbnm', 'tyutyutyutyu']
countlettersinstrings(a, 'capitalize')
countlettersinstrings(a, 'count', 'a')

sys.exit()


stime = time.time()
fpgas = []
for h in hosts:
    f = casperfpga.KatcpClientFpga(h)
    fpgas.append(f)
print('that took %.3f' % (time.time() - stime)
for fpga in fpgas:
    print(fpga.host, fpga.is_connected()

stime = time.time()
othefpgas = utils.create_fpgas_from_hosts(hosts)
print('and that took %.3f' % (time.time() - stime)
for fpga in othefpgas:
    print(fpga.host, fpga.is_connected()

sys.exit()

logging.basicConfig(level=logging.INFO)

utils.non_blocking_request(fpgas, 600, 'update-romfs', [])

sys.exit()

stime = time.time()
utils.threaded_fpga_operation(fpgas, hosthost, -1, 'zebra', 123456)
etime = time.time()
LOGGER.info('Request to %d FPGAs took %.3f seconds.' % (len(fpgas), etime - stime))

# fpgas[0].deprogram()
# stime = time.time()
# fpgas[0].upload_to_ram_and_program('/srv/bofs/feng/r2_256w_4k_32x_r434_2014_Jul_21_1700.fpg')
# etime = time.time()
# LOGGER.info('Programming 1 FPGA took %.3f seconds.' % (etime - stime))

# for f in fpgas:
#     f.deprogram()
# utils.program_fpgas('/srv/bofs/feng/r2_256w_4k_32x_r434_2014_Jul_21_1700.fpg', fpgas)


stime = time.time()
utils.non_blocking_request(fpgas, 600, 'listdev', [])
etime = time.time()
LOGGER.info('Request to %d FPGAs took %.3f seconds.' % (len(fpgas), etime - stime))

stime = time.time()
for f in fpgas:
    f.listdev()
etime = time.time()
LOGGER.info('Request to %d FPGAs took %.3f seconds.' % (len(fpgas), etime - stime))

sys.exit()


import time
import sys

waitlist = [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]
waittime = 0.1

iterations = 0
stime = time.time()
while len(waitlist) > 0:
    print('WHLOOP, %d items left' % len(waitlist)
    for w in waitlist:
        print('\t%d' % w
        waitlist.pop(waitlist.index(w))
        iterations += 1
    if len(waitlist) > 0:
        time.sleep(waittime)
etime = time.time()
print('that took %d iterations and %0.3f seconds' % (iterations, etime - stime)

waitlist = [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]
iterations = 0
stime = time.time()
while len(waitlist) > 0:
    donelist = []
    print('WHLOOP, %d items left' % len(waitlist)
    for w in waitlist:
        print('\t%d' % w
        donelist.append(w)
        iterations += 1
    for done in donelist:
        waitlist.pop(waitlist.index(done))
    if len(waitlist) > 0:
        time.sleep(waittime)
etime = time.time()
print('that took %d iterations and %0.3f seconds' % (iterations, etime - stime)

sys.exit(0)

import time, sys, logging, argparse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

#sys.path.insert(0, '/home/paulp/code/corr2.ska.github/src')

from casperfpga import KatcpClientFpga

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
fhosts = ['roach020958', 'roach02091b', 'roach020914', 'roach020922']
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

fchan_per_x = 128


xengines



f = KatcpClientFpga('roach020921')
f.get_system_information()

#
#import corr, struct
#f = corr.katcp_wrapper.FpgaClient('roach020921')
#time.sleep(0.3)
#sd = f.snapshot_get('snap_reord0_ss', circular_capture=True, man_trig=True)
#up = struct.unpack('>2048Q', sd['data'])
#for ctr in range(0, 2048, 2):
#    print(ctr, ':',
#    w1 = up[ctr]
#    w2 = up[ctr+1]
#    sync = (w1 >> 63) & 0x01
#    data = (w1 >> 31) & 0xffffffff
#    valid = (w1 >> 30) & 0x01
#    dtime = ((w1 & (pow(2,30)-1)) << 12) & ((w2 >> 46) & (pow(2,18)-1))
#    freq = (w2 >> 4) & (pow(2,42)-1)
#    xeng_err = (w2 >> 3) & 0x01
#    feng_err = (w2 >> 2) & 0x01
#    adc_err = (w2 >> 1) & 0x01
#    nd_on = (w2 >> 0) & 0x01
#    print('%10d\t%10d\t%10d\t%2d\t%2d\t%2d\t%2d\t%2d\t%2d' % (data, dtime, freq, sync, valid, xeng_err, feng_err, adc_err, nd_on)
#print(''

f = KatcpClientFpga('roach020921')
f.get_system_information()
snapdata = f.snapshots.snap_reord0_ss.read(circular_capture=True, man_trig=True)['data']
for ctr in range(0, len(snapdata['sync'])):
    print(ctr, ':',
    sync = snapdata['sync'][ctr]
    data = snapdata['data'][ctr]
    valid = snapdata['valid'][ctr]
    dtime = snapdata['time'][ctr]
    freq = snapdata['freq'][ctr]
    xeng_err = snapdata['xeng_err'][ctr]
    feng_err = snapdata['feng_err'][ctr]
    adc_err = snapdata['adc_over'][ctr]
    nd_on = snapdata['nd_on'][ctr]
    print('%10d\t%10d\t%10d\t%2d\t%2d\t%2d\t%2d\t%2d\t%2d' % (data, dtime, freq, sync, valid, xeng_err, feng_err, adc_err, nd_on)

sys.exit()

#for host in [dhost]:
#    fpga = KatcpClientFpga(host)
#    fpga.get_system_information()
#    fpga.registers.control.write(cnt_rst='pulse')

#for host in fhosts:
#    fpga = KatcpClientFpga(host)
#    fpga.get_system_information()
#    fpga.registers.control.write(cnt_rst='pulse')

import numpy

xfpgas = []
for host in xhosts:
    fpga = KatcpClientFpga(host)
    fpga.get_system_information()
    xfpgas.append(fpga)
#    fpga.registers.control.write(cnt_rst='pulse', gbe_debug_rst='pulse', clr_status='pulse')

xfreqs = {}
for f in xfpgas:
    xfreqs[f.host] = {}
    for snapctr in range(0,4):
        xfreqs[f.host][snapctr] = {}
        for ctr in range(0,4):
            xfreqs[f.host][snapctr][ctr] = []

done = False
for ctr in range(0, 500):
    try:
        for f in xfpgas:
            snapdata0 = f.snapshots.snap_unpack0_ss.read()['data']
            snapdata1 = f.snapshots.snap_unpack1_ss.read()['data']
            snapdata2 = f.snapshots.snap_unpack2_ss.read()['data']
            snapdata3 = f.snapshots.snap_unpack3_ss.read()['data']
            for snapctr, snapdata in enumerate([snapdata0, snapdata1, snapdata2, snapdata3]):
                for pktctr in range(0, len(snapdata['eof'])):
                    if snapdata['eof'][pktctr] == 1:
                        if not snapdata['valid'][pktctr] == 1:
                            raise RuntimeError('(!valid && eof) ?!?!')
                        fengid = snapdata['feng_id'][pktctr]
                        freq = snapdata['freq'][pktctr]
                        xfreqs[f.host][snapctr][fengid].append(freq)
                        xfreqs[f.host][snapctr][fengid] = list(numpy.unique(xfreqs[f.host][snapctr][fengid]))
                        xfreqs[f.host][snapctr][fengid].sort()
    except KeyboardInterrupt:
        done = True
    print(ctr,
    sys.stdout.flush()
    if done:
        break
print(''

for f in xfpgas:
    print(f.host, f.registers.board_id.read()['data'], ':'
    for snapctr in range(0,4):
        print('\t', 'stream%i'%snapctr, ':'
        for ctr in range(0,4):
            print('\t\t', 'ant%i'%ctr, xfreqs[f.host][snapctr][ctr]

for f in xfpgas:
    f.disconnect()

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
#    print([tengbe.ip2str(ip) for ip in iplist]
#
#sys.exit()

#for host in rts_roaches:
#    f = KatcpClientFpga(host)
#    time.sleep(0.3)
#    f.upload_to_ram_and_program('/home/paulp/r2_2f_4x_4a_4k_r366_2014_Mar_18_1306.fpg', wait_complete=True)
#    f.test_connection()
#    f.get_system_information()
#    print(f.host
#sys.exit()

#fdig = Digitiser(txhost)
#time.sleep(0.3)
#fdig.test_connection()
#fdig.get_system_information()
#numgbes = len(fdig.dev_tengbes)
#print(numgbes
#print(fdig.get_current_time()
#print(fdig.devices['gbe3'].tap_info()
#print(fdig.devices['gbe3'].read_counters()
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
    print(50*'='
    print(f.registers.mcnt_nolock.read()
    print(''
    print(f.registers.fifo_of0.read()
    print(f.registers.fifo_of1.read()
    print(f.registers.fifo_of2.read()
    print(f.registers.fifo_of3.read()
    print(''
    print(f.registers.fifo_pktof0.read()
    print(f.registers.fifo_pktof1.read()
    print(f.registers.fifo_pktof2.read()
    print(f.registers.fifo_pktof3.read()
    print(''
    print(f.registers.spead_err0.read()
    print(f.registers.spead_err1.read()
    print(f.registers.spead_err2.read()
    print(f.registers.spead_err3.read()
    print(''
    print('CT_SYNC \t', f.registers.ct_synccnt.read()
    print('CT_valid\t', f.registers.ct_validcnt.read()
    print(f.registers.ct_errcnt0.read()
    print(f.registers.ct_parity_errcnt0.read()
    print(f.registers.ct_errcnt1.read()
    print(f.registers.ct_parity_errcnt1.read()
    print(''
    time.sleep(1)


#while True:
#    data = f.snapshots.snapfifo_0_ss.read(man_valid=True, man_trig=True)['data']
#    timestamp_list = []
#    for ctr in range(0, len(data[data.keys()[0]])):
#        thistime = data['timestamp'][ctr]
#        if not thistime in timestamp_list:
#            timestamp_list.append(thistime)
#    for vvvvv in timestamp_list:
#        print(vvvvv, ',',
#    print(''
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
#        print(tengbe.ip2str(vvvvv), ',',
#    print(''
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
        print(timestamp, '-', d0, '-', d1, '-', dx, '-', d7, '-', d80
    gotmyshit = True

#f.snapshots.snapreord0_ss.print_snap()
f.disconnect()
sys.exit()

# end
