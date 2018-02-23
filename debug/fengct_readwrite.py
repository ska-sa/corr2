# class BitDict(dict):
#     def __getattr__(self, item):
#         print(item)
#         if item == '__dict__':
#             return self.__dict__
#         return self.__dict__[item]
#
# b = BitDict()
# import IPython
# IPython.embed()
# raise RuntimeError

import IPython
import time

import feng_utils

# hosts = feng_utils.setup_xhosts()
#
# IPython.embed()
# raise RuntimeError

hosts = feng_utils.setup_fhosts()
feng_utils.ct_tvg(hosts, 1)

# feng_utils.reset_counters(hosts)
# raise RuntimeError

# check the error registers
while True:
    try:
        feng_utils.print_err_regs(hosts)
        time.sleep(1)
    except KeyboardInterrupt:
        print('')
        break

# read the snap
man_trig = False
man_valid = True
circular_capture = False
f = hosts[feng_utils.HOST_UUT]

f.registers.ct_debug.write(snap_wesel=1, snap_trigsel=1, snap_trig=0)
f.snapshots['hmc_readwrite0_ss'].arm(man_valid=True, circular_capture=False)
f.registers.ct_debug.write(snap_trig='pulse')
d = f.snapshots['hmc_readwrite0_ss'].read(arm=False, timeout=15)['data']
snaplen = len(d[d.keys()[0]])
anyerrors = 0
for ctr in range(snaplen):
    prtstr = '%5i' % ctr

    prtstr += ' WR_SYNC' if d['wr_sync'][ctr] else '        '
    prtstr += ' WR_EN0' if d['wr_en'][ctr] else '       '
    prtstr += ' WR_EN1' if d['wr_en1'][ctr] else '       '
    prtstr += ' WR_D0,4[%6i,%6i]' % (d['wr_d0'][ctr], d['wr_d4'][ctr])
    prtstr += ' WR_ADDR[%6i]' % d['wr_addr_raw'][ctr]
    # prtstr += ',%6i]' % d['wr_addr'][ctr]

    prtstr += '  |||  '

    prtstr += ' RD_ARM' if d['rd_arm'][ctr] else '       '
    prtstr += ' RD_EN0' if d['rd_en'][ctr] else '       '
    prtstr += ' RD_EN1' if d['rd_en1'][ctr] else '       '
    prtstr += ' RD_ADDR[%3i,%6i]' % (d['rd_tag'][ctr], d['rd_addr_raw'][ctr])
    # prtstr += ',%6i]' % d['rd_addr'][ctr]

    errors = 0
    for k in ['bank_err', 'sync_err0', 'sync_err1',
              'bank_err1', 'sync_err01', 'sync_err11']:
        if d[k][ctr]:
            errors += 1
    if errors > 0:
        prtstr += ' ERROR'
        anyerrors += errors

    errors = 0
    for k in ['wr_rdy', 'rd_rdy', 'wr_rdy1', 'rd_rdy1']:
        if d[k][ctr] == 0:
            errors += 1
    if errors > 0:
        prtstr += ' RDY_ERROR'
        anyerrors += errors
    # for k in d:
    #     prtstr += ' %s[%4i]' % (k, d[k][ctr])
    print(prtstr)

print(anyerrors)
if anyerrors > 0:
    raise RuntimeError('ERRORS!')

d = f.snapshots['hmc_readwrite1_ss'].read(arm=False, timeout=15)['data']

d = f.snapshots['hmc_readwrite1_ss'].read(man_trig=True, man_valid=True,
                                          timeout=15)['data']

snaplen = len(d[d.keys()[0]])
anyerrors = 0
syncat = -1
for ctr in range(snaplen):
    prtstr = '%5i' % ctr

    # [post_ok init_done d0 dv0 tag0 d1 dv1 tag1 sync_in]
    errors = 0
    for k in ['post_ok', 'init_done']:
        if d[k][ctr] == 0:
            errors += 1
    if errors > 0:
        prtstr += ' HMC_ERROR'
        anyerrors += errors

    if d['sync_in'][ctr]:
        prtstr += ' SYNC'
        syncat = ctr
    else:
        prtstr += '     '

    if d['dv1'][ctr] and d['dv0'][ctr]:
        raise RuntimeError('DV CLASH?!')

    prtstr += ' HMC0['
    prtstr += 'EN' if d['dv0'][ctr] else '  '
    prtstr += '%6i,%4i]' % (d['d0'][ctr], d['tag0'][ctr])

    prtstr += ' HMC1['
    prtstr += 'EN' if d['dv1'][ctr] else '  '
    prtstr += '%6i,%4i]' % (d['d1'][ctr], d['tag1'][ctr])

    # for k in d:
    #     prtstr += ' %s[%4i]' % (k, d[k][ctr])
    print(prtstr)

print anyerrors
print syncat
raise RuntimeError

IPython.embed()

for ctr in range(100):
    d = f.snapshots['hmc_readwrite1_ss'].read(man_trig=True,
                                              man_valid=True,
                                              timeout=120)['data']
    filename = '/tmp/hmc_output_new2_%03i.mat' % ctr
    feng_utils.save_to_mat(
        d, filename)
    print('Saved %s' % filename)

raise RuntimeError

# target = []
# snaplen = len(d[d.keys()[0]])
# for ctr in range(snaplen):
#     prtstr = '%5i' % ctr
#     for hmcctr in range(2):
#         prtstr += ' || '
#         if d['dv%i' % hmcctr][ctr]:
#             prtstr += 'DV '
#             prtstr += '(%3i, %5i)' % (d['tag%i' % hmcctr][ctr], d['d%i' % hmcctr][ctr])
#         else:
#             prtstr += '               '
#     prtstr += ' || '
#     if d['sync_in'][ctr]:
#         prtstr += 'SYNC '
#     else:
#         prtstr += '     '
#     if (not d['init_done'][ctr]) or (not d['post_ok'][ctr]):
#         prtstr += 'HMC_ERROR(%i,%i)' % (d['init_done'][ctr], d['post_ok'][ctr])
#     # for k in d:
#     #     prtstr += ' %s[%4i]' % (k, d[k][ctr])
#     if (d['tag0'][ctr] == 0 or d['tag1'][ctr] == 0 or
#             d['tag0'][ctr] == 256 or d['tag1'][ctr] == 256) and \
#             (d['dv0'][ctr] == 1 or d['dv1'][ctr] == 1):
#         prtstr += ' PKT_START'
#     print(prtstr)
#     if d['d0'][ctr] == feng_utils.PROBLEM_FREQ:
#         target.append(ctr)
# print(target)
# IPython.embed()
# raise RuntimeError


def make_interleaved_freqs():
    numfreqs = 4096
    numfreqs = 32768
    parallel_freqs = 8
    numx = 16
    xperboard = 4
    numboards = numx / xperboard
    freqperboard = numfreqs / numboards
    freqperx = numfreqs / numx
    interleaved_freqs = []
    for loopctr in range((numfreqs / parallel_freqs) / numx):
        base = loopctr * parallel_freqs
        for xctr in range(numx / xperboard):
            for boardid in range(numboards):
                freq = (xctr * freqperx) + (freqperboard * boardid) + base
                interleaved_freqs.append(freq)
    return interleaved_freqs


def save_hmc_out(suffix):
    """
    :return:
    """
    d = {}
    f.registers.ct_debug.write(snap_trig=False)
    snaprange = [0, 1, 2]
    for ctr in snaprange:
        f.snapshots['hmc_readwrite%1i_ss' % ctr].arm(
            man_trig=False, man_valid=True)
    f.snapshots['hmc_readwrite3_ss'].arm(man_trig=False, man_valid=True,
                                         offset=524288 * 1)
    f.snapshots['hmc_readwrite4_ss'].arm(man_trig=False, man_valid=True,
                                         offset=524288 * 2)
    f.snapshots['hmc_readwrite5_ss'].arm(man_trig=False, man_valid=True,
                                         offset=524288 * 3)
    f.snapshots['hmc_readwrite6_ss'].arm(man_trig=False, man_valid=True,
                                         offset=524288 * 4)
    f.registers.ct_debug.write(snap_trig='pulse')
    for ctr in snaprange:
        d[ctr] = f.snapshots['hmc_readwrite%1i_ss' % ctr].read(
            arm=False)['data']
    for ctr in [3, 4, 5, 6]:
        d[ctr] = f.snapshots['hmc_readwrite%1i_ss' % ctr].read(
            arm=False)['data']
    for ctr in [3, 4, 5, 6]:
        for k in d[2]:
            d[2][k].extend(d[ctr][k])
    import numpy as np
    import scipy.io as sio
    datadict = {
        'simin_dv0': {'time': [], 'signals': {
            'dimensions': 1, 'values': np.array(d[2]['dv0'], dtype=np.uint32)}},
        'simin_d0': {'time': [], 'signals': {
            'dimensions': 1, 'values': np.array(d[2]['d0'], dtype=np.uint32)}},
        'simin_tag0': {'time': [], 'signals': {
            'dimensions': 1, 'values': np.array(d[2]['tag0'], dtype=np.uint32)}},
        'simin_dv1': {'time': [], 'signals': {
            'dimensions': 1, 'values': np.array(d[2]['dv1'], dtype=np.uint32)}},
        'simin_d1': {'time': [], 'signals': {
            'dimensions': 1, 'values': np.array(d[2]['d1'], dtype=np.uint32)}},
        'simin_tag1': {'time': [], 'signals': {
            'dimensions': 1, 'values': np.array(d[2]['tag1'], dtype=np.uint32)}},
    }
    datadict['simin_d0']['signals']['values'].shape = (len(d[2]['dv0']), 1)
    datadict['simin_dv0']['signals']['values'].shape = (len(d[2]['dv0']), 1)
    datadict['simin_tag0']['signals']['values'].shape = (len(d[2]['dv0']), 1)
    datadict['simin_d1']['signals']['values'].shape = (len(d[2]['dv0']), 1)
    datadict['simin_dv1']['signals']['values'].shape = (len(d[2]['dv0']), 1)
    datadict['simin_tag1']['signals']['values'].shape = (len(d[2]['dv0']), 1)
    filename = '/tmp/hmc_out_%05i.mat' % suffix
    sio.savemat(filename, datadict)
    print('Saved %s.' % filename)


def analyse_hmc_output():
    """
    Check the data coming out of the HMCs. Is the test data in the correct
    order and are all the tags coming out?
    :return:
    """
    d = f.snapshots['hmc_readwrite1_ss'].read(
        man_trig=True, man_valid=True, circular_capture=False)['data']
    # d = f.snapshots['hmc_readwrite1_ss'].read(arm=False)['data']
    # reassemable the data
    snaplen = len(d['d0'])
    values = []
    tags = []
    for ctr in range(snaplen):
        val = None
        en = 0
        if d['dv0'][ctr]:
            val = (d['d0'][ctr], d['tag0'][ctr])
            en = 1
        if d['dv1'][ctr]:
            val = (d['d1'][ctr], d['tag1'][ctr])
            en = 1
        if en:
            try:
                index = values.index(val[0])
            except ValueError:
                index = None
            if index is None:
                values.append(val[0])
                tags.append([val[1]])
            else:
                tags[index].append(val[1])
    values = values[2:-2]
    tags = tags[2:-2]
    errors = []
    for ctr, value in enumerate(values):
        sorttags = sorted(tags[ctr])
        if max(sorttags) > 300:
            if sorttags != range(256, 512):
                errors.append(value)
        else:
            if sorttags != range(256):
                errors.append(value)
    if len(errors) > 0:
        if len(errors) == 3:
            start_okay = errors[0] == values[0]
            middle_okay = (errors[1] == values[1]) or (errors[1] == values[-2])
            end_okay = errors[2] == values[-1]
            if not (start_okay and middle_okay and end_okay):
                print('Frequencies with missing tags in the wrong place.')
                print(errors)
                IPython.embed()
                raise RuntimeError
        elif len(errors) == 2:
            start_error = (errors[0] != values[0]) and (errors[0] != values[1])
            end_error = (errors[1] != values[-1])
            if start_error or end_error:
                print('Frequencies with missing tags in the wrong place.')
                print(errors)
                IPython.embed()
                raise RuntimeError
        elif len(errors) == 1:
            start_okay = (errors[0] == values[0]) or (errors[0] == values[1])
            end_okay = errors[0] == values[-1]
            if not (start_okay or end_okay):
                print('Frequencies with missing tags in the wrong place.')
                print(errors)
                IPython.embed()
                raise RuntimeError
        elif len(errors) > 3:
            print('Too many frequencies with missing tags.')
            print(errors)
            IPython.embed()
            raise RuntimeError
    interleaved_freqs = make_interleaved_freqs()
    interleaved_freqs.extend(make_interleaved_freqs())
    startpos = -1
    for ctr in range(len(interleaved_freqs)):
        if interleaved_freqs[ctr] == values[0]:
            startpos = ctr
            break
    if startpos == -1:
        print('Could not find freq %i in interleaved freqs' % values[0])
        print(values)
        IPython.embed()
        raise RuntimeError
    if interleaved_freqs[startpos:startpos + len(values)] != values:
        print('Freqs from HMC are not in the correct order.')
        print(values)
        print('')
        print(interleaved_freqs[startpos:startpos + len(values)])
        IPython.embed()
        raise RuntimeError
    print('%.5f - all freqs output by HMC okay.' % time.time())


while True:
    analyse_hmc_output()

raise RuntimeError


def hmc_out_circ():
    d = {}
    f.registers.ct_debug.write(snap_trig=False)
    f.snapshots['hmc_readwrite2_ss'].arm(
        man_trig=False, man_valid=True, circular_capture=True)
    # for ctr in [3, 4, 5, 6]:
    #     offset = (ctr - 2) * 524288
    #     f.snapshots['hmc_readwrite%i_ss' % ctr].arm(
    #         man_trig=False, man_valid=True, circular_capture=True,
    #         offset=offset)
    f.registers.ct_debug.write(snap_trig='pulse')
    d[2] = f.snapshots['hmc_readwrite2_ss'].read(arm=False)['data']
    # for ctr in [2, 3, 4, 5, 6]:
    #     d[ctr] = f.snapshots['hmc_readwrite%1i_ss' % ctr].read(
    #         arm=False)['data']
    # for ctr in [3, 4, 5, 6]:
    #     for k in d[2]:
    #         d[2][k].extend(d[ctr][k])
    snaplen = len(d[2]['post_ok'])
    # snaplen = 1000
    print('')
    for ctr in range(snaplen):
        prtstr = '%5i' % ctr
        status = d[2]['post_ok'][ctr] + d[2]['init_done'][ctr]
        prtstr += ' d0(%5i,%1i,%3i) d1(%5i,%1i,%3i)' % (
            d[2]['d0'][ctr], d[2]['dv0'][ctr], d[2]['tag0'][ctr],
            d[2]['d1'][ctr], d[2]['dv1'][ctr], d[2]['tag1'][ctr]
        )
        if status != 2:
            prtstr += ' STATUS_ERROR(%1i,%1i)' % (
                d[2]['post_ok'][ctr], d[2]['init_done'][ctr],
            )
        print(prtstr)


def hmc_readwrite_circ():
    f.registers.ct_debug.write(snap_trig=False)
    f.snapshots['hmc_readwrite0_ss'].arm(
        man_trig=False, man_valid=True, circular_capture=True)
    f.snapshots['hmc_readwrite2_ss'].arm(
        man_trig=False, man_valid=True, circular_capture=True)
    f.registers.ct_debug.write(snap_trig='pulse')
    d0 = f.snapshots['hmc_readwrite0_ss'].read(arm=False)['data']
    d2 = f.snapshots['hmc_readwrite2_ss'].read(arm=False)['data']
    snaplen = len(d0['wr_rdy'])
    # snaplen = 1000
    print('')
    sync_location = []
    for ctr in range(snaplen):
        prtstr = '%5i' % ctr
        status = d2['post_ok'][ctr] + d2['init_done'][ctr] + \
            d0['wr_rdy'][ctr] + d0['rd_rdy'][ctr] + \
            d0['wr_rdy1'][ctr] + d0['rd_rdy1'][ctr]
        # write
        if d0['wr_sync'][ctr] != 0:
            prtstr += ' SYNC'
            sync_location.append(ctr)
        prtstr += '       WRITE['
        prtstr += 'addr(%6i,%6i)' % (d0['wr_addr_raw'][ctr],
                                      d0['wr_addr'][ctr])
        prtstr += ' d(%4i,%4i)' % (d0['wr_d0'][ctr], d0['wr_d4'][ctr])
        # read
        prtstr += ']       READ['
        rd_tag = d0['rd_tag'][ctr]
        prtstr += 'addr(%6i,%6i) tag(%3i)' % (d0['rd_addr_raw'][ctr],
                                              d0['rd_addr'][ctr], rd_tag)
        prtstr += ']       '
        # two hmcs
        prtstr += 'HMC0(%s' % ('WR,' if d0['wr_en'][ctr] else '  ,')
        prtstr += '%s)' % ('RD' if d0['rd_en'][ctr] else '  ')
        prtstr += ' HMC1(%s' % ('WR,' if d0['wr_en1'][ctr] else '  ,')
        prtstr += '%s)' % ('RD' if d0['rd_en1'][ctr] else '  ')
        prtstr += ' |*| d0(%5i,%1i,%3i) d1(%5i,%1i,%3i)' % (
            d2['d0'][ctr], d2['dv0'][ctr], d2['tag0'][ctr],
            d2['d1'][ctr], d2['dv1'][ctr], d2['tag1'][ctr]
        )
        if status != 6:
            prtstr += ' STATUS_ERROR(%1i,%1i||%1i,%1i||%1i,%1i)' % (
                d2['post_ok'][ctr], d2['init_done'][ctr],
                d0['wr_rdy'][ctr], d0['rd_rdy'][ctr],
                d0['wr_rdy1'][ctr], d0['rd_rdy1'][ctr],
            )
        print(prtstr)


def get_snap_new(d=None, verbose=False, circ=circular_capture):
    """

    :param d:
    :param verbose:
    :param circ:
    :return:
    """
    if d is None:
        d = {}
        f.registers.ct_debug.write(snap_trig=False)
        snaprange = [0, 1]
        for ctr in snaprange:
            f.snapshots['hmc_readwrite%1i_ss' % ctr].arm(
                man_trig=False, man_valid=True)
        for ctr in [2, 3, 4, 5, 6]:
            offset = (ctr - 2) * 524288
            f.snapshots['hmc_readwrite%i_ss' % ctr].arm(
                man_trig=False, man_valid=True, offset=offset)
        f.registers.ct_debug.write(snap_trig='pulse')
        for ctr in snaprange:
            d[ctr] = f.snapshots['hmc_readwrite%1i_ss' % ctr].read(
                arm=False)['data']
        for ctr in [2, 3, 4, 5, 6]:
            d[ctr] = f.snapshots['hmc_readwrite%1i_ss' % ctr].read(
                arm=False)['data']
    snaplen = len(d[0]['wr_rdy'])
    # snaplen = 1000
    print('')
    for ctr in range(snaplen):
        prtstr = '%5i' % ctr
        status = d[2]['post_ok'][ctr] + d[2]['init_done'][ctr] + \
            d[0]['wr_rdy'][ctr] + d[0]['rd_rdy'][ctr] + \
            d[1]['wr_rdy'][ctr] + d[1]['rd_rdy'][ctr]
        for bank in range(2):
            b = d[bank]
            if b['wr_en'][ctr] == 1:
                prtstr += ' |*| EN '
            else:
                prtstr += ' |*|    '
            # write
            if b['wr_sync'][ctr] != 0:
                prtstr += ' SYNC'
            prtstr += ' addr(%6i,%6i)' % (b['wr_addr_raw'][ctr],
                                          b['wr_addr'][ctr])
            prtstr += ' d(%4i,%4i)' % (b['wr_d0'][ctr], b['wr_d4'][ctr])
            # read
            rd_tag = b['rd_tag'][ctr]
            if b['rd_en'][ctr] == 1:
                prtstr += ' | EN '
            else:
                prtstr += ' |    '
            prtstr += 'addr(%6i,%6i) tag(%3i)' % (b['rd_addr_raw'][ctr],
                                                  b['rd_addr'][ctr], rd_tag)
            # if (b['rd_arm'][ctr] == 0) or b['bank_err'][ctr] or \
            #         b['sync_err0'][ctr] or b['sync_err1'][ctr]:
            #     prtstr += ' ERROR(%1i,%1i,%1i,%1i)' % (
            #         b['rd_arm'][ctr], b['bank_err'][ctr], b['sync_err0'][ctr],
            #         b['sync_err1'][ctr])
        prtstr += ' |*| d0(%5i,%1i,%3i) d1(%5i,%1i,%3i)' % (
            d[2]['d0'][ctr], d[2]['dv0'][ctr], d[2]['tag0'][ctr],
            d[2]['d1'][ctr], d[2]['dv1'][ctr], d[2]['tag1'][ctr]
        )
        if status != 6:
            prtstr += ' STATUS_ERROR(%1i,%1i||%1i,%1i||%1i,%1i)' % (
                d[2]['post_ok'][ctr], d[2]['init_done'][ctr],
                d[0]['wr_rdy'][ctr], d[0]['rd_rdy'][ctr],
                d[1]['wr_rdy'][ctr], d[1]['rd_rdy'][ctr],
            )
        # prtstr += ' |*| d0(%4i) dv0(%1i) tag0(%3i)' % (
        #     d[2]['d0'], d[2]['dv0'], d[2]['tag0'])
        # prtstr += ' d1(%4i) dv1(%1i) tag1(%3i)' % (
        #     d[2]['d1'], d[2]['dv1'], d[2]['tag1'])
        if verbose:
            print(prtstr)

    return d, False

loopctr = 0
while True:
    print(loopctr, time.time())
    analyse_hmc_output()
    # time.sleep(0.5)
    loopctr += 1
    break
raise RuntimeError

# (data, errors) = get_snap_new()
# raise RuntimeError

for ctr in range(30):
    save_hmc_out(ctr)
raise RuntimeError


def get_snap(d=None, verbose=False, circ=circular_capture):
    if d is None:
        f.registers.ct_debug.write(snap_trig=False)
        if circ:
            f.registers.ct_debug.write(wrrd_stopmux=6)
        for ctr in [0, 1, 2]:
            f.snapshots['hmc_readwrite%i_ss' % ctr].arm(
                man_trig=man_trig, man_valid=man_valid,
                circular_capture=circ)
        f.registers.ct_debug.write(snap_trig='pulse')
        d = {}
        for ctr in [0, 1, 2]:
            d.update(
                f.snapshots['hmc_readwrite%i_ss' % ctr].read(arm=False)['data']
            )
    errors = {
        'read_write_sync': [],
        'rdy': [],
        'hmc_data': [],
        'data_in': [],
        'address_catch': [],
    }
    for ctr in range(len(d['d0'])):
        prtstr = '%5i' % ctr
        # write
        prtstr += ' | d(%5i)' % d['d0'][ctr]
        prtstr += ' en(%i) addr(%7i, %7i)' % (
            d['wr_en'][ctr], d['wr_addr_raw'][ctr], d['wr_addr'][ctr])
        # read
        prtstr += ' | en(%i) addr(%7i, %7i) tag(%3i) arm(%i)' % (
            d['rd_en'][ctr], d['rd_addr_raw'][ctr], d['rd_addr'][ctr],
            d['rd_tag'][ctr], d['rd_arm'][ctr])
        # hmc status
        try:
            hmc_d0_3 = (d['hmc_d0_3_msb'][ctr] << 11) + d['hmc_d0_3_ls11'][ctr]
        except KeyError:
            hmc_d0_3 = (d['hmc_d0_3_ms4'][ctr] << 11) + d['hmc_d0_3_ls11'][ctr]
        prtstr += ' | d(%4i) tag_out(%3i) dv_out(%i) rdy(%i,%i) ' \
                  'init_post(%i,%i) ' \
                  'err(pktlen,dvblk,wrd_rep,wrd_d4z:%i,%i,%i,%i)' % (
                    d['hmc_d0_0'][ctr], d['hmc_tag'][ctr], d['hmc_dv'][ctr],
                    d['wr_rdy'][ctr], d['rd_rdy'][ctr], d['init_done'][ctr],
                    d['post_okay'][ctr], d['err_pktlen'][ctr],
                    d['err_dvblock'][ctr],
                    d['err_wrdata_repeat'][ctr], d['err_wrdata_d4zero'][ctr])
        # data in error
        if ((d['d1'][ctr] != d['d0'][ctr] + 1) or
                (d['d4'][ctr] != d['d1'][ctr] + 3)) and d['wr_en'][ctr]:
            errors['data_in'].append(ctr)
            prtstr += ' DATA_IN_ERROR(%4i, %4i, %4i)' % (
                d['d0'][ctr], d['d1'][ctr], d['d4'][ctr])
        # hmc_data_out_error
        if ((d['hmc_d0_1'][ctr] != d['hmc_d0_0'][ctr] + 1) or
                (d['hmc_d0_2'][ctr] != d['hmc_d0_1'][ctr] + 1) or
                (hmc_d0_3 != d['hmc_d0_2'][ctr] + 1)) and d['hmc_dv'][ctr]:
            errors['hmc_data'].append(ctr)
            prtstr += ' HMC_OUT_DATA_ERROR(%4i, %4i, %4i, %4i)' % (
                    d['hmc_d0_0'][ctr], d['hmc_d0_1'][ctr], d['hmc_d0_2'][ctr],
                    hmc_d0_3)
        # sync error?
        if (d['rd_en'][ctr] and (not d['wr_en'][ctr])) or \
                ((not d['rd_en'][ctr]) and d['wr_en'][ctr]):
            errors['read_write_sync'].append(ctr)
            prtstr += ' SYNC_ERROR'
        # ready error?
        if (not d['rd_rdy'][ctr]) or (not d['wr_rdy'][ctr]):
            errors['rdy'].append(ctr)
            prtstr += ' RDY_ERROR'
        # catch the aligned zero address
        if (d['d0'][ctr] == 0) and (d['wr_addr_raw'][ctr] == 0):
            errors['address_catch'].append(ctr)
            prtstr += ' D0_ZERO'
        if d['rd_addr_raw'][ctr] == 1:
            errors['address_catch'].append(ctr)
            prtstr += ' RD_RAW_ONE'
        if (d['rd_en'][ctr] or d['wr_en'][ctr]) and verbose:
            print(prtstr)

    got_errors = False
    for k in errors:
        if verbose:
            print('%s: %s' % (k, errors[k]))
        if len(errors[k]) > 0:
            got_errors = True

    return d, got_errors


# data, errs = get_snap(None, True, False)
# raise RuntimeError

loopctr = 0
max_loops = 10
while True:
    print('%i %f' % (loopctr, time.time()))
    try:
        data, errs = get_snap(None, False, False)
    except KeyboardInterrupt:
        print('All done.')
        break
    feng_utils.save_to_mat(data, '/tmp/hmc_write_read_%03i.mat' % loopctr)
    if errs:
        get_snap(data, True)
        break
    loopctr += 1
    if max_loops != -1 and loopctr > max_loops:
        print('Max loops done.')
        break

# end
