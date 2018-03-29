__author__ = 'paulp'

import casperfpga
import logging

logging.basicConfig(level=logging.INFO)

bitfile = '/home/paulp/snb_b_deconly_2015_Mar_18_1030.fpg'
bitfile = '/home/paulp/snb_b_ser2par_2015_Mar_19_1619.fpg'

host = 'roach020a03'

f = casperfpga.KatcpFpga(host)
if False:
    f.upload_to_ram_and_program(bitfile)

    # roach020a03:
    # INFO:corr2.fxcorrelator:		DataSource(ant0_x) @ 239.2.0.64+2 port(8888)
    # INFO:corr2.fxcorrelator:		DataSource(ant0_y) @ 239.2.0.66+2 port(8888)
    #
    # INFO:corr2.fxcorrelator:fhost(roach020a03) gbe(gbe0) MAC(02:02:00:00:01:0a) IP(10.100.0.150) port(8888) board(0) txIPbase(239.2.0.150) txPort(8888)
    # INFO:corr2.fxcorrelator:fhost(roach020a03) gbe(gbe1) MAC(02:02:00:00:01:0b) IP(10.100.0.151) port(8888) board(0) txIPbase(239.2.0.150) txPort(8888)
    # INFO:corr2.fxcorrelator:fhost(roach020a03) gbe(gbe2) MAC(02:02:00:00:01:0c) IP(10.100.0.152) port(8888) board(0) txIPbase(239.2.0.150) txPort(8888)
    # INFO:corr2.fxcorrelator:fhost(roach020a03) gbe(gbe3) MAC(02:02:00:00:01:0d) IP(10.100.0.153) port(8888) board(0) txIPbase(239.2.0.150) txPort(8888)

    f.registers.control.write(gbe_txen=False)
    f.registers.control.write(gbe_rst=False)

    macbase = 0x0a
    feng_ip_base = 150
    feng_port = 8888
    for gbe in f.tengbes:
        this_mac = '%s%02x' % ('02:02:00:00:01:', macbase)
        this_ip = '%s%d' % ('10.100.0.', feng_ip_base)
        gbe.setup(mac=this_mac, ipaddress=this_ip,
                  port=feng_port)
        logging.info('fhost(%s) gbe(%s) MAC(%s) IP(%s) port(%i)' % (f.host, gbe.name, this_mac, this_ip, feng_port))
        macbase += 1
        feng_ip_base += 1

    for gbe in f.tengbes:
        gbe.tap_start(True)

    f.registers.control.write(gbe_rst=False)

    import time
    print('waiting for arp'
    time.sleep(20)

    print('subscribing to multicast'
    f.tengbes.gbe0.multicast_receive('239.2.0.64', 0)
    f.tengbes.gbe1.multicast_receive('239.2.0.65', 0)
    f.tengbes.gbe2.multicast_receive('239.2.0.66', 0)
    f.tengbes.gbe3.multicast_receive('239.2.0.67', 0)
else:
    f.get_system_information()


import time
import numpy
import matplotlib.pyplot as pyplot

pyplot.ion()

while True:
    EXPECTED_FREQS = 4096
    # with serial to parallel block
    f.snapshots.snap_serial0_ss.arm()
    f.snapshots.snap_serial1_ss.arm()
    f.registers.snaparm.write(sersnap_arm='pulse')
    time.sleep(1.0)
    d1 = f.snapshots.snap_serial0_ss.read(arm=False)['data']
    d2 = f.snapshots.snap_serial1_ss.read(arm=False)['data']
    cplx = []
    for ctr in range(0, len(d1['dv'])):
        cplx.append(complex(d1['d0_r'][ctr], d1['d0_i'][ctr]))
        cplx.append(complex(d1['d1_r'][ctr], d1['d1_i'][ctr]))
        cplx.append(complex(d1['d2_r'][ctr], d1['d2_i'][ctr]))
        cplx.append(complex(d2['d3_r'][ctr], d2['d3_i'][ctr]))
    showdata = EXPECTED_FREQS * [0]
    for ctr, sample in enumerate(cplx[:EXPECTED_FREQS]):
        showdata[ctr] = pow(sample.real, 2) + pow(sample.imag, 2)
    pyplot.cla()
    pyplot.semilogy(showdata[0:2048])
    pyplot.draw()


while True:

    d = f.snapshots.snap_mixed0_ss.read(man_trig=True)['data']
    cplx = []
    for ctr in range(0, len(d['p0_18r'])):
        cplx.append(complex(d['p0_18r'][ctr], d['p0_18i'][ctr]))

    # d = f.snapshots.snap_mixed_s_ss.read(man_trig=True)['data']
    # cplx = []
    # for ctr in range(0, len(d['p0_10r'])):
    #     cplx.append(complex(d['p0_10r'][ctr], d['p0_10i'][ctr]))

    # f.snapshots.snap_mixed_ss.arm()
    # f.snapshots.snap_mixed1_ss.arm()
    # f.snapshots.snap_mixed2_ss.arm()
    # f.registers.mixsnap_ctrl.write(trig_snap='pulse')
    # d1 = f.snapshots.snap_mixed_ss.read(arm=False)['data']
    # d2 = f.snapshots.snap_mixed1_ss.read(arm=False)['data']
    # d3 = f.snapshots.snap_mixed2_ss.read(arm=False)['data']
    # cplx = []
    # for ctr in range(0, len(d1['r0'])):
    #     cplx.append(complex(d1['r0'][ctr], d1['i0'][ctr]))
    #     cplx.append(complex(d1['r1'][ctr], d1['i1'][ctr]))
    #     cplx.append(complex(d1['r2'][ctr], d1['i2'][ctr]))
    #     cplx.append(complex(d2['r3'][ctr], d2['i3'][ctr]))
    #     cplx.append(complex(d2['r4'][ctr], d2['i4'][ctr]))
    #     cplx.append(complex(d2['r5'][ctr], d2['i5'][ctr]))
    #     cplx.append(complex(d3['r6'][ctr], d3['i6'][ctr]))
    #     cplx.append(complex(d3['r7'][ctr], d3['i7'][ctr]))

    EXPECTED_FREQS = 4096
    fftdata = numpy.fft.fft(cplx)
    showdata = EXPECTED_FREQS * [0]
    for ctr, sample in enumerate(fftdata[:EXPECTED_FREQS]):
        showdata[ctr] = pow(sample.real, 2) + pow(sample.imag, 2)
    print(time.time(), showdata.index(max(showdata)),

    # pyplot.subplot(211)
    # pyplot.cla()
    # pyplot.hist(numpy.real(cplx), bins=1024)
    # pyplot.subplot(212)
    # pyplot.cla()
    # pyplot.hist(numpy.imag(cplx), bins=1024)

    pyplot.subplot(211)
    pyplot.cla()
    pyplot.semilogy(showdata)

    d = f.snapshots.snap_pfb0_ss.read()['data']

    print('\n'

    print(d.keys()

    # for ctr in range(0, len(d['p0_31r'])):
    #     print(ctr, d['p0_31r'][ctr], d['dv'][ctr]
    #
    # break

    # last_val = d['p0_31r'][0] - 1
    # start_index = -1
    # for ctr in range(0, len(d['p0_31r'])):
    #     if last_val != d['p0_31r'][ctr]:
    #         if start_index < ctr - 1:
    #             print('same from %i to %i = %i' % (start_index, ctr - 1, ctr - 1 - start_index)
    #         start_index = ctr
    #     last_val = d['p0_31r'][ctr]
    #
    # break

    showdata = EXPECTED_FREQS * [0]
    for ctr in range(0, len(d['p0_31r'])):
        showdata[ctr] = pow(d['p0_31r'][ctr], 2) + pow(d['p0_31i'][ctr], 2)
    print(time.time(), showdata.index(max(showdata))

    pyplot.subplot(212)
    pyplot.cla()
    pyplot.semilogy(showdata[0:2048])

    pyplot.draw()
    time.sleep(1)



