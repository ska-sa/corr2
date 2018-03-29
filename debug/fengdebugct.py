import logging
import scipy.io as sio
import numpy as np

import casperfpga

logging.basicConfig(level=logging.INFO)

# f = casperfpga.CasperFpga('skarab020306-01')
# f.get_system_information('/srv/bofs/xeng/s_b4a4x256f_2017-8-2_1745.fpg')
# d = f.snapshots.snap_rx_unpack0_ss.read(circular_capture=True,
#                                         man_trig=True, man_valid=True)['data']
# errors = []
# for ctr in range(len(d['valid'])):
#     print '%5i' % ctr,
#     for k in d:
#         print '%s(%i)' % (k, d[k][ctr]),
#     if (d['hdr_err'][ctr] or d['pad_err'][ctr] or d['pkt_len_err'][ctr] or \
#             d['magic_err'][ctr]) and (d['eof'][ctr]):
#         print 'ERROR',
#         errors.append(ctr)
#     print ''
# print errors
#
# raise RuntimeError

f = casperfpga.CasperFpga('skarab02030A-01')
# f.get_system_information('/home/paulp/bofs/feng_ct_2017-8-3_1734.fpg')
# f.get_system_information('/home/paulp/bofs/feng_ct_2017-8-4_1043.fpg')
# f.get_system_information('/home/paulp/bofs/feng_ct_2017-8-4_1250.fpg')
# f.get_system_information('/home/paulp/bofs/feng_ct_2017-8-4_1719.fpg')
f.get_system_information('/home/paulp/bofs/s_c856m4k_2017-8-4_1926.fpg')


def decode(word, size=32):
    vals = []
    for ctr in range(size):
        bit = (word >> ctr) & 0x01
        vals.append(bit)
    return vals


def get_ct_output(d=None, verbose=True):
    # if d is None:
    #     f.registers.x_setup.write(snap_arm=0)
    #     f.snapshots.output_ss.arm(
    #         circular_capture=False, man_trig=True, man_valid=True)
    #     f.snapshots.output1_ss.arm(
    #         circular_capture=False, man_trig=True, man_valid=True)
    #     f.registers.x_setup.write(snap_arm=1)
    #     d0 = f.snapshots.output_ss.read(arm=False)
    #     d1 = f.snapshots.output1_ss.read(arm=False)
    #     f.registers.x_setup.write(snap_arm=0)
    d = d or f.snapshots.pack_inputs_ss.read(man_trig=True,
                                             man_valid=True)['data']
    datalen = len(d['data_valid'])
    pkt_start = -1
    pktlens = {}
    if verbose:
        for ctr in range(datalen):
            print ctr,
            for k in d:
                print '%s(%i)' % (k, d[k][ctr]),
            print ''
    for ctr in range(datalen):
        if d['data_ready'][ctr] == 1:
            if ctr != datalen - 1:
                if d['data_valid'][ctr+1] == 0:
                    print 'pkt_start is one when next dv is zero?!'
                    return d
            pkt_start = ctr
        if pkt_start != -1:
            if (d['data_valid'][ctr] == 0) and (d['data_valid'][ctr-1] == 1):
                pktlen = ctr - pkt_start
                if pktlen not in pktlens:
                    pktlens[pktlen] = 0
                pktlens[pktlen] += 1
                pkt_start = -1
                if pktlen != 33 and ctr > 1:
                    print ctr
                    print pktlens
                    print 'pktlen is not 32?'
                    return d
    if verbose:
        print pktlens
    return None

loopctr = 0
while True:
    d = get_ct_output(None, False)
    if d is not None:
        get_ct_output(d, True)
        break
    print loopctr
    loopctr += 1

raise RuntimeError


def get_obuf_addr(d=None, verbose=True):
    d = d or f.snapshots.obuf_addr_ss.read(
        circular_capture=True, man_trig=False, man_valid=True)['data']
    last_rising_edge = -1
    pkt_errors = []
    syncs = []
    for ctr in range(len(d['rd_en'])):
        in_tag = d['wr_addr'][ctr] & 511
        in_dv = d['wr_en'][ctr]
        if verbose:
            print '%5i' % ctr, 'SYNC(%i)' % d['raw_sync'][ctr],
            print '   ||   ', 'WR_EN(%i)' % d['wr_en'][ctr],
            print 'WR_ADDR(%4i)' % d['wr_addr'][ctr],
            print 'BANK(%i)' % (d['wr_addr'][ctr] >> 9), 'TAG(%3i)' % in_tag,
            print '   ||   ',
            print 'RD_CNT_EN(%i)' % d['rd_ctr_en'][ctr],
            print 'RD_CNT(%4i)' % d['rd_ctr'][ctr],
            print 'RD_CNT_RST(%i)' % d['rd_ctr_rst'][ctr],
            print 'RD_BANK(%2i)' % d['rd_bank'][ctr],
            print 'RD_EN(%i)' % d['rd_en'][ctr],
            print 'RD_ADDR(%4i)' % d['rd_addr'][ctr],
            print 'MUX(%3i)' % d['muxsel'][ctr],
            print '   ||   ',
        if d['raw_sync'][ctr]:
            syncs.append(ctr)
            if verbose:
                print 'SYNC',
        if ctr > 0:
            if d['rd_en'][ctr] and d['rd_en'][ctr-1] == 0:
                last_rising_edge = ctr
            if d['rd_en'][ctr] == 0 and d['rd_en'][ctr-1]:
                pkt_len = ctr - last_rising_edge
                if pkt_len != 32 and ctr > 32:
                    pkt_errors.append(ctr)
                    if verbose:
                        print 'PKTLEN_ERROR(%i)' % pkt_len,
                        print ''
                    break
        if verbose:
            print ''
    print 'pkt_len_errors:', pkt_errors
    print 'syncs:', syncs
    print '----------'
    return pkt_errors, d

loopctr = 0
errctr = 0
while True:
    errs, d = get_obuf_addr(None, False)
    print loopctr, errs
    # if errs[0] > 60000:
    if errs[0] < 10000:
        filename = save_to_mat(d, errctr)
        print 'Saved to %s.' % filename
        break
        errctr += 1
        if errctr > 10:
            break

raise RuntimeError


for loopctr in range(30):
    d = f.snapshots.hmc_dv_out_ss.read(circular_capture=True,
                                       man_trig=True, man_valid=False)['data']
    # for ctr in range(len(d['dv'])):
    #     print '%05i' % ctr,
    #     print 'dv(%i)' % d['dv'][ctr],
    #     print 'tag(%i)' % d['tag'][ctr],
    #     print 'sync(%i)' % d['sync'][ctr],
    #     print ''
    dvs = []
    for dv in d['dv128']:
        dvs.extend(decode(dv, 128))
    datadict = {
        'simin_dv': {
            'time': [], 'signals': {
                'dimensions': 1,
                'values': np.array(dvs, dtype=np.uint32)
            }
        }
    }
    datadict['simin_dv']['signals']['values'].shape = (len(dvs), 1)
    filename = '/tmp/hmc_dv_out%03i.mat' % loopctr
    sio.savemat(filename, datadict)
    print '%i. %s was %i points long.' % (loopctr, filename, len(dvs))

raise RuntimeError


d = f.snapshots.ct_dv_out_ss.read(circular_capture=True,
                                  man_trig=True)['data']
dvs = []
for dv in d['dv128']:
    dvs.extend(decode(dv, 128))
rising_edge = -1
problem_location = -1
for ctr in range(1, len(dvs)):
    dv_prev = dvs[ctr - 1]
    dv = dvs[ctr]
    # print dv,
    if dv == 1 and dv_prev == 0:
        rising_edge = ctr
    if dv == 0 and dv_prev == 1:
        diff = ctr - rising_edge
        if diff != 32 and ctr > 1000:
            problem_location = ctr
            break

if problem_location > -1:
    print problem_location
    start = max(0, problem_location - 200)
    end = min(problem_location + 200, len(dvs))
    print start
    print end
    print dvs[start:end]


raise RuntimeError


for loopctr in range(30):
    # d = f.snapshots.ct_dv_in_ss.read(circular_capture=True,
    #                                  man_trig=True)['data']
    d = f.snapshots.ct_dv_out_ss.read(circular_capture=True,
                                      man_trig=True)['data']
    dvs = []
    # for dv in d['dv128']:
    #     dvs.extend(decode(dv, 128))
    for dv in d['dv32']:
        dvs.extend(decode(dv, 32))
    datadict = {
        'simin_dv': {
            'time': [], 'signals': {
                'dimensions': 1,
                'values': np.array(dvs, dtype=np.uint32)
            }
        }
    }
    datadict['simin_dv']['signals']['values'].shape = (len(dvs), 1)
    filename = '/tmp/ct_out%03i.mat' % loopctr
    sio.savemat(filename, datadict)
    print loopctr

# import IPython
# IPython.embed()

# end
