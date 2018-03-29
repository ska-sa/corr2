import feng_utils

hosts = feng_utils.setup_hosts()
feng_utils.ct_tvg(hosts, 1)
feng_utils.print_err_regs(hosts)

# # enable real data
# feng_utils.bypass_cd(hosts, 0)

findex = 0

for f in hosts:
    # set up the muxes and snapshots
    f.registers.ct_debug.write(
        in_stopmux=6,
        in_trigmux=1,
        wrrd_stopmux=6,
        out_stopmux=3,
        outfreq_stopmux=3,
        gbe_stopmux=0,
        snap_arm=0,
        snap_trig=0,
    )

    # arm all the snaps
    f.snapshots['ct_dv_in_ss'].arm(circular_capture=True)
    f.snapshots['hmc_readwrite0_ss'].arm(circular_capture=True, man_valid=True)
    f.snapshots['hmc_readwrite1_ss'].arm(circular_capture=True, man_valid=True)
    f.snapshots['hmc_readwrite2_ss'].arm(circular_capture=True, man_valid=True)
    f.snapshots['hmc_dv_out_ss'].arm(circular_capture=True)
    f.snapshots['obuf_info_ss'].arm(circular_capture=True, man_valid=True)
    f.snapshots['output_ss'].arm(circular_capture=True, man_valid=True)
    f.snapshots['output1_ss'].arm(circular_capture=True, man_valid=True)
    f.snapshots['out_freqs_ss'].arm(circular_capture=True)
    f.snapshots['ct_dv_out_ss'].arm(circular_capture=True)
    f.snapshots['txips_ss'].arm()

    # trigger them
    f.registers.ct_debug.write(
        snap_arm=1,
        snap_trig='pulse',
    )

import time
while True:
    try:
        feng_utils.print_err_regs(hosts)
        time.sleep(1)
    except KeyboardInterrupt:
        findex = None
        print('\n\n\nSet the findex!\n\n\n')
        import IPython
        IPython.embed()
        break

f = hosts[findex]


# read 'em
def get_data_ct_dv_in(data=None, verbose=False, verbose_limits=(-1, -1)):
    # get a snapshot of the output
    if data is None:
        f = hosts[findex]
        d = data or f.snapshots['ct_dv_in_ss'].read(arm=False)['data']
        dvs = []
        for d32 in d['dv32']:
            dvs.extend(feng_utils.decode(d32, 32))
        ctr = 0
        while dvs[ctr] == 1:
            ctr += 1
        dvs = dvs[ctr:]
    else:
        dvs = data
    print('DV INPUT TO CT:')
    one_lens = {}
    zero_lens = {}
    last_rising = -1
    last_falling = -1
    one_len_errors = []
    for ctr in range(1, len(dvs)):
        prtstr = '%5i %i' % (ctr, dvs[ctr])
        if (dvs[ctr] == 1) and (dvs[ctr - 1] == 0):
            # rising edge
            zlen = ctr - last_falling
            if zlen not in zero_lens:
                zero_lens[zlen] = 0
            zero_lens[zlen] += 1
            prtstr += ' ZLEN(%i)' % zlen
            last_rising = ctr
        elif (dvs[ctr] == 0) and (dvs[ctr - 1] == 1):
            # falling edge
            olen = ctr - last_rising
            if olen not in one_lens:
                one_lens[olen] = 0
            one_lens[olen] += 1
            prtstr += ' OLEN(%i)' % olen
            if olen != 512:
                one_len_errors.append(ctr)
            last_falling = ctr
        if verbose:
            if ((verbose_limits[0] == -1) or (ctr > verbose_limits[0])) and \
               ((verbose_limits[1] == -1) or (ctr < verbose_limits[1])):
                print(prtstr)
    print('\tONE_LENS: %s' % one_lens)
    print('\tZERO_LENS: %s' % zero_lens)
    print('\tONE_LEN_ERRORS: %s' % one_len_errors)
    return dvs, one_len_errors

data, errors = get_data_ct_dv_in()
if len(errors) > 0:
    err_start = errors[0] - 50
    err_end = err_start + 100
    a = get_data_ct_dv_in(data, True, (err_start, err_end))
    raise RuntimeError('Already an error in the input.')
else:
    print('NO ERRORS IN INPUT TO HMC CT.')
print(75*'#')


def get_data_hmc_dv_out(data=None, verbose=False, verbose_limits=(-1, -1)):
    """

    :param data:
    :param verbose:
    :param verbose_limits:
    :return:
    """
    # get a snapshot of the output
    if data is None:
        f = hosts[findex]
        d = data or f.snapshots['hmc_dv_out_ss'].read(arm=False)['data']
        dvs = []
        for d128 in d['dv128']:
            dvs.extend(feng_utils.decode(d128, 128))
        ctr = 0
        while dvs[ctr] == 1:
            ctr += 1
        dvs = dvs[ctr:]
    else:
        dvs = data
    print('HMC OUTPUT DVs:')
    one_lens = {}
    zero_lens = {}
    last_rising = -1
    last_falling = -1
    for ctr in range(1, len(dvs)):
        prtstr = '%5i %i' % (ctr, dvs[ctr])
        if (dvs[ctr] == 1) and (dvs[ctr - 1] == 0):
            # rising edge
            zlen = ctr - last_falling
            if zlen not in zero_lens:
                zero_lens[zlen] = 0
            zero_lens[zlen] += 1
            prtstr += ' ZLEN(%i)' % zlen
            last_rising = ctr
        elif (dvs[ctr] == 0) and (dvs[ctr - 1] == 1):
            # falling edge
            olen = ctr - last_rising
            if olen not in one_lens:
                one_lens[olen] = 0
            one_lens[olen] += 1
            prtstr += ' OLEN(%i)' % olen
            last_falling = ctr
        if verbose:
            if ((verbose_limits[0] == -1) or (ctr > verbose_limits[0])) and \
               ((verbose_limits[1] == -1) or (ctr < verbose_limits[1])):
                print(prtstr)
    print('\tONE_LENS: %s' % one_lens)
    print('\tZERO_LENS: %s' % zero_lens)
    return dvs, []

data, errors = get_data_hmc_dv_out()
print(75*'#')


def get_data_ct_out(data=None, verbose=False, verbose_limits=(-1, -1)):
    # get a snapshot of the output
    if data is None:
        f = hosts[findex]
        d = data or f.snapshots.ct_dv_out_ss.read(arm=False)['data']
        dvs = []
        for d128 in d['dv128']:
            dvs.extend(feng_utils.decode(d128, 128))
        ctr = 0
        while dvs[ctr] == 1:
            ctr += 1
        dvs = dvs[ctr:]
    else:
        dvs = data

    one_lens = {}
    zero_lens = {}
    last_rising = -1
    last_falling = -1
    one_len_errors = []
    for ctr in range(1, len(dvs)):
        prtstr = '%5i %i' % (ctr, dvs[ctr])
        if (dvs[ctr] == 1) and (dvs[ctr - 1] == 0):
            # rising edge
            zlen = ctr - last_falling
            if zlen not in zero_lens:
                zero_lens[zlen] = 0
            zero_lens[zlen] += 1
            prtstr += ' ZLEN(%i)' % zlen
            last_rising = ctr
        elif (dvs[ctr] == 0) and (dvs[ctr - 1] == 1):
            # falling edge
            olen = ctr - last_rising
            if olen not in one_lens:
                one_lens[olen] = 0
            one_lens[olen] += 1
            prtstr += ' OLEN(%i)' % olen
            if olen != 32:
                one_len_errors.append(ctr)
            last_falling = ctr
        if verbose:
            if ((verbose_limits[0] == -1) or (ctr > verbose_limits[0])) and \
               ((verbose_limits[1] == -1) or (ctr < verbose_limits[1])):
                print(prtstr)
    print('ONE_LENS: %s' % one_lens)
    print('ZERO_LENS: %s' % zero_lens)
    print('ONE_LEN_ERRORS: %s' % one_len_errors)
    return dvs, one_len_errors

data, errors = get_data_ct_out()
if len(errors) > 0:
    err_start = errors[0] - 50
    err_end = err_start + 100
    a = get_data_ct_out(data, True, (err_start, err_end))
print(75*'#')


def read_hmc_output(data=None, verbose=False, verbose_limits=(-1, -1)):
    if data is None:
        d = f.snapshots['hmc_readwrite0_ss'].read(arm=False)['data']
        d.update(f.snapshots['hmc_readwrite1_ss'].read(arm=False)['data'])
        d.update(f.snapshots['hmc_readwrite2_ss'].read(arm=False)['data'])
    else:
        d = data
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
        prtstr += ' | d(%4i)' % d['d0'][ctr]
        prtstr += ' en(%i) addr(%6i, %6i)' % (
            d['wr_en'][ctr], d['wr_addr_raw'][ctr], d['wr_addr'][ctr])
        # read
        prtstr += ' | en(%i) addr(%6i, %6i) tag(%3i) arm(%i)' % (
            d['rd_en'][ctr], d['rd_addr_raw'][ctr], d['rd_addr'][ctr],
            d['rd_tag'][ctr], d['rd_arm'][ctr])
        # hmc status
        hmc_d0_3 = (d['hmc_d0_3_msb'][ctr] << 9) + d['hmc_d0_3_lsb'][ctr]
        prtstr += ' | d(%4i) tag_out(%i) dv_out(%i) rdy(%i,%i) ' \
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
        # if (d['d0'][ctr] == 0) and (d['wr_addr_raw'][ctr] == 0):
        #     errors['address_catch'].append(ctr)
        #     prtstr += ' D0_ZERO'
        # if d['rd_addr_raw'][ctr] == 1:
        #     errors['address_catch'].append(ctr)
        #     prtstr += ' RD_RAW_ONE'
        if verbose and (d['rd_en'][ctr] or d['wr_en'][ctr]):
            if ((verbose_limits[0] == -1) or (ctr > verbose_limits[0])) and \
               ((verbose_limits[1] == -1) or (ctr < verbose_limits[1])):
                print(prtstr)
    got_errors = False
    for k in errors:
        if verbose:
            print('%s: %s' % (k, errors[k]))
        if len(errors[k]) > 0:
            got_errors = True
    return d, got_errors

# data_hmc, errors = read_hmc_output(None, True)
# # if errors > 0:
# #     a = read_hmc_output(data_hmc, True)
# print(75 * '#')


def read_obuf_info(data=None, verbose=False, verbose_limits=(-1, -1)):
    if data is None:
        d = f.snapshots['obuf_info_ss'].read(arm=False)['data']
        ctr = 0
        while d['rden'][ctr] == 1:
            ctr += 1
        for k in d:
            d[k] = d[k][ctr:]
    else:
        d = data
    one_lens = {}
    zero_lens = {}
    last_rising = -1
    last_falling = -1
    one_len_errors = []
    for ctr in range(1, len(d['rden'])):
        prtstr = '%5i' % ctr
        # write
        prtstr += ' | en(%1i) addr(%6i) d(%5i)' % (
            d['wren'][ctr], d['wraddr'][ctr], d['wrd0'][ctr])
        # read
        try:
            future_data = d['rdd0'][ctr+10]
        except IndexError:
            future_data = -1
        prtstr += ' | en(%1i) addr(%3i) d(%4i) mx(%2i)' % (
                    d['rden'][ctr], d['rdaddr'][ctr], d['rdd0'][ctr],
                    d['rdmux'][ctr])
        # prtstr += ' dshft(%4i)' % future_data
        prtstr += ' raw(%i,%i) ctren(%i) ctrrst(%i) ctr(%3i) now(%i)' \
                  ' now2(%i)' % (
                      d['raw_sync'][ctr],
                      d['raw_armed'][ctr], d['rdctr_en'][ctr],
                      d['rdctr_rst'][ctr], d['rdctr'][ctr],
                      d['rdnow'][ctr], d['rdnow2'][ctr])
        # if d['wren'][ctr] and (d['wraddr'][ctr] == 250):
        #     prtstr += 'GO_NOW'
        if (d['rden'][ctr] == 1) and (d['rden'][ctr - 1] == 0):
            # rising edge
            zlen = ctr - last_falling
            if zlen not in zero_lens:
                zero_lens[zlen] = 0
            zero_lens[zlen] += 1
            prtstr += ' ZLEN(%i)' % zlen
            last_rising = ctr
        elif (d['rden'][ctr] == 0) and (d['rden'][ctr - 1] == 1):
            # falling edge
            olen = ctr - last_rising
            if olen not in one_lens:
                one_lens[olen] = 0
            one_lens[olen] += 1
            prtstr += ' OLEN(%i)' % olen
            if olen != 32:
                one_len_errors.append(ctr)
            last_falling = ctr
        if verbose:
            if ((verbose_limits[0] == -1) or (ctr > verbose_limits[0])) and \
               ((verbose_limits[1] == -1) or (ctr < verbose_limits[1])):
                print(prtstr)
    print('ONE_LENS: %s' % one_lens)
    print('ZERO_LENS: %s' % zero_lens)
    print('ONE_LEN_ERRORS: %s' % one_len_errors)
    return d, one_len_errors

# data_output, errors = read_obuf_info()
# if len(errors) > 0:
#     err_start = errors[0] - 100
#     err_end = err_start + 1000
#     # a = read_ct_output(data, True, (err_start, err_end))
#     a = read_obuf_info(data_output, True)
# print(75 * '#')


from fengct_output import read_ct_output

data_output, errors = read_ct_output(f)
if len(errors) > 0:
    err_start = errors[0] - 100
    err_end = err_start + 1000
    # a = read_ct_output(f, data, True, (err_start, err_end))
    a = read_ct_output(f, data_output, True)
print(75 * '#')

import IPython
IPython.embed()

# end
