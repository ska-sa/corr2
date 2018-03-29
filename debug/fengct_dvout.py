import sys

import feng_utils

findex = 0
circ = False
if len(sys.argv) > 1:
    findex = int(sys.argv[1])
if len(sys.argv) > 2:
    arg = sys.argv[2].strip()
    circ = arg == '1'

hosts = feng_utils.setup_hosts()
feng_utils.ct_tvg(hosts, 1)
feng_utils.print_err_regs(hosts)


def get_data(data=None, verbose=False, verbose_limits=(-1, -1)):
    # get a snapshot of the output
    if data is None:
        f = hosts[findex]
        d = data or f.snapshots.ct_dv_out_ss.read(man_trig=True,
                                                  circular_capture=circ)['data']
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

data, errors = get_data()
if len(errors) > 0:
    err_start = errors[0] - 50
    err_end = err_start + 100
    a = get_data(data, True, (err_start, err_end))

import IPython
IPython.embed()

# end
