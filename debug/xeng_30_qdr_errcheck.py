import time
import casperfpga
from casperfpga import utils as fpgautils
import numpy.random as nprand

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

hosts = ['roach02081a', 'roach020712', 'roach020818', 'roach02064a']

xfs = []
errors_undetected = {}
undetected_writes = {}

for host in hosts:
    f = casperfpga.KatcpFpga(host)
    f.get_system_information()
    xfs.append(f)

f = xfs[0]

snapname = 'vaccsnap_0_ss'
snapname = 'snap_vacc_ss'

snap = f.snapshots[snapname]

f.registers.vacc_snap_ctrl.write(arm=0)
snap.arm(circular_capture=True, man_valid=False)
# f.snapshots.vaccsnap_1_ss.arm(circular_capture=True, man_valid=False)
f.registers.vacc_snap_ctrl.write(arm=1)

d = snap.read(arm=False)['data']
# d.update(f.snapshots.vaccsnap_1_ss.read(arm=False)['data'])

print(len(d[d.keys()[0]])

# d['dreal_acc'] = []
# d['dimage_acc'] = []
# d['dreal_qdr'] = []
# d['dimage_qdr'] = []
# for ctr in range(len(d[d.keys()[0]])):
#     _acc_data = (d['acc_data_ms60'][ctr] << 8) | d['acc_data_ls8'][ctr]
#     _dr = _acc_data & (2**32-1)
#     _di = (_acc_data >> 32) & (2**32-1)
#     d['dreal_acc'].append(_dr)
#     d['dimage_acc'].append(_di)
#     _dr = d['qdr_data'][ctr] & (2**32-1)
#     _di = (d['qdr_data'][ctr] >> 32) & (2**32-1)
#     d['dreal_qdr'].append(_dr)
#     d['dimage_qdr'].append(_di)
# d.pop('qdr_data')
# d.pop('acc_data_ms60')
# d.pop('acc_data_ls8')

key_order = ['new_acc', 'fifo_rd_en', 'qdr_data_ls10', 'qdr_wr_en', 'qdr_addr',
             'qdr_valid',  'blank', 'qdr_addr_del', 'burst_rdy', 'qdr_rd_en']

print('ctr\t',
for key in d.keys():
    print(key, '\t',
print(''
for ctr in range(len(d['new_acc'])):
    print(ctr,
    for key in d.keys():
        print(d[key][ctr], '\t',
    print(''

# import IPython
# IPython.embed()


# before_writing = THREADED_FPGA_OP(
#         xfs, timeout=5,
#         target_function=(lambda fpga_:
#                          fpga_.registers.control.write(cnt_rst='pulse'),))
#
# total_ctr = 0
#
# while True:
#
#     word_to_write = int(nprand.random() * (2**32))
#     word_to_write = int(nprand.random() * (2**16))
#
#     before_writing = [
#         THREADED_FPGA_OP(
#             xfs, timeout=5,
#             target_function=(lambda fpga_:
#                              fpga_.registers['vacc_errors%i' % qdrnum].read(),))
#         for qdrnum in range(0, 4)]
#
#     [THREADED_FPGA_OP(
#         xfs, timeout=5,
#         target_function=(lambda fpga_:
#                          fpga_.write_int('qdr%i_memory' % qdrnum, word_to_write,
#                                          blindwrite=True),))
#      for qdrnum in range(0, 4)]
#
#     time.sleep(1)
#
#     after_writing = [
#         THREADED_FPGA_OP(
#             xfs, timeout=5,
#             target_function=(lambda fpga_:
#                              fpga_.registers['vacc_errors%i' % qdrnum].read(),))
#         for qdrnum in range(0, 4)]
#
#     total_ctr += 1
#
#     for f in xfs:
#         print(f.host, ':'
#         for qdrnum in range(0, 4):
#             before = before_writing[qdrnum][f.host]['data']['parity']
#             after = after_writing[qdrnum][f.host]['data']['parity']
#             print('\t%i: %i > %i' % (qdrnum, before, after)
#             if before == after:
#                 errors_undetected[f.host][qdrnum] += 1
#                 _errnum = '0x%08x' % word_to_write
#                 if _errnum not in undetected_writes[f.host]:
#                     undetected_writes[f.host].append(_errnum)
#         print('undetected errors = %s / %i' % (errors_undetected[f.host],
#                                                total_ctr)
#         print('vals = %s' % undetected_writes[f.host]
