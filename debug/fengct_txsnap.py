import casperfpga
import time

hosts = []
for host in ['skarab02030A-01', 'skarab02030B-01',
             'skarab02030C-01', 'skarab02030E-01']:
    f = casperfpga.CasperFpga(host)
    f.get_system_information(FPG)
    hosts.append(f)

for f in hosts:
    f.registers.ct_control0.write(tvg_en2=1, tvg_en=1)

raise RuntimeError

ctr = 0
while True:
    try:
        for f in hosts:
            print f.host, 'QT: %s' % f.registers.qt_dv_err.read()['data'], \
                'CT: %s' % f.registers.ct_dv_err.read()['data'], \
                'PACK: %s' % f.registers.pack_dv_err.read()['data'], \
                'GBE: %s' % f.registers.gbe0_txerrctr.read()['data']
        print '%06i' % ctr
        ctr += 1
        time.sleep(1)
    except KeyboardInterrupt:
        break

raise RuntimeError

f = casperfpga.CasperFpga('skarab02030A-01')
# f = casperfpga.CasperFpga('skarab020304-01')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_2017-7-25_1906.fpg')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_2017-7-26_1637.fpg')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_2017-7-27_1442.fpg')

# f.get_system_information('/home/paulp/bofs/feng_ct_2017-7-30_1025.fpg')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_p_2017-7-30_1026.fpg')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_p_2017-7-31_1252.fpg')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_p_2017-7-31_1743.fpg')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_p_2017-8-2_1029.fpg')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_p_2017-8-2_1442.fpg')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_2017-8-4_1926.fpg')
f.get_system_information(FPG)

# print f.registers.pack_dv_err.read()
# time.sleep(1)
# print f.registers.pack_dv_err.read()
# time.sleep(1)
# print f.registers.pack_dv_err.read()
# time.sleep(1)
# print f.registers.pack_dv_err.read()


# def getdata(d=None, verbose=True):
#     d = d or f.snapshots.gbe_in_misc_ss.read(man_trig=True,
#                                              man_valid=True)['data']
#     data_len = len(d[d.keys()[0]])
#     pktlens = {}
#     errors = 0
#     dvstart = -1
#     pkts = 0
#     for ctr in range(1, data_len):
#         lastdv = d['valid_raw'][ctr-1]
#         dv = d['valid_raw'][ctr]
#         if dv == 1 and lastdv == 0:
#             dvstart = ctr
#         elif dv == 0 and lastdv == 1:
#             pktlen = ctr - dvstart
#             if pktlen not in pktlens:
#                 pktlens[pktlen] = 0
#             pktlens[pktlen] += 1
#             if pktlen != 35 and dvstart != -1:
#                 errors += 1
#             pkts += 1
#     if errors > 0:
#         return d, pktlens, pkts
#     return None, None, pkts
#
# import sys
# while True:
#     d, pktlens, numpkts = getdata()
#     print numpkts,
#     sys.stdout.flush()
#     if d:
#         print pktlens
#         break
#
# raise RuntimeError

# def checkoutputs(data=None, verbose=True):
#     d = data or \
#         f.snapshots.output_ss.read(man_trig=True, man_valid=True)['data']
#     startctr = 0
#     for ctr in range(1, len(d['dv'])):
#         if d['pkt_start'][ctr]:
#             break
#         startctr += 1
#     pktlens = {}
#     pktstarts = {}
#     errs = []
#     pktlen_errs = []
#     last_pkt_start = startctr - 64
#     dv_start = 0
#     for ctr in range(startctr, len(d['dv'])):
#         if verbose:
#             print '%5i' % ctr,
#             for k in ['trig', 'pkt_start', 'dv', 'd0_0']:
#                 print '%s(%i)' % (k, d[k][ctr]),
#         if d['pkt_start'][ctr]:
#             diff = ctr - last_pkt_start
#             if verbose:
#                 print 'PKTSTART(%i)' % diff,
#             if diff not in pktstarts:
#                 pktstarts[diff] = 0
#                 pktstarts[diff] += 1
#             if diff < 64:
#                 errs.append(ctr)
#             last_pkt_start = ctr
#
#         if (d['dv'][ctr] == 1) and (d['dv'][ctr - 1] == 0):
#             # rising edge
#             dv_start = ctr
#         if (d['dv'][ctr] == 0) and (d['dv'][ctr-1] == 1):
#             # falling edge
#             pktlen = ctr - dv_start
#             if pktlen not in pktlens:
#                 pktlens[pktlen] = 0
#             pktlens[pktlen] += 1
#             if pktlen != 32:
#                 pktlen_errs.append(ctr)
#             if verbose:
#                 print 'PKT(%i)' % pktlen,
#         if verbose:
#             print ''
#     if verbose:
#         print pktlens
#         print pktstarts
#         print errs
#         print pktlen_errs
#     for k in pktlens:
#         if k != 32:
#             return False, d
#     return True, d
#
# import sys
# while True:
#     print '.',
#     sys.stdout.flush()
#     res, data = checkoutputs(None, False)
#     if not res:
#         checkoutputs(data, True)
#         break
#
# raise RuntimeError


# d = f.snapshots.obuf_probs_ss.read(circular_capture=True,
#                                    man_trig=True, man_valid=True)['data']
# in_tag = []
# in_dv = []
# for ctr in range(6, len(d['rd_en'])):
#     in_dv.append(d['wr_en'][ctr-6])
#     tag = d['wr_addr'][ctr-6] & 511
#     in_tag.append(tag)
#
# import scipy.io as sio
# import numpy as np
# datadict = {
#     'simin_tag': {
#         'time': [], 'signals': {
#             'dimensions': 1,
#             'values': np.array(in_tag, dtype=np.uint32)
#         }
#     },
#     'simin_dv': {
#         'time': [], 'signals': {
#             'dimensions': 1,
#             'values': np.array(in_dv, dtype=np.uint32)
#         }
#     }
# }
# datadict['simin_tag']['signals']['values'].shape = (len(in_tag), 1)
# datadict['simin_dv']['signals']['values'].shape = (len(in_dv), 1)
# filename = '/tmp/obuf_inputs.mat'
# sio.savemat(filename, datadict)
#
# raise RuntimeError

# addr_errs = []
# d = f.snapshots.obuf_probs_ss.read(man_trig=True, man_valid=True)['data']
# for ctr in range(len(d['rd_en'])):
#     # if d['wr_en'][ctr] == 0:
#     #     continue
#     print ctr,
#     wr_addr_shift = d['wr_addr'][ctr] >> 3
#     print '   |   WR(%1i, %04i, %03i)' % (
#         d['wr_en'][ctr], d['wr_addr'][ctr], wr_addr_shift),
#     print '   |   RD(%1i, %04i)' % (d['rd_en'][ctr], d['rd_addr'][ctr]),
#     rd_bank = d['rd_addr'][ctr] >> 5
#     wr_bank = d['wr_addr'][ctr] >> 8
#     print '   |   BANKS(%i,%i)' % (wr_bank, rd_bank),
#     if d['addr_err'][ctr]:
#         print 'ADDR_ERR',
#         addr_errs.append(ctr)
#     print ''
#     if d['addr_err'][ctr]:
#         break
# print addr_errs
#
# import IPython
# IPython.embed()
#
# raise RuntimeError

f.registers.x_setup.write(snap_arm=False)

circ = True
man_valid = True

f.snapshots.gbe_in_msb_ss.arm(man_valid=man_valid, circular_capture=circ)
f.snapshots.gbe_in_lsb_ss.arm(man_valid=man_valid, circular_capture=circ)
f.snapshots.gbe_in_misc_ss.arm(man_valid=man_valid, circular_capture=circ)

f.registers.x_setup.write(snap_arm=True)

d0 = f.snapshots.gbe_in_msb_ss.read(arm=False)['data']
d1 = f.snapshots.gbe_in_lsb_ss.read(arm=False)['data']
d2 = f.snapshots.gbe_in_misc_ss.read(arm=False)['data']

f.registers.x_setup.write(snap_arm=False)

d = []
for ctr in range(len(d0['d_msb'])):
    if d2['valid_raw'][ctr]:
        d.append(d0['d_msb'][ctr] >> 64)
        d.append(d0['d_msb'][ctr] & (2**64-1))
        d.append(d1['d_lsb'][ctr] >> 64)
        d.append(d1['d_lsb'][ctr] & (2 ** 64 - 1))

dv_prev = d2['valid_raw'][0]
zeros = {}
ones = {}
eofs = {}
eofs_dv = {}
gbe_errors = []
prev_ctr = 0
prev_eof = 0
eof_dv_ctr = 0
for ctr in range(1, len(d0['d_msb'])):
    dv = d2['valid_raw'][ctr]

    if dv:
        eof_dv_ctr += 1
    dvstr = ''
    if dv != dv_prev:
        diff = ctr - prev_ctr
        if dv:
            collection = zeros
        else:
            collection = ones
        if diff not in collection:
            collection[diff] = 0
        collection[diff] += 1
        prev_ctr = ctr
        dvstr = 'DV_CHANGE(%i)' % diff
    dv_prev = dv
    eofstr = ''
    if d2['eof'][ctr]:
        diff = ctr - prev_eof
        if diff not in eofs:
            eofs[diff] = 0
        eofs[diff] += 1
        if eof_dv_ctr not in eofs_dv:
            eofs_dv[eof_dv_ctr] = 0
        eofs_dv[eof_dv_ctr] += 1
        prev_eof = ctr
        eofstr = 'EOF(%i,%i)' % (diff, eof_dv_ctr)
        eof_dv_ctr = 0

    print '%5i' % ctr, '0x%032x' % d0['d_msb'][ctr], \
        '0x%032x' % d1['d_lsb'][ctr],

    for k in d2.keys():
        print '%s(%i)' % (k, d2[k][ctr]),

    if d2['gbe_err'][ctr] or d2['gbe_full'][ctr] or d2['gbe_of'][ctr]:
        print 'GBE_ERROR',
        gbe_errors.append(ctr)

    print eofstr


print gbe_errors

print 'ones:', ones
print 'zeros:', zeros
print 'eofs:', eofs
print 'eofs_dv:', eofs_dv

for host in ['skarab02030A-01', 'skarab02030B-01',
             'skarab02030C-01', 'skarab02030E-01']:
    f = casperfpga.CasperFpga(host)
    f.get_system_information('/home/paulp/bofs/s_c856m4k_p_2017-8-8_0927.fpg')
    print host, f.registers.qt_dv_err.read()['data'], f.registers.ct_dv_err.read()['data'], f.registers.pack_dv_err.read()['data'], f.registers.gbe0_txerrctr.read()['data']


# d = f.snapshots.flow_ss.read(man_valid=True)['data']
# # CT
# dv_prev = d['ct_dv'][0]
# zeros = {}
# ones = {}
# prev_ctr = 0
# pkt_start_errors = 0
# for ctr in range(1, len(d['ct_sync'])):
#     dv = d['ct_dv'][ctr]
#     dvstr = ''
#     if dv != dv_prev:
#         diff = ctr - prev_ctr
#         if dv:
#             collection = zeros
#         else:
#             collection = ones
#         if diff not in collection:
#             collection[diff] = 0
#         collection[diff] += 1
#         prev_ctr = ctr
#         dvstr = 'DV_CHANGE(%i)' % diff
#         if (dv == 1) and (d['ct_pktstart'][ctr-1] != 1):
#             pkt_start_errors += 1
#             dvstr += ' PKT_START_ERROR'
#     dv_prev = dv
#     print '%05i' % ctr,
#     for key in ['ct_sync', 'ct_dv', 'ct_pktstart']:
#         print '%s(%i)\t' % (key, d[key][ctr]),
#     print dvstr
# print 'ones:', ones
# print 'zeros:', zeros
# print 'pkt_start_errors', pkt_start_errors
#
#
# def andrew_data():
#     import scipy.io as sio
#     import numpy as np
#     d = f.snapshots.flow_ss.read(man_valid=True)['data']
#     datadict = {
#         'simin_dv': {
#             'time': [], 'signals': {
#                 'dimensions': 1,
#                 'values': np.array(d['ct_dv'], dtype=np.uint32)
#             }
#         },
#         'simin_sync': {
#             'time': [], 'signals': {
#                 'dimensions': 1,
#                 'values': np.array(d['ct_sync'], dtype=np.uint32)
#             }
#         },
#         'simin_pktstart': {
#             'time': [], 'signals': {
#                 'dimensions': 1,
#                 'values': np.array(d['ct_pktstart'], dtype=np.uint32)
#             }
#         }
#     }
#     datadict['simin_dv']['signals']['values'].shape = (len(d['ct_dv']), 1)
#     datadict['simin_sync']['signals']['values'].shape = (len(d['ct_sync']), 1)
#     datadict['simin_pktstart']['signals']['values'].shape = (len(d['ct_pktstart']), 1)
#     filename = '/tmp/andy_sim_ct_output32.mat'
#     sio.savemat(filename, datadict)

# # GAP
# dv_prev = d['gap_dv'][0]
# zeros = {}
# ones = {}
# prev_ctr = 0
# for ctr in range(1, len(d['gap_sync'])):
#     dv = d['gap_dv'][ctr]
#     dvstr = ''
#     if dv != dv_prev:
#         diff = ctr - prev_ctr
#         if dv:
#             collection = zeros
#         else:
#             collection = ones
#         if diff not in collection:
#             collection[diff] = 0
#         collection[diff] += 1
#         prev_ctr = ctr
#         dvstr = 'DV_CHANGE(%i)' % diff
#     dv_prev = dv
#     print ctr,
#     for key in ['gap_sync', 'gap_dv']:
#         print '%s(%i)\t' % (key, d[key][ctr]),
#     print dvstr
# print 'ones:', ones
# print 'zeros:', zeros

# # TIME
# dv_prev = d['time_dv'][0]
# zeros = {}
# ones = {}
# prev_ctr = 0
# for ctr in range(1, len(d['time_sync'])):
#     dv = d['time_dv'][ctr]
#     dvstr = ''
#     if dv != dv_prev:
#         diff = ctr - prev_ctr
#         if dv:
#             collection = zeros
#         else:
#             collection = ones
#         if diff not in collection:
#             collection[diff] = 0
#         collection[diff] += 1
#         prev_ctr = ctr
#         dvstr = 'DV_CHANGE(%i)' % diff
#
#         if diff < 20 and ctr > 100:
#             break
#
#     dv_prev = dv
#     print ctr,
#     for key in ['time_sync', 'time_dv']:
#         print '%s(%i)\t' % (key, d[key][ctr]),
#     print dvstr
# print 'ones:', ones
# print 'zeros:', zeros

# import IPython
# IPython.embed()

# end
