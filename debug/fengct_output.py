import time
import feng_utils
import IPython

from casperfpga.network import Mac, IpAddress

hosts = feng_utils.setup_fhosts()
feng_utils.ct_tvg(hosts, 1)
# feng_utils.print_err_regs(hosts)
# feng_utils.bypass_cd(hosts, 1)

# feng_utils.reset_fhosts(hosts)

while True:
    try:
        feng_utils.print_err_regs(hosts)
        time.sleep(1)
    except KeyboardInterrupt:
        break

man_valid = True
circ = False

print('')
for h in hosts:
    print(h.host, h.registers.ct_control0.read()['data'])

for h in hosts:
    h.registers.ct_control0.write(obuf_read_gap=45)

# read the CT output
f = hosts[feng_utils.HOST_UUT]

f.registers.ct_debug.write(
    out_stopmux=1,
    # gbe_stopmux=5,
    snap_arm=0,
    snap_trig=0,
    snap_wesel=1,
    snap_trigsel=1,
)

# just print the contents of the snap block
man_valid = False
circ = True
for snapctr in range(3):
    f.snapshots['output%i_ss' % snapctr].arm(
        circular_capture=circ, man_trig=False, man_valid=man_valid)
f.registers.ct_debug.write(
    snap_wesel=1,
    snap_trigsel=1,
    snap_trig='pulse', )
d = {}
for snapctr in range(2):
    d.update(f.snapshots['output%i_ss' % snapctr].read(arm=False)['data'])

print len(d[d.keys()[0]])

# ctr = 0
# while d['dv'][ctr] == 1:
#     ctr += 1
# for k in d:
#     d[k] = d[k][ctr:]
errors = []
for ctr in range(0, len(d['dv'])):
    prtstr = '%5i ' % ctr
    for k in d:
        prtstr += ' %s(%i)' % (k, d[k][ctr])

    if d['dv'][ctr] and (
                (d['pkt_freq'][ctr] != d['d0_0'][ctr]) or
                (d['pkt_freq'][ctr] != d['d0_1'][ctr]) or
                (d['pkt_freq'][ctr] != d['d1_0'][ctr]) or
                (d['pkt_freq'][ctr] != d['d7_0'][ctr]) or
                (d['pkt_freq'][ctr] != d['d7_1'][ctr])):
        prtstr += ' ERROR'
        errors.append(ctr)

    if d['dv'][ctr] or d['sync'][ctr]:
        print(prtstr)
    else:
        print('%5i' % ctr)

print errors

raise RuntimeError



f.registers.ct_debug.write(snap_trig=0)
for snapctr in range(3):
    f.snapshots['gbe_in%i_ss' % snapctr].arm(
        man_trig=False, man_valid=True)
f.registers.ct_debug.write(snap_trig='pulse')
d = {}
for snapctr in range(3):
    d.update(f.snapshots['gbe_in%i_ss' % snapctr].read(arm=False)['data'])
d['d0'] = []
d['d1'] = []
d['d2'] = []
d['d3'] = []
for ctr in range(len(d['dv'])):
    d['d0'].append(d['d_msb'][ctr] >> 64)
    d['d1'].append(d['d_msb'][ctr] & ((2**64)-1))
    d['d2'].append(d['d_lsb'][ctr] >> 64)
    d['d3'].append(d['d_lsb'][ctr] & ((2**64)-1))
d['d_msb'] = None
d['d_lsb'] = None
for ctr in range(0, len(d['dv'])):
    prtstr = '%5i' % ctr
    prtstr += ' DV' if d['dv'][ctr] else '   '
    prtstr += ' EOF' if d['eof'][ctr] else '    '
    prtstr += ' OF' if d['of'][ctr] else '   '
    ip = IpAddress(d['ip'][ctr])
    prtstr += ' %s:%i' % (str(ip), d['port'][ctr])
    prtstr += ' %3i' % d['xindex'][ctr]
    prtstr += ' %4i' % (d['xindex'][ctr] * 256)
    prtstr += ' %4i' % (d['d0'][ctr] & ((2**16)-1))
    prtstr += ' %016x' % d['d0'][ctr]
    prtstr += ' %016x' % d['d1'][ctr]
    prtstr += ' %016x' % d['d2'][ctr]
    prtstr += ' %016x' % d['d3'][ctr]
    print(prtstr)
f.registers.ct_debug.write(snap_trig=1)
raise RuntimeError

# d = f.gbes.gbe0.read_txsnap()
# for ctr in range(1, len(d['valid'])):
#     prtstr = '%5i ' % ctr
#     for k in d:
#         if k == 'dv' or k == 'valid':
#             prtstr += ' DV' if d[k][ctr] else '   '
#         elif k == 'eof':
#             prtstr += ' EOF' if d[k][ctr] else '    '
#         elif k == 'tx_full':
#             prtstr += ' AFULL' if d[k][ctr] else '      '
#         elif k == 'tx_over':
#             prtstr += ' OF' if d[k][ctr] else '   '
#         elif k == 'data':
#             prtstr += ' %016x' % ((d[k][ctr] >> 192) & ((2**64)-1))
#             prtstr += ' %016x' % ((d[k][ctr] >> 128) & ((2**64)-1))
#             prtstr += ' %016x' % ((d[k][ctr] >> 64) & ((2**64)-1))
#             prtstr += ' %016x' % ((d[k][ctr] >> 0) & ((2**64)-1))
#         else:
#             prtstr += ' %s(%i)' % (k, d[k][ctr])
#     print(prtstr)


xhosts = feng_utils.setup_xhosts()
x = xhosts[0]

d = x.gbes.gbe0.read_rxsnap()
for ctr in range(1, len(d[d.keys()[0]])):
    prtstr = '%5i ' % ctr
    for k in d:
        if k == 'dv' or k == 'valid' or k == 'valid_in':
            prtstr += ' DV' if d[k][ctr] else '   '
        elif k == 'eof' or k == 'eof_in':
            prtstr += ' EOF' if d[k][ctr] else '    '
        elif k == 'tx_full':
            prtstr += ' AFULL' if d[k][ctr] else '      '
        elif k == 'tx_over' or k == 'overrun':
            prtstr += ' OF' if d[k][ctr] else '   '
        elif k == 'data':
            prtstr += ' %016x' % ((d[k][ctr] >> 192) & ((2**64)-1))
            prtstr += ' %016x' % ((d[k][ctr] >> 128) & ((2**64)-1))
            prtstr += ' %016x' % ((d[k][ctr] >> 64) & ((2**64)-1))
            prtstr += ' %016x' % ((d[k][ctr] >> 0) & ((2**64)-1))
        else:
            prtstr += ' %s(%i)' % (k, d[k][ctr])
    print(prtstr)

print x.snapshots
IPython.embed()


raise RuntimeError


# feng_utils.reset_fhosts(hosts)

# # just print the contents of the snap block
# man_valid = True
# fpga = f
# for snapctr in range(3):
#     f.snapshots['output%i_ss' % snapctr].arm(
#         circular_capture=circ, man_trig=False, man_valid=man_valid)
# f.registers.ct_debug.write(snap_arm=1, snap_trig='pulse', )
# d = {}
# for snapctr in range(3):
#     d.update(fpga.snapshots['output%i_ss' % snapctr].read(
#         arm=False)['data'])
# ctr = 0
# # import IPython
# # IPython.embed()
#
# while d['dv'][ctr] == 1:
#     ctr += 1
# for k in d:
#     d[k] = d[k][ctr:]
# for ctr in range(1, len(d['dv'])):
#     prtstr = '%5i ' % ctr
#     for k in d:
#         prtstr += ' %s(%i)' % (k, d[k][ctr])
#     print prtstr
#
#
# raise RuntimeError


# d = f.snapshots['output0_ss'].read(arm=False)['data']
# d.update(f.snapshots['output1_ss'].read(arm=False)['data'])
# d.update(f.snapshots['output2_ss'].read(arm=False)['data'])
# snaplen = len(d[d.keys()[0]])
# for ctr in range(snaplen):
#     prtstr = '%5i' % ctr
#     for k in d:
#         prtstr += ' %s[%4i]' % (k, d[k][ctr])
#     print(prtstr)
#     if d['dv'][ctr]:
#         if d['pkt_freq'][ctr] != d['d0_0'][ctr]:
#             break
# raise RuntimeError


def read_ct_output(fpga, data=None, verbose=False, verbose_limits=(-1, -1)):
    """
    Read the CT output snapshot
    :param fpga:
    :param data:
    :param verbose:
    :param verbose_limits:
    :return:
    """
    if data is None:
        for snapctr in range(3):
            f.snapshots['output%i_ss' % snapctr].arm(
                circular_capture=circ, man_trig=False, man_valid=man_valid)
        f.registers.ct_debug.write(snap_arm=1, snap_trig='pulse',)
        d = {}
        for snapctr in range(3):
            d.update(fpga.snapshots['output%i_ss' % snapctr].read(
                arm=False)['data'])
        ctr = 0
        while d['dv'][ctr] == 1:
            ctr += 1
        for k in d:
            d[k] = d[k][ctr:]
    else:
        d = data
    one_lens = {}
    zero_lens = {}
    last_rising = -1
    last_falling = -1
    errors = {
        'one_len': [],
        'data_freqid': [],
        'sync': [],
    }
    for ctr in range(1, len(d['dv'])):
        prtstr = '%5i dv(%i)' % (ctr, d['dv'][ctr])
        prtstr += ' pkt_start(%i) sync(%i)' % (
            d['pkt_start'][ctr], d['sync'][ctr])
        prtstr += ' pkt_freq(%i)' % d['pkt_freq'][ctr]
        pkt_ctr = (d['pkt_ctr_msb'][ctr] << 32) + d['pkt_ctr_lsb'][ctr]
        raw_freq = (pkt_ctr & 131071) >> 5
        interleaved_freq = calc_interleaved_freq(raw_freq)
        prtstr += ' pkt_ctr(%12i, %4i, %4i)' % (
            pkt_ctr, raw_freq, interleaved_freq)
        prtstr += ' d(%4i)' % d['d0_0'][ctr]

        def _data_error(compare):
            if d['d0_0'][ctr] != compare:
                return ' ERROR(%4i,%4i)' % (d['d0_0'][ctr], compare)
            return ''
        prtstr += _data_error(d['d0_1'][ctr])
        prtstr += _data_error(d['d1_0'][ctr])
        prtstr += _data_error(d['d7_0'][ctr])
        prtstr += _data_error(d['d7_1'][ctr])
        if d['pkt_start'][ctr]:
            prtstr += ' PKT_START'

        # # TODO - HACK - the counter is off by one packet!
        # # i.e. the sync is one whole packet too early!
        # pkt_cnt = d['pkt_ctr'][ctr] - 1
        # if pkt_cnt == -1:
        #     pkt_cnt = 4095
        # # /TODO

        # interleave it
        # prtstr += ' pkt_cnt(%i)' % pkt_cnt
        # prtstr += ' groupid(%i)' % ((pkt_cnt >> 7) & 0x1f)
        # prtstr += ' xeng(%i)' % ((pkt_cnt >> 3) & 0x0f)
        # prtstr += ' eighth(%i)' % (pkt_cnt & 0x07)
        # prtstr += ' interleaved(%i)' % interleaved_freq
        # if translated != d['d0_0'][ctr]:
        #     prtstr += ' DATA_FREQID_ERROR(%i,%i)' % (
        #         translated, d['d0_0'][ctr])
        #     errors['data_freqid'].append(ctr)
        if (d['dv'][ctr] == 1) and (d['dv'][ctr - 1] == 0):
            # rising edge
            zlen = ctr - last_falling
            if zlen not in zero_lens:
                zero_lens[zlen] = 0
            zero_lens[zlen] += 1
            prtstr += ' ZLEN(%i)' % zlen
            last_rising = ctr
        elif (d['dv'][ctr] == 0) and (d['dv'][ctr - 1] == 1):
            # falling edge
            olen = ctr - last_rising
            if olen not in one_lens:
                one_lens[olen] = 0
            one_lens[olen] += 1
            prtstr += ' OLEN(%i)' % olen
            if olen != 32:
                errors['one_len'].append(ctr)
            last_falling = ctr
        if (d['pkt_freq'][ctr] != d['d0_0'][ctr]) and (d['dv'][ctr]):
            errors['sync'].append(ctr)
            prtstr += ' SYNC(off %i)' % (d['pkt_freq'][ctr] - d['d0_0'][ctr])
        if verbose:
            if ((verbose_limits[0] == -1) or (ctr > verbose_limits[0])) and \
               ((verbose_limits[1] == -1) or (ctr < verbose_limits[1])):
                print(prtstr)
        # if d['pkt_start'][ctr - 1] == 1:
        #     print(prtstr)

    def limit100(lst):
        if len(lst) == 0:
            return lst
        return lst[0:min([100, len(lst)])]
    print('ONE_LENS: %s' % one_lens)
    print('ZERO_LENS: %s' % zero_lens)
    print('ONE_LEN_ERRORS: %s' % limit100(errors['one_len']))
    print('DATA_FREQ_ID_ERRORS: %s' % limit100(errors['data_freqid']))
    print('SYNC_ERRORS: %s' % limit100(errors['sync']))
    return d, errors


while True:
    data_output, errors = read_ct_output(f)
    got_error = False
    for k in errors:
        if len(errors[k]) > 0:
            got_error = True
            break

    got_error = True

    if got_error:
        # err_start = errors[0] - 100
        # err_end = err_start + 1000
        # a = read_ct_output(f, data, True, (err_start, err_end))
        a = read_ct_output(f, data_output, True)
        break

# for host in hosts:
#     a = read_ct_output(host, data_output, True)
#     print(host.host)
#     print(75 * '#')

raise RuntimeError


def print_rows(d, start=0, end=-1):
    if end == -1:
        end = len(d[d.keys()[0]])
    for ctr in range(start, end):
        prtstr = '%5i ' % ctr
        for k in d:
            prtstr += '%s(%s) ' % (k, str(d[k][ctr]))
        print(prtstr.strip())


def analyse_output_freqs():
    f.registers.ct_debug.write(snap_arm=0,)
    f.snapshots['output_ss'].arm(circular_capture=False, man_valid=False)
    f.snapshots['output1_ss'].arm(circular_capture=False, man_valid=False)
    f.registers.ct_debug.write(snap_arm=1, snap_trig='pulse',)
    d = f.snapshots['output_ss'].read(arm=False)['data']
    d2 = f.snapshots['output1_ss'].read(arm=False)['data']
    d['d7_1'] = d2['d7_1']
    d['pkt_ctr'] = d2['pkt_ctr']
    # chop off the first incomplete packet
    xeng0 = d['d0_0'][0] / 256
    ctr = 1
    while (d['d0_0'][ctr] / 256) == xeng0:
        ctr += 1
    data = {}
    for k in d:
        data[k] = d[k][ctr:]
    datalen = len(data['dv'])
    errors = {'data': [], 'xeng': [], 'pkt_ctr': []}
    prev_data = None
    prev_xeng = None
    prev_pkt_ctr = data['pkt_ctr'][0] - 1
    for xctr in range(0, len(data['dv'])-256, 32 * 8):
        xeng = data['d0_0'][xctr] / 256
        for pktctr in range(0, 8):
            pktidx = xctr + (pktctr * 32)
            try:
                pkt_d = data['d0_0'][pktidx]
            except IndexError:
                print xctr
                print pktidx
                print '*&^*&^*&^*&^'
                raise
            for pktcontentsctr in range(0, 32):
                idx = pktidx + pktcontentsctr
                if ((data['d0_1'][idx] != data['d0_0'][idx]) or
                        (data['d1_0'][idx] != data['d0_0'][idx]) or
                        (data['d1_1'][idx] != data['d0_0'][idx]) or
                        (data['d7_0'][idx] != data['d0_0'][idx]) or
                        (data['d7_1'][idx] != data['d0_0'][idx])):
                    errors['data'].append(ctr)
                if data['d0_1'][idx] != pkt_d:
                    errors['data'].append(idx)
                try:
                    this_xeng = data['d0_0'][idx] / 256
                except:
                    print xctr
                    print pktidx
                    print idx
                    print '*&^*&^*&^*&^'
                    raise
                if this_xeng != xeng:
                    # print_rows(d, idx-10, idx+10)
                    errors['xeng'].append(idx)
                if data['pkt_ctr'][idx] != prev_pkt_ctr + 1:
                    if (data['pkt_ctr'][idx] != 0) and (prev_pkt_ctr != 4095):
                        errors['pkt_ctr'].append(ctr)
            prev_pkt_ctr = data['pkt_ctr'][pktidx]
        if prev_xeng is not None:
            if xeng == 0:
                if prev_xeng != 15:
                    errors['xeng'].append(xctr)
            else:
                if xeng != prev_xeng + 1:
                    errors['xeng'].append(xctr)
        prev_xeng = xeng
    got_error = False
    for k in errors:
        if len(errors[k]) > 0:
            got_error = True
            break
    if got_error:
        print('data_errors: %s' % errors['data'])
        print('xeng_errors: %s' % errors['xeng'])
        print('pkt_ctr_errors: %s' % errors['pkt_ctr'])
    return d, got_error

loopctr = 0
while True:
    data, errors = analyse_output_freqs()
    if errors:
        print_rows(data)
        break
    loopctr += 1
    print(loopctr)


# # get a snapshot of the output
#
#
#
# f.registers.x_setup.write(snap_arm=False)
# f.registers.ct_debug.write(out_stopmux=2)
# f.snapshots.output_ss.arm(man_trig=True,
#                           man_valid=man_valid, circular_capture=circ)
# f.snapshots.output1_ss.arm(man_trig=True,
#                            man_valid=man_valid, circular_capture=circ)
# f.registers.x_setup.write(snap_arm=True)
# time.sleep(1)
# d = f.snapshots.output_ss.read(arm=False)['data']
# d.update(f.snapshots.output1_ss.read(arm=False)['data'])
# f.registers.x_setup.write(snap_arm=False)
# datalen = len(d['dv'])
# data_errors = []
# for ctr in range(datalen):
#     xeng = d['d0_0'][ctr] / 256
#     prtstr = '%5i' % ctr
#     prtstr += ' dv(%i)' % d['dv'][ctr]
#     prtstr += ' trig(%i)' % d['trig'][ctr]
#     prtstr += ' pkt_start(%i)' % d['pkt_start'][ctr]
#     prtstr += ' pkt_ctr(%i)' % d['pkt_ctr'][ctr]
#     prtstr += ' d0_0(%4i)' % d['d0_0'][ctr]
#     prtstr += ' xeng(%2i)' % xeng
#     if ((d['d0_1'][ctr] != d['d0_0'][ctr]) or
#             (d['d1_0'][ctr] != d['d0_0'][ctr]) or
#             (d['d1_1'][ctr] != d['d0_0'][ctr]) or
#             (d['d7_0'][ctr] != d['d0_0'][ctr]) or
#             (d['d7_1'][ctr] != d['d0_0'][ctr])):
#         prtstr += ' DATA_ERROR(%4i,%4i,%4i,%4i,%4i,%4i)' % (
#             d['d0_0'][ctr], d['d0_1'][ctr],
#             d['d1_0'][ctr], d['d1_1'][ctr],
#             d['d7_0'][ctr], d['d7_1'][ctr])
#         data_errors.append(ctr)
#     print(prtstr)
# print(len(data_errors) > 0)
#
# import numpy as np
# import time
# import scipy.io as sio
# datadict = {
#     'simin_dv': {
#         'time': [], 'signals': {
#             'dimensions': 1,
#             'values': np.array(d['dv'], dtype=np.uint32)
#         }
#     },
#     'simin_d0_0': {
#         'time': [], 'signals': {
#             'dimensions': 1,
#             'values': np.array(d['d0_0'], dtype=np.uint32)
#         }
#     }
# }
# datadict['simin_dv']['signals']['values'].shape = (len(d['dv']), 1)
# datadict['simin_d0_0']['signals']['values'].shape = (len(d['d0_0']), 1)
# filename = '/tmp/ct_out_dv_%i.mat' % time.time()
# sio.savemat(filename, datadict)

# end
