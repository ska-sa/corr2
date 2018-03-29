import IPython
import time
import feng_utils

hosts = feng_utils.setup_fhosts()
feng_utils.ct_tvg(hosts, 1)

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

# d = f.snapshots['obuf0_ss'].read(arm=False, timeout=15)['data']
# feng_utils.save_to_mat(d, 'obuf_in_65k.mat')
# print(d.keys())
# raise RuntimeError

f.registers.ct_debug.write(snap_wesel=1, snap_trigsel=1, snap_trig=0)
f.snapshots['obuf0_ss'].arm(man_valid=True, circular_capture=True)
f.snapshots['obuf1_ss'].arm(man_valid=True, circular_capture=True)
f.snapshots['obuf2_ss'].arm(man_valid=True, circular_capture=True)
f.snapshots['obuf3_ss'].arm(man_valid=True, circular_capture=True)
f.registers.ct_debug.write(snap_trig='pulse')
d = f.snapshots['obuf0_ss'].read(arm=False, timeout=15)['data']
d_wr = f.snapshots['obuf1_ss'].read(arm=False, timeout=15)['data']
d_rd = f.snapshots['obuf2_ss'].read(arm=False, timeout=15)['data']
d_rd.update(f.snapshots['obuf3_ss'].read(arm=False, timeout=15)['data'])
target = []
addr_clash = []
bank_clash = []
stopctr = None
snaplen = len(d[d.keys()[0]])
errors = []
for ctr in range(snaplen):
    prtstr = '%5i' % ctr

    prtstr += ' IN_SYNC' if d['in_sync'][ctr] else '        '
    prtstr += ' IN_DV' if d['in_dv'][ctr] else '      '
    if d['in_dv'][ctr]:
        prtstr += ' in_tag[%3i]' % d['in_tag'][ctr]
        prtstr += ' in_d0[%5i]' % d['in_d0'][ctr]
    else:
        prtstr += ' ' * 25

    prtstr += '  ||  '

    wr_bank = None
    if d['wr_en'][ctr]:
        prtstr += ' WR_EN'
        wr_addr8 = d['wr_addr'][ctr] >> 3
        wr_bank = wr_addr8 / 32
        prtstr += ' wr_addr[%4i,%3i,%i]' % (d['wr_addr'][ctr], wr_addr8, wr_bank)
        wrd0 = d_wr['wr_d0'][ctr]
        wr_d_error = False
        for wrctr in range(1, 8):
            if d_wr['wr_d%i' % wrctr][ctr] != wrd0 + wrctr:
                wr_d_error = True
        if wr_d_error and d['wr_en'][ctr]:
            prtstr += ' wr_d['
            for wrctr in range(8):
                prtstr += '%5i,' % d_wr['wr_d%1i' % wrctr][ctr]
            prtstr = prtstr[:-1]
            prtstr += ']'
        else:
            prtstr += ' wr_d[%5i]' % wrd0
    else:
        prtstr += ' ' * 38

    prtstr += '  ||  '
    rd_bank = None
    prtstr += ' RD_GO' if d['rd_go'][ctr] else '      '
    if d['rd_en'][ctr]:
        prtstr += ' RD_EN'
        prtstr += ' rd_mux[%1i]' % d['rd_mux'][ctr]
        prtstr += ' rd_busy[%1i]' % d['rd_busy'][ctr]
        prtstr += ' rd_done[%1i]' % d['rd_done'][ctr]
        # prtstr += ' rd_ctr9[192]' % d[''][ctr]
        # prtstr += ' rd_addr_msw[1]' % d[''][ctr]
        rd_bank = d['rd_addr'][ctr] / 32
        prtstr += ' rd_addr[%3i,%i]' % (d['rd_addr'][ctr], rd_bank)
    else:
        prtstr += ' ' * 53

    prtstr += '  ||  '
    prtstr += ' SYNC' if d_rd['sync'][ctr] else '     '
    if d_rd['dv'][ctr]:
        prtstr += ' DV'
        prtstr += ' mux[%1i]' % d_rd['mux'][ctr]
        prtstr += ' d[%5i]' % d_rd['d%i' % d_rd['mux'][ctr]][ctr]
        prtstr += ' addr[%3i]' % d_rd['rd_addr_out'][ctr]
        prtstr += ' freq[%5i]' % d_rd['premux_freq'][ctr]

        if d_rd['d%i' % d_rd['mux'][ctr]][ctr] != d_rd['premux_freq'][ctr]:
            prtstr += ' ERROR'
            errors.append(ctr)

    if wr_bank is not None and rd_bank is not None:
        if wr_bank == rd_bank:
            prtstr += 'BNK_CLSH'
            bank_clash.append(ctr)

    rd_addr_comp = d['rd_addr'][ctr] >> 5
    wr_addr_comp = d['wr_addr'][ctr] >> 8
    if d['rd_en'][ctr] and d['wr_en'][ctr] and (rd_addr_comp == wr_addr_comp):
        prtstr += 'ADDRSSNG_CLSH'
        addr_clash.append(ctr)

    print(prtstr)

    # if d['in_d0'][ctr] == feng_utils.PROBLEM_FREQ:
    #     target.append(ctr)
    #     stopctr = ctr + 6000
    #
    # if stopctr is not None and ctr >= stopctr:
    #     break
print(target)
print('addr_clash', addr_clash)
print('bank_clash', bank_clash)
print('data errors:', str(errors[0:min(len(errors), 100)]))
IPython.embed()
raise RuntimeError


def make_interleaved_freqs():
    numfreqs = 4096
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
    total_freqs = []
    for freq in interleaved_freqs:
        for ctr in range(8):
            total_freqs.append(freq + ctr)
    return total_freqs


freqs_compare = make_interleaved_freqs()
freqs_compare.extend(make_interleaved_freqs())


def obuf_circ():
    d = {}
    f.registers.ct_debug.write(snap_trig=False)
    f.snapshots['obuf0_ss'].arm(
        man_trig=False, man_valid=True, circular_capture=True)
    f.snapshots['obuf1_ss'].arm(
        man_trig=False, man_valid=True, circular_capture=True)
    f.registers.ct_debug.write(snap_trig='pulse')
    d = f.snapshots['obuf0_ss'].read(arm=False)['data']
    d.update(f.snapshots['obuf1_ss'].read(arm=False)['data'])
    print('')
    lastmux = -1
    pktlen = 0
    snaplen = len(d['rd_en']) - 50

    d = {
        'en': d['dv'],
        'mux': d['mux'],
        'd0': d['d0'],
        'd1': d['d1'],
        'd2': d['d2'],
        'd3': d['d3'],
        'd4': d['d4'],
        'd5': d['d5'],
        'd6': d['d6'],
        'd7': d['d7'],
    }
    ctr = 0
    while d['en'][ctr]:
        ctr += 1
    ctr += 1
    for k in d:
        d[k] = d[k][ctr:]
    pktctr = 0
    pktlens = {}
    pktctr_error = False
    for ctr in range(1, snaplen):
        prtstr = '%5i' % ctr
        for k in d:
            prtstr += ' %s(%i)' % (k, d[k][ctr])
        if d['en'][ctr]:
            pktctr += 1
        else:
            if d['en'][ctr - 1]:
                prtstr += ' PKT(%i)' % pktctr
                if pktctr not in pktlens:
                    pktlens[pktctr] = 0
                pktlens[pktctr] += 1
                if pktctr != 32:
                    pktctr_error = True
                pktctr = 0
        print(prtstr)
        if pktctr_error:
            raise RuntimeError
    print pktlens


def obuf_circ_analyse():
    # d = {}
    # f.registers.ct_debug.write(snap_trig=False)
    # f.snapshots['obuf0_ss'].arm(
    #     man_trig=False, man_valid=True, circular_capture=True)
    # f.snapshots['obuf1_ss'].arm(
    #     man_trig=False, man_valid=True, circular_capture=True)
    # f.registers.ct_debug.write(snap_trig='pulse')
    d = f.snapshots['obuf0_ss'].read(arm=False)['data']
    d.update(f.snapshots['obuf1_ss'].read(arm=False)['data'])
    lastmux = -1
    pktlen = 0
    pktlens = {}
    lastmux = d['mux'][0]
    ctr = 0
    while d['mux'][ctr] == lastmux:
        ctr += 1
    for k in d:
        d[k] = d[k][ctr:]
    lastmux = -1
    snaplen = len(d['in_tag'])
    pktval = -1
    freqs = []
    wrong_pktlens = {}
    for ctr in range(snaplen):
        prtstr = '%5i' % ctr
        dv = d['dv'][ctr]
        muxval = d['mux'][ctr]
        if dv:
            data = d['d%i' % muxval][ctr]
            prtstr += ' d(%4i)' % data
            prtstr += ' calc_freq(%4i)' % d['premux_freq'][ctr]
            prtstr += ' mux(%1i)' % d['mux'][ctr]
            if muxval != lastmux:
                pktval = data
                freqs.append(data)
                if pktlen not in pktlens:
                    pktlens[pktlen] = 0
                pktlens[pktlen] += 1
                if pktlen != 32:
                    if pktlen not in wrong_pktlens:
                        wrong_pktlens[pktlen] = []
                    wrong_pktlens[pktlen].append(ctr)
                prtstr += ' ' + str(pktlen)
                lastmux = muxval
                pktlen = 1
            else:
                pktlen += 1
                if data != pktval:
                    print('data changes inside pkt at position %i' % ctr)
                    import IPython
                    IPython.embed()
                    raise RuntimeError
            print(prtstr)
    if 0 in pktlens:
        if pktlens[0] == 1:
            pktlens.pop(0)
    if len(pktlens) > 1:
        print('')
        print(pktlens)
        print('Incorrect pkt len found.')
        import IPython
        IPython.embed()
        raise RuntimeError
    if pktlens.keys()[0] != 32:
        print('')
        print(pktlens)
        print('pkts are not 32 long.')
        import IPython
        IPython.embed()
        raise RuntimeError
    # check the frequencies
    idx = freqs_compare.index(freqs[0])
    if freqs != freqs_compare[idx: idx + len(freqs)]:
        print('frequencies are not correct.')
        import IPython
        IPython.embed()
        raise RuntimeError

print(f.host)
loopctr = 0
while True:
    obuf_circ_analyse()
    print(loopctr, time.time())
    loopctr += 1
    break

# end
