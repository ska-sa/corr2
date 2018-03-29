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

# get a snapshot of the TX outputs - are the packets going to the correct place?
f.registers.x_setup.write(snap_arm=False)
# f.registers.ct_debug.write(gbe_mux=4)

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
    prtstr = '%5i' % ctr
    dv = d2['valid_raw'][ctr]
    prtstr += ' 0x%032x' % d0['d_msb'][ctr]
    prtstr += ' 0x%032x' % d1['d_lsb'][ctr]
    dword0 = (d0['d_msb'][ctr]) & 0xffff
    prtstr += ' d0(%i)' % dword0
    ip = IpAddress(d2['src_ip'][ctr])
    prtstr += ' %s:%i' % (ip, d2['src_port'][ctr])
    prtstr += ' dv(%i)' % d2['valid_raw'][ctr]
    prtstr += ' eof(%i)' % d2['eof'][ctr]
    if dv:
        eof_dv_ctr += 1
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
        prtstr += ' DV_CHANGE(%i)' % diff
    dv_prev = dv
    if d2['eof'][ctr]:
        diff = ctr - prev_eof
        if diff not in eofs:
            eofs[diff] = 0
        eofs[diff] += 1
        if eof_dv_ctr not in eofs_dv:
            eofs_dv[eof_dv_ctr] = 0
        eofs_dv[eof_dv_ctr] += 1
        prev_eof = ctr
        prtstr += ' EOF(%i,%i)' % (diff, eof_dv_ctr)
        eof_dv_ctr = 0
    if d2['gbe_err'][ctr] or d2['gbe_full'][ctr] or d2['gbe_of'][ctr]:
        prtstr += ' GBE_ERROR'
        gbe_errors.append(ctr)

    print prtstr


print gbe_errors

print 'ones:', ones
print 'zeros:', zeros
print 'eofs:', eofs
print 'eofs_dv:', eofs_dv

# end
