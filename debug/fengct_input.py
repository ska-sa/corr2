import feng_utils
import time
import numpy as np
import scipy.io as sio

hosts = feng_utils.setup_fhosts()
# feng_utils.ct_tvg(hosts, 1)

while True:
    feng_utils.print_err_regs(hosts)
    break
    time.sleep(1)

#
#
# d = f.snapshots.ct_dv_in_ss.read(circular_capture=True,
#                                  man_trig=True)['data']
# dvs = []
# for dv in d['dv32']:
#     dvs.extend(decode(dv, 32))
# rising_edge = -1
# problem_location = -1
# for ctr in range(1, len(dvs)):
#     dv_prev = dvs[ctr - 1]
#     dv = dvs[ctr]
#     # print dv,
#     if dv == 1 and dv_prev == 0:
#         rising_edge = ctr
#     if dv == 0 and dv_prev == 1:
#         diff = ctr - rising_edge
#         if diff != 512 and ctr > 1000:
#             problem_location = ctr
#             break
#
# if problem_location > -1:
#     print problem_location
#     start = max(0, problem_location - 1500)
#     end = min(problem_location + 1500, len(dvs))
#     print start
#     print end
#     print dvs[start:end]
#
# for host in ['skarab02030A-01', 'skarab02030B-01',
#              'skarab02030C-01', 'skarab02030E-01']:
#     f = casperfpga.CasperFpga(host)
#     f.get_system_information('/home/paulp/bofs/s_c856m4k_p_2017-8-8_0927.fpg')
#     print host, f.registers.qt_dv_err.read()['data'], f.registers.ct_dv_err.read()['data'], f.registers.pack_dv_err.read()['data'], f.registers.gbe0_txerrctr.read()['data']
#
# f = casperfpga.CasperFpga('skarab02030A-01')
# f.get_system_information('/home/paulp/bofs/s_c856m4k_p_2017-8-8_0927.fpg')
#
# import IPython
# IPython.embed()
#
# raise RuntimeError

# f = hosts[0]
# f.registers.ct_debug.write(in_stopmux=2)
# # d = f.snapshots.ct_dv_in_ss.read(man_trig=True)['data']
# d = f.snapshots.ct_dv256_in_ss.read(man_trig=True)['data']
# dvs = []
# for dv in d['dv32']:
#     dvs.extend(feng_utils.decode(dv, 32))
# zero_start = -1
# one_start = -1
# one_len = {}
# zero_len = {}
# for ctr in range(1, len(dvs)):
#     prtstr = '%5i: %i' % (ctr, dvs[ctr])
#     if dvs[ctr] == 1 and dvs[ctr-1] == 0:
#         zlen = ctr - zero_start
#         if zlen not in zero_len:
#             zero_len[zlen] = 0
#         zero_len[zlen] += 1
#         one_start = ctr
#         prtstr += ' %i' % zlen
#     elif dvs[ctr] == 0 and dvs[ctr-1] == 1:
#         olen = ctr - one_start
#         if olen not in one_len:
#             one_len[olen] = 0
#         one_len[olen] += 1
#         zero_start = ctr
#         prtstr += ' %i' % olen
#     # print(prtstr)
#
# print zero_len
# print one_len
#
# import IPython
# IPython.embed()

f = hosts[0]
loopctr = 0
try:
    while True:
        stime = time.time()
        print('Triggering snap%i at %.3f' % (loopctr, stime))
        d = f.snapshots.ct_dv_in_ss.read(circular_capture=True,
                                         man_trig=True)['data']
        dvs = []
        for dv in d['dv32']:
            dvs.extend(feng_utils.decode(dv, 32))
        # print len(dvs)
        # raise RuntimeError
        datadict = {
            'simin_dv': {
                'time': [], 'signals': {
                    'dimensions': 1,
                    'values': np.array(dvs, dtype=np.uint32)
                }
            }
        }
        datadict['simin_dv']['signals']['values'].shape = (len(dvs), 1)
        filename = '/tmp/ct_in%03i.mat' % loopctr
        sio.savemat(filename, datadict)
        print('\twaited %.3f seconds and saved: %s ' % (
            (time.time() - stime), filename))
        loopctr += 1
        if loopctr == 100:
            raise KeyboardInterrupt
except KeyboardInterrupt:
    print('Saved %i files in /tmp/' % loopctr)

# import IPython
# IPython.embed()

# end
