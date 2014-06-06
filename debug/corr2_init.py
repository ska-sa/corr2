# -*- coding: utf-8 -*-
# pylint: disable-msg = C0301
# pylint: disable-msg = C0103
"""
Created on Mon Oct 28 17:01:29 2013

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
parser.add_argument('-u', '--unicast', dest='unicast', action='store_true',
                    default=False,
                    help='transmit unicast to the first f-engine, not multicast to all of them')
args = parser.parse_args()

andrewhost = 'roach020915'
dhost = 'roach020959'
fhosts = ['roach020958', 'roach02091b', 'roach020914', 'roach020922']
xhosts = ['roach020921', 'roach020927', 'roach020919', 'roach020925',
          'roach02091a', 'roach02091e', 'roach020923', 'roach020924']

dfpg = '/srv/bofs/deng/r2_deng_tvg_2014_May_30_1123.fpg'
ffpg = '/srv/bofs/feng/feng_rx_test_2014_Jun_05_1818.fpg'
xfpg = '/srv/bofs/xeng/x_rx_reorder_2014_Jun_02_1913.fpg'

fdig = Digitiser(dhost)
ffpgas = []
for host in fhosts:
    fpga = KatcpClientFpga(host)
    ffpgas.append(fpga)
xfpgas = []
for host in xhosts:
    fpga = KatcpClientFpga(host)
    xfpgas.append(fpga)
all_fpgas = [fdig]
all_fpgas.extend(ffpgas)
all_fpgas.extend(xfpgas)

if args.deprogram:
    for fpga in all_fpgas:
        try:
            fpga.deprogram()
            fpga.disconnect()
        except:
            pass
    sys.exit()

if args.restart:
    for fpga in all_fpgas:
        fpga.katcprequest(name='restart', require_ok=False)
        fpga.disconnect()
    sys.exit()

program = args.program
setup_gbe = args.setupgbe

if program:
    setup_gbe = True
    for fpga in all_fpgas:
        fpga.deprogram()
    ftuple = [(fdig, dfpg)]
    ftuple.extend([(fpga, ffpg) for fpga in ffpgas])
    ftuple.extend([(fpga, xfpg) for fpga in xfpgas])
    stime = time.time()
    print 'Programming: ',
    sys.stdout.flush()
    misc.program_fpgas(ftuple, timeout=45)
    print time.time() - stime
    ftuple = None

for fpga in all_fpgas:
    fpga.test_connection()
    fpga.get_system_information()

if setup_gbe:
    # stop sending data
    fdig.registers.control.write(gbe_txen = False)
    for fpga in ffpgas:
        fpga.registers.control.write(gbe_txen = False)
    for fpga in xfpgas:
        fpga.registers.control.write(gbe_txen = False)

    # pulse the cores reset lines from False to True
    fdig.registers.control.write(gbe_rst = False)
    for fpga in ffpgas:
        fpga.registers.control.write(gbe_rst = False)
    for fpga in xfpgas:
        fpga.registers.control.write(gbe_rst = False)
#    fdig.registers.control.write(gbe_rst = True)
#    for fpga in ffpgas:
#        fpga.registers.control.write(gbe_rst = True)
#    for fpga in xfpgas:
#        fpga.registers.control.write(gbe_rst = True)

    # start the local timer on the test d-engine - mrst, then a fake sync
    fdig.registers.control.write(mrst = 'pulse')
    fdig.registers.control.write(msync = 'pulse')

    # reset the fengine fpgas
    for fpga in ffpgas:
        fpga.registers.control.write(sys_rst='pulse')

    # x-engines don't have a reset?

    # the all_fpgas have tengbe cores, so set them up
    fipbase = 150
    xipbase = 110
    fdig.tengbes.gbe0.setup(mac='02:02:00:00:00:01', ipaddress='10.0.0.70', port=7777)
    fdig.tengbes.gbe1.setup(mac='02:02:00:00:00:02', ipaddress='10.0.0.71', port=7777)
    fdig.tengbes.gbe2.setup(mac='02:02:00:00:00:03', ipaddress='10.0.0.72', port=7777)
    fdig.tengbes.gbe3.setup(mac='02:02:00:00:00:04', ipaddress='10.0.0.73', port=7777)
    macbase = 10
    board_id = 0
    for fpga in ffpgas:
        for gbe in fpga.tengbes:
            gbe.setup(mac='02:02:00:00:01:%02x' % macbase, ipaddress='10.0.0.%d' % fipbase, port=7777)
            macbase += 1
            fipbase += 1
        fpga.registers.iptx_base.write_int(tengbe.str2ip('10.0.0.%d' % xipbase))
        fpga.registers.tx_metadata.write(board_id=board_id, porttx=8778)
        board_id += 1
    macbase = 10
    board_id = 0
    for fpga in xfpgas:
        for gbe in fpga.tengbes:
            gbe.setup(mac='02:02:00:00:02:%02x' % macbase, ipaddress='10.0.0.%d' % xipbase, port=8778)
            macbase += 1
            xipbase += 1
        fpga.registers.board_id.write_int(board_id)
        board_id += 4 # see the model file as to why this must incrementby 4 - this needs to be changed!!

    # tap start
    for fpga in all_fpgas:
        for gbe in fpga.tengbes:
            gbe.tap_start(True)

    # set the destination IP and port for the tx
    if not args.unicast:
        fdig.write_int('gbe_iptx0', tengbe.str2ip('239.2.0.64'))
        fdig.write_int('gbe_iptx1', tengbe.str2ip('239.2.0.65'))
        fdig.write_int('gbe_iptx2', tengbe.str2ip('239.2.0.66'))
        fdig.write_int('gbe_iptx3', tengbe.str2ip('239.2.0.67'))
    else:
        fdig.write_int('gbe_iptx0', tengbe.str2ip('10.0.0.90'))
        fdig.write_int('gbe_iptx1', tengbe.str2ip('10.0.0.91'))
        fdig.write_int('gbe_iptx2', tengbe.str2ip('10.0.0.92'))
        fdig.write_int('gbe_iptx3', tengbe.str2ip('10.0.0.93'))
    fdig.write_int('gbe_porttx', 7777)

    if program:
        # start the tap devices
        arptime = 200
        stime = time.time()
        while time.time() < stime + arptime:
            print '\rWaiting for ARP, %ds   ' % (arptime-(time.time()-stime)),
            sys.stdout.flush()
            time.sleep(1)
        print 'done.'

    # release from reset
    for fpga in xfpgas:
        fpga.registers.control.write(gbe_rst=False)
    for fpga in ffpgas:
        fpga.registers.control.write(gbe_rst=False)
    fdig.registers.control.write(gbe_rst=False)

    # set the rx multicast groups
    if not args.unicast:
        for fpga in ffpgas:
            fpga.tengbes.gbe0.multicast_receive('239.2.0.64', 0)
            fpga.tengbes.gbe1.multicast_receive('239.2.0.65', 0)
            fpga.tengbes.gbe2.multicast_receive('239.2.0.66', 0)
            fpga.tengbes.gbe3.multicast_receive('239.2.0.67', 0)

    # enable the tvg on the digitiser and set up the pol id bits
    fdig.registers.control.write(tvg_select0=True)
    fdig.registers.control.write(tvg_select1=True)
    fdig.registers.id2.write(pol1_id=1)

    # start tx
    print 'Starting TX...',
    sys.stdout.flush()
    fdig.registers.control.write(gbe_txen=True)
#    sleeptime = 5
#    stime = time.time()
#    while time.time() < stime + sleeptime:
#        print '\rStarting TX... %ds   ' % (sleeptime-(time.time()-stime)),
#        sys.stdout.flush()
#        time.sleep(1)
#    for fpga in ffpgas:
#        fpga.registers.control.write(gbe_txen=True)
    print 'done.'

## print 10gbe core details
#fdig.tengbes.gbe0.print_10gbe_core_details(arp=True)
#fdig.tengbes.gbe1.print_10gbe_core_details(arp=True)
#fdig.tengbes.gbe2.print_10gbe_core_details(arp=True)
#fdig.tengbes.gbe3.print_10gbe_core_details(arp=True)
#for fpga in ffpgas:
#    fpga.tengbes.gbe0.print_10gbe_core_details(arp=True)
#    fpga.tengbes.gbe1.print_10gbe_core_details(arp=True)
#    fpga.tengbes.gbe2.print_10gbe_core_details(arp=True)
#    fpga.tengbes.gbe3.print_10gbe_core_details(arp=True)

#ffpgas[0][0].registers.snap_control.write(trig_reord_en=True)
#ffpgas[0][0].snapshots.snapreord0_ss.print_snap(man_trig=True)

for fpga in all_fpgas:
    fpga.disconnect()
sys.exit()

def print_gbe_tx(only_eofs=False, num_lines=-1):
    # read the tengbe snapshot on tx
    stx = fdig.devices['snap_gbe_tx_ss']
    txgbedata = stx.read(man_valid=False)['data']
    if num_lines == -1:
        num_lines = len(txgbedata['data'])
    for ctr in range(0, num_lines):
        pstr = '%05i ' % ctr
        pstr2 = ''
        for key in txgbedata.keys():
            if key == 'ip':
                pstr = '%s%s(%s) ' % (pstr, key, tengbe.ip2str(txgbedata[key][ctr]))
            else:
                pstr = '%s%s(%i) ' % (pstr, key, txgbedata[key][ctr])
            pstr2 = '%s %i' % (pstr2, txgbedata[key][ctr])
        if only_eofs:
            if txgbedata['eof'][ctr]:
                print pstr
        else:
            print pstr

def print_gbe_rx(only_eofs=False):
    srx = ffpgas[0].devices['snap_gbe_rx00_ss']
    rxgbedata = srx.read(man_trig=True, man_valid=True)['data']
    for ctr in range(0, len(rxgbedata['data'])):
        pstr = '%05i ' % ctr
        for key in rxgbedata.keys():
            pstr = '%s%s(%i) ' % (pstr, key, rxgbedata[key][ctr])
        if only_eofs:
            if rxgbedata['eof'][ctr]:
                print pstr
        else:
            print pstr

def print_tx_stats(numtimes = 2):
    oldcnt = 0
    olderr = 0
    fdig.registerscontrol.write(clr_status='pulse')
    times = numtimes
    while(times > 0):
        newcnt = fdig.read_uint('gbetx_cnt00')
        newerr = fdig.read_uint('gbetx_errcnt00')
        print 'cnt(%i,%i) err(%i,%i)' % (newcnt, newcnt-oldcnt, newerr, newerr-olderr)
        oldcnt = newcnt
        olderr = newerr
        time.sleep(1)
        times = times - 1

def print_rx_stats(numtimes = 3):
    for f in ffpgas:
        oldcnt = 0
        olderr = 0
        oldover = 0
        oldbad = 0
        f.registerscontrol.write(cnt_rst='pulse')
        times = numtimes
        while(times > 0):
            newcnt = f.read_uint('gbe_rx_cnt00')
            newerr = f.read_uint('gbe_rx_err_cnt00')
            overcnt = f.read_uint('gbe_rx_over_cnt00')
            badcnt = f.read_uint('gbe_rx_bad_cnt00')
            rxvalid = f.read_uint('gbe_rx_valid_cnt00')
            rxeof = f.read_uint('gbe_rx_eof_cnt00')
            print 'cnt(%i,%i) err(%i,%i) over(%i,%i) bad(%i,%i) gbevalid(%i) gbeeof(%i)' % \
                (newcnt, newcnt-oldcnt, newerr, newerr-olderr, overcnt, overcnt-oldover, badcnt, badcnt-oldbad, rxvalid, rxeof)
            oldcnt = newcnt
            olderr = newerr
            oldover = overcnt
            oldbad = badcnt
            time.sleep(1)
            times = times - 1

def check_snap80_output(fpga):
    import threading, Queue
    snap_data0 = Queue.Queue()
    snap_data1 = Queue.Queue()
    def get_snap_data(snap, queue):
        try:
            data = snap.read(man_valid=False, man_trig=False, timeout=6, arm=True)
            queue.put(data)
        except:
            return
    fpga.devices['snap_ctrl'].write(sel_trig_d80=1) # trigger is manual from reg
    trig_snap0 = threading.Thread(target = get_snap_data, args = (fpga.devices['snap80_00_ss'], snap_data0, ))
    trig_snap1 = threading.Thread(target = get_snap_data, args = (fpga.devices['snap80_01_ss'], snap_data1, ))
    trig_snap0.start()
    trig_snap1.start()
    time.sleep(1)
    fpga.devices['snap_ctrl'].write(trig_d80='pulse')
    trig_snap1.join(7)
    d0 = snap_data0.get()
    d1 = snap_data1.get()
    old0 = (-1, -1)
    old1 = (-1, -1)
    for n,_ in enumerate(d0['d80']):
        d0_now = (d0['d80'][n], d0['timestamp'][n])
        d1_now = (d1['d80'][n], d1['timestamp'][n])
        print '0: %10d, %10d, %10d, %5d\t\t1: %10d, %10d, %10d, %5d - timediff(%10d)' % (
            d0_now[0], d0_now[0] - old0[0], d0_now[1], d0_now[1] - old0[1],
            d1_now[0], d1_now[0] - old1[0], d1_now[1], d1_now[1] - old1[1],
            d1_now[1] - d0_now[1])
#        if d['timestamp'][n] != old[0]:
#            print d['timestamp'][n], d['timestamp'][n] - old[0], d['d80'][n], d['d80'][n] - old[1]
#        else:
#            if abs(d['d80'][n] - old[1]) > 10:
#                print '\tDATA JUMP IN PACKET:\n\t\t',
#                for ctr in range(n-4, n+4):
#                    print d['d80'][ctr],
#                print ''
        old0 = d0_now
        old1 = d1_now

def check_snap80_eof(fpga, snaps):
    # arm
#    fpga.devices['snap_ctrl'].write(sel_we_d80=0) # write_enable is EOF
#    fpga.devices['snap_ctrl'].write(sel_we_d80=1) # write_enable is Valid
#    fpga.devices['snap_ctrl'].write(sel_trig_d80=0) # trigger is start
    fpga.devices['snap_ctrl'].write(sel_trig_d80=1, sel_we_d80=0) # trigger is manual from reg
    fpga.devices[snaps[0]]._arm()
    fpga.devices[snaps[1]]._arm()
    # trig
    fpga.devices['snap_ctrl'].write(trig_d80='pulse')
    # read
    d0 = fpga.devices[snaps[0]].read(man_valid=False, man_trig=False, timeout=5, arm=False)
    d1 = fpga.devices[snaps[1]].read(man_valid=False, man_trig=False, timeout=5, arm=False)
    old0 = (-1, -1)
    old1 = (-1, -1)
    for n,_ in enumerate(d0['d80']):
        d0_now = (d0['d80'][n], d0['timestamp'][n])
        d1_now = (d1['d80'][n], d1['timestamp'][n])
        if n == 0:
            firsttimediff = d1_now[1] - d0_now[1]
        else:
            datadiff0 = d0_now[0] - old0[0]
            datadiff1 = d1_now[0] - old1[0]
            timediff0 = d0_now[1] - old0[1]
            timediff1 = d1_now[1] - old1[1]
            timediff_channels = d1_now[1] - d0_now[1]
            print '%6d: 0: %10d, %10d, %10d, %5d\t\t1: %10d, %10d, %10d, %5d - timediff(%10d)' % (
                n,
                d0_now[0], datadiff0, d0_now[1], timediff0,
                d1_now[0], datadiff1, d1_now[1], timediff1,
                timediff_channels)
            if (datadiff0 != 2048) or (datadiff1 != 2048) or (timediff0 != 2) or (timediff1 != 2) or (pow(firsttimediff, 2) != 1) or (timediff_channels != firsttimediff):
                raise RuntimeError('The last packet was out of sync.')
        old0 = d0_now
        old1 = d1_now

def check_snap80_data(fpga, snaps):
    # arm
#    fpga.devices['snap_ctrl'].write(sel_we_d80=0) # write_enable is EOF
#    fpga.devices['snap_ctrl'].write(sel_we_d80=1) # write_enable is Valid
#    fpga.devices['snap_ctrl'].write(sel_trig_d80=0) # trigger is start
    fpga.devices['snap_ctrl'].write(sel_trig_d80=1, sel_we_d80=1) # trigger is manual from reg
    fpga.devices[snaps[0]]._arm()
    fpga.devices[snaps[1]]._arm()
    # trig
    fpga.devices['snap_ctrl'].write(trig_d80='pulse')
    # read
    d0 = fpga.devices[snaps[0]].read(man_valid=False, man_trig=False, timeout=5, arm=False)
    d1 = fpga.devices[snaps[1]].read(man_valid=False, man_trig=False, timeout=5, arm=False)
    old0 = (-1, -1)
    old1 = (-1, -1)
    for n,_ in enumerate(d0['d80']):
        d0_now = (d0['d80'][n], d0['timestamp'][n])
        d1_now = (d1['d80'][n], d1['timestamp'][n])
        if n == 0:
            firsttimediff = d1_now[1] - d0_now[1]
            lasttimediff = firsttimediff
        else:
            datadiff0 = d0_now[0] - old0[0]
            datadiff1 = d1_now[0] - old1[0]
            timediff0 = d0_now[1] - old0[1]
            timediff1 = d1_now[1] - old1[1]
            timediff_channels = d1_now[1] - d0_now[1]
            print '%6d: 0: %10d, %10d, %10d, %5d\t\t1: %10d, %10d, %10d, %5d - timediff(%10d)' % (
                n,
                d0_now[0], datadiff0, d0_now[1], timediff0,
                d1_now[0], datadiff1, d1_now[1], timediff1,
                timediff_channels)
            if (datadiff0 != 2) or (datadiff1 != 2) or (timediff0 != 0) or (timediff1 != 0) or (pow(firsttimediff, 2) != 1):
                if not ((((datadiff0 == 1026) and (timediff0 == 2)) or ((datadiff1 == 1026) and (timediff1 == 2))) and (lasttimediff == timediff_channels * -1)):
                    raise RuntimeError('The last packet was out of sync.', datadiff0, datadiff1, timediff0, timediff1, firsttimediff, timediff_channels)
            lasttimediff = timediff_channels
        old0 = d0_now
        old1 = d1_now

def check_fifo_output(fpga, pol, numrows = -1):
    if pol == 0:
        snaps = ['snapfifo_0_ss', 'snapfifo_1_ss']
    else:
        snaps = ['snapfifo_2_ss', 'snapfifo_3_ss']
    fpga.devices[snaps[0]]._arm()
    fpga.devices[snaps[1]]._arm()
    # trig
    fpga.devices['snap_ctrl'].write(trig_fifo='pulse')
    # read
    d0 = fpga.devices[snaps[0]].read(man_valid=False, man_trig=False, timeout=5, arm=False)
    d1 = fpga.devices[snaps[1]].read(man_valid=False, man_trig=False, timeout=5, arm=False)
    old0 = (-1, -1)
    old1 = (-1, -1)
    for n, _ in enumerate(d0['d80']):
        d0_now = (d0['d80'][n], d0['timestamp'][n])
        d1_now = (d1['d80'][n], d1['timestamp'][n])
        if n == 0:
            firsttimediff = d1_now[1] - d0_now[1]
            lasttimediff = firsttimediff
        else:
            datadiff0 = d0_now[0] - old0[0]
            datadiff1 = d1_now[0] - old1[0]
            timediff0 = d0_now[1] - old0[1]
            timediff1 = d1_now[1] - old1[1]
            timediff_channels = d1_now[1] - d0_now[1]
            print '%6d: 0: %10d, %10d, %10d, %5d\t\t1: %10d, %10d, %10d, %5d - timediff(%10d)' % (
                n,
                d0_now[0], datadiff0, d0_now[1], timediff0,
                d1_now[0], datadiff1, d1_now[1], timediff1,
                timediff_channels)
            if (datadiff0 != 4) or (datadiff1 != 4) or (timediff0 != 0) or (timediff1 != 0) or (pow(firsttimediff, 2) != 1):
                if not ((((datadiff0 == 1028) and (timediff0 == 2)) or ((datadiff1 == 1028) and (timediff1 == 2)))):# and (lasttimediff == timediff_channels * -1)):
                    raise RuntimeError('The last packet was out of sync.', datadiff0, datadiff1, timediff0, timediff1, firsttimediff, timediff_channels)
            lasttimediff = timediff_channels
        old0 = d0_now
        old1 = d1_now
        if (numrows == n):
            break

def check_reordered(fpga):
    '''Read the reordered snap block from the f-engines.
    Check the data there.
    '''
    snaps = ['snapreord0_ss', 'snapreord1_ss']
    fpga.devices['snap_ctrl'].write(trig_reord_en=False, sel_trig_reord=1)
    for snap in snaps:
        fpga.devices[snap]._arm()
    fpga.devices['snap_ctrl'].write(trig_reord_en=True)
    fpga.devices['snap_ctrl'].write(trig_reord='pulse')
    data = {}
    for snap in snaps:
        data[snap] = {}
        data[snap]['d'] = fpga.devices[snap].read(man_valid=False, man_trig=False, timeout=5, arm=False)
        data[snap]['old'] = {'d80': -1, 'timestamp': -1}
        data[snap]['current'] = {'d80': -1, 'timestamp': -1}
    pkt_ctr = 0
    first_packet= True
    for n,_ in enumerate(data[snaps[0]]['d']['d80']):
        data['snapreord0_ss']['current'] = {'d80': data['snapreord0_ss']['d']['d80'][n], 'timestamp': data['snapreord0_ss']['d']['timestamp'][n]}
        data['snapreord1_ss']['current'] = {'d80': data['snapreord1_ss']['d']['d80'][n], 'timestamp': data['snapreord0_ss']['d']['timestamp'][n]}
#        for snap in snaps:
#            data[snap]['current'] = {'d80': data[snap]['d']['d80'][n],
#                'timestamp': data[snap]['d']['timestamp'][n]}
        if n == 0:
            firsttimediff = data[snaps[1]]['current']['timestamp'] - \
                data[snaps[0]]['current']['timestamp']
            lasttimediff = firsttimediff
        else:
            diffs = {}
            for snap in snaps:
                diffs[snap] = {'data': (data[snap]['current']['d80'] - data[snap]['old']['d80']),
                    'time': (data[snap]['current']['timestamp'] - data[snap]['old']['timestamp'])}
            current = []
            diff = []
            for snap in snaps:
                current.append(data[snap]['current'])
                diff.append(diffs[snap])
            print '%6d,%6d: 0: %10d, %10d, %10d, %5d\t\t1: %10d, %10d, %10d, %5d\t%2d' % (n, pkt_ctr,
                current[0]['d80'], diff[0]['data'], current[0]['timestamp'], diff[0]['time'],
                current[1]['d80'], diff[1]['data'], current[1]['timestamp'], diff[1]['time'],
                data['snapreord1_ss']['d']['recvd'][n],)
            if (diff[0]['data'] != 2) or (diff[0]['time'] != 0) or (diff[1]['data'] != 2) or (diff[1]['time'] != 0):
                if (diff[0]['time']==1 and pkt_ctr==512) or first_packet:
                    pkt_ctr = 0
                    first_packet = False
                else:
                    raise RuntimeError('The last packet was out of sync.', diff[0]['data'], diff[0]['time'], pkt_ctr)
            if (current[1]['d80'] - current[0]['d80'] != 1):
                raise RuntimeError('Data error - d0(%10d) d1(%10d)', current[0]['d80'], current[1]['d80'])
        for snap in snaps:
            data[snap]['old'] = data[snap]['current']
        pkt_ctr += 1

def check_timestamps(fpga, sleeptime=1):
    def read_timestamp_data(sel):
        if sel == 0:
            maxtimestamp = fpga.devices['unpack_maxdiff'].read()['reg']
        else:
            maxtimestamp = fpga.devices['unpack_maxdiff1'].read()['reg']
        regvals = []
        for ctr in range((sel*5)+1,(sel*5)+6):
            regvals.append(fpga.devices['unpack_extra%i' % ctr].read()['reg'])
        source = (regvals[1] << 16) + (regvals[2] >> 16)
        mintime = ((regvals[2] & 0xffff) << 32) + regvals[3]
        maxtime = (regvals[4] << 16) + (regvals[4] & 0xffff)
        return (maxtimestamp, source, mintime, maxtime)
    f.devices.control.write(rst_maxtime='pulse')
    time.sleep(sleeptime)
    gbe0 = read_timestamp_data(0)
    gbe1 = read_timestamp_data(1)
    print '0(%13i,%13i,%13i,%13i)' % (gbe0[0], gbe0[1], gbe0[2], gbe0[3]), \
            '1(%13i,%13i,%13i,%13i)' % (gbe1[0], gbe1[1], gbe1[2], gbe1[3]), 'diff(%10i)' % (gbe0[1] - gbe1[1])

#print fdig.listdev()
#print fdig.registers['snap_ctrl']
#check_snap80_data(fdig, ['d80_00_ss', 'd80_01_ss'])

#check_snap80_data(ffpgas[0], ['snap80_0_ss', 'snap80_1_ss'])
#check_snap80_data(ffpgas[0], ['snap80_2_ss', 'snap80_3_ss'])
#for ctr in range(0,1000):
#    check_snap80_data(ffpgas[0], ['snap80_0_ss', 'snap80_1_ss'])
#    check_snap80_data(ffpgas[1], ['snap80_0_ss', 'snap80_1_ss'])
#    check_snap80_data(ffpgas[2], ['snap80_0_ss', 'snap80_1_ss'])
#check_snap80_data(fdig, ['d80_00_ss', 'd80_01_ss'])

#check_fifo_output(ffpgas[1], pol=0, numrows=50)
#check_fifo_output_expanded(ffpgas[1], pol=0, numrows=50)
#for ctr in range(0,1000):
#    for f in ffpgas:
#        check_fifo_output(f, pol=0)
#        check_fifo_output(f, pol=1)

for f in ffpgas:
    f.registers.control.write(rst_unpack_cnt='pulse')
ctr = 0
while False:
    print ctr
    for f in ffpgas:
        print '\t', f.host, ':',
        print f.devices['step_d0'].read()['reg'],
        print f.devices['step_d1'].read()['reg'],
        print f.devices['step_time'].read()['reg'],
        print f.devices['recvd0'].read()['reg'],
        print f.devices['recvd1'].read()['reg']
    time.sleep(1)
    ctr = ctr + 1

check_reordered(ffpgas[1])
for ctr in range(0,1000):
    for f in ffpgas:
        check_reordered(f)

#print ffpgas[0]