import feng_utils

hosts = feng_utils.setup_hosts()
feng_utils.ct_tvg(hosts, 1)
feng_utils.print_err_regs(hosts)

# raise RuntimeError

# get a snapshot of the output
f = hosts[0]
d = f.snapshots.out_freqs_ss.read(man_trig=True)['data']
prev_idx = -8
prev_xeng = -1
errors = []
for ctr, freq in enumerate(d['d0_0']):
    xeng = freq / 256
    prtstr = '%5i - freq(%4i) xeng(%2i)' % (ctr, freq, xeng)
    if xeng != prev_xeng:
        diff = ctr - prev_idx
        if diff != 8:
            errors.append(ctr)
            prtstr += ' ERROR'
        prev_idx = ctr
    print(prtstr)
    prev_xeng = xeng
print errors

# end
