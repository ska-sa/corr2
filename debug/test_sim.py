__author__ = 'paulp'

import spead64_48 as spead
import numpy
import argparse
import casperfpga
from corr2 import utils
import sys

lab_xhosts = 'roach020921', 'roach020927', 'roach020919', 'roach020925',\
             'roach02091a', 'roach02091e', 'roach020923', 'roach020924'

allhosts = 'roach020958', 'roach02091b', 'roach020914', 'roach020922', 'roach020921',\
           'roach020927', 'roach020919', 'roach020925', 'roach02091a', 'roach02091e',\
           'roach020923', 'roach020924'

site_fhosts = 'roach020916', 'roach020913', 'roach020912', 'roach02092B'

site_xhosts = 'roach02092F', 'roach020918', 'roach02090C', 'roach020619',\
              'roach020930', 'roach02091F', 'roach020928', 'roach020920'

hosts = lab_xhosts
GBE_PORT = 8888
GBE_HOST_IP = '10.1.0.1'
X_GBE_PREFIX = '10.1.0.'
DATA_PORT = 8888


def deprogram_all():
    for h in allhosts:
        f = casperfpga.KatcpClientFpga(h)
        try:
            f.get_system_information()
        except RuntimeError:
            print('could not get to host %s' % f.host
            continue
        f.deprogram()
    print('deprogrammed all'


def stop_tx():
    print('Stopping TX.'
    for f in fpgas:
        f.registers.ctrl.write(comms_en=False)


def send_meta():
    print('Sending meta'
    spead_ig = spead.ItemGroup()
    spead_tx = spead.Transmitter(spead.TransportUDPtx('127.0.0.1', DATA_PORT))
    # ndarray = numpy.dtype(numpy.int64), (4096 * 40 * 1, 1, 1)
    ndarray = numpy.dtype(numpy.int32), (4096, 40, 2)
    spead_ig.add_item(name='xeng_raw', id=0x1800, description='raw simulator data', ndarray=ndarray)
    spead_ig.add_item(name='timestamp', id=0x1600, description='Timestamp', shape=[],
                      fmt=spead.mkfmt(('u', spead.ADDRSIZE)), init_val=0)
    spead_tx.send_heap(spead_ig.get_heap())


def start_tx():
    print('Starting TX.'
    for f in fpgas:
        f.registers.ctrl.write(comms_en=True)


def setup():
    txip = casperfpga.tengbe.str2ip(GBE_HOST_IP)
    xipbase = 110
    macbase = 10
    boardbase = 0

    print('programming...',
    sys.stdout.flush()
    utils.program_fpgas('/srv/bofs/xeng/r2_2f_r366_sim_2014_Aug_01_1556.fpg', fpgas)
    #utils.program_fpgas('/home/paulp/xengsim_test_2014_Aug_01_1355.fpg', fpgas)
    print('done.'

    for fpga_ in fpgas:
        fpga_.get_system_information()
        fpga_.registers.simulator.write(en=False, rst='pulse')
        fpga_.registers.ctrl.write(comms_rst=True, comms_en=False)
        fpga_.registers.ctrl.write(comms_status_clr='pulse')
        fpga_.registers.acc_len.write_int(100)
        fpga_.registers.txip.write(txip=txip)
        fpga_.registers.txport.write_int(DATA_PORT)
        fpga_.registers.board_id.write_int(boardbase)
        boardbase += 1
        for gbe in fpga_.tengbes:
            gbe.setup(mac='02:02:00:00:02:%02x' % macbase, ipaddress=(X_GBE_PREFIX + '%d' % xipbase), port=GBE_PORT)
            macbase += 1
            xipbase += 1
        for gbe in fpga_.tengbes:
            gbe.tap_start()
    for fpga_ in fpgas:
        fpga_.tap_arp_reload()
    for fpga_ in fpgas:
        fpga_.registers.ctrl.write(comms_rst=False)
        fpga_.registers.simulator.write(en=True)
        fpga_.registers.acc_len.write_int(200)
    #send_meta()
    #start_tx()
    print('now check for spead heaps'

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Start a corr2 instrument server.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--start', dest='start_tx', action='store_true',
                    default=False,
                    help='start transmission')
    parser.add_argument('--stop', dest='stop_tx', action='store_true',
                    default=False,
                    help='stop transmission')
    parser.add_argument('--meta', dest='meta', action='store_true',
                    default=False,
                    help='send meta information')
    parser.add_argument('--setup', dest='setup', action='store_true',
                    default=False,
                    help='set up the boards')
    parser.add_argument('--deprogram', dest='deprogram_all', action='store_true',
                    default=False,
                    help='deprogram ALL the boards')
    args = parser.parse_args()

    if args.deprogram_all:
        deprogram_all()

    print('making roaches'
    fpgas = []
    for h in hosts:
        f = casperfpga.KatcpClientFpga(h)
        try:
            f.get_system_information()
        except RuntimeError:
            pass
        fpgas.append(f)

    if args.setup:
        setup()

    if args.stop_tx:
        stop_tx()

    if args.meta:
        send_meta()

    if args.start_tx:
        start_tx()

# end