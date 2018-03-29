import time
import IPython

import casperfpga

import feng_utils

FPGAS_OP = casperfpga.utils.threaded_fpga_operation
CIRC = True
MANVALID = True

hosts = feng_utils.setup_fhosts()

FPGAS_OP(hosts, 5, lambda f: f.registers.control.write(sys_rst='pulse',))
                                                       # cnt_rst='pulse'))
time.sleep(2)

while True:
    try:
        feng_utils.print_err_regs(hosts)
        print('*' * 100)
        time.sleep(1)
    except KeyboardInterrupt:
        break

while True:
    try:
        for host in hosts:
            print(host.host)
            print('\t%s' % host.registers.sync_ctrs1.read()['data'])
            print('\t%s' % host.registers.sync_ctrs2.read()['data'])
        print('*' * 100)
        time.sleep(1)
    except KeyboardInterrupt:
        break


def get_sync_times(f):
    ct_sync = (f.registers.ct_sync_time_msw.read()['data']['reg'] << 32) + \
        f.registers.ct_sync_time_lsw.read()['data']['reg']
    pack_sync = (f.registers.pack_sync_time_msw.read()['data']['reg'] << 32) + \
        f.registers.pack_sync_time_lsw.read()['data']['reg']
    return ct_sync, pack_sync

data = FPGAS_OP(hosts, 5, get_sync_times)

for host in hosts:
    ct_sync = data[host.host][0]
    pack_sync = data[host.host][1]
    print(host.host)
    print('\tCT sync time: %s' % ct_sync)
    print('\tPack sync time: %s' % pack_sync)
    print('\tDiff: %i' % (pack_sync - ct_sync))

print('\nCtrl+C to continue...\n')
while True:
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        break


# set up the snapshots
def setup_snaps(f):
    # f.registers.ct_debug.write(wrrd_stopmux=7, out_stopmux=4,
    #                            snap_arm=False, snap_trig=False)
    f.registers.ct_debug.write(wrrd_stopmux=6, out_stopmux=3,
                               snap_arm=False, snap_trig=False)
    f.snapshots.hmc_readwrite0_ss.arm(circular_capture=CIRC, man_valid=MANVALID)
    f.snapshots.hmc_readwrite1_ss.arm(circular_capture=CIRC, man_valid=MANVALID)
    f.snapshots.hmc_readwrite2_ss.arm(circular_capture=CIRC, man_valid=MANVALID)
    f.snapshots.output_ss.arm(circular_capture=CIRC, man_valid=MANVALID)
    f.snapshots.output1_ss.arm(circular_capture=CIRC, man_valid=MANVALID)
    f.snapshots.obuf_info_ss.arm(circular_capture=CIRC, man_valid=MANVALID)
    f.snapshots.obuf_info1_ss.arm(circular_capture=CIRC, man_valid=MANVALID)
    f.registers.ct_debug.write(snap_arm=True, snap_trig=True)

FPGAS_OP(hosts, 5, setup_snaps)

print('Waiting for an error...')
last_vals = {host.host: None for host in hosts}
error_host = None
loopctr = 0
while True:
    for host in hosts:
        hname = host.host
        val = host.registers.ct_status2.read()['data']['freq_sync_err']
        if last_vals[hname] is None:
            print('%s: %i freq sync errors' % (host.host, val))
        elif last_vals[hname] != val:
            print('%s has SYNC ERRORS' % hname)
            error_host = host
            break
        last_vals[hname] = val
    if error_host is not None:
        break
    time.sleep(0.2)
    if loopctr == 10:
        print('\t%i' % time.time())
        loopctr = 0
    loopctr += 1
hosts = [error_host]


# read the snapshots
def read_snaps(f):
    d0 = f.snapshots.hmc_readwrite0_ss.read(arm=False)['data']
    d1 = f.snapshots.hmc_readwrite1_ss.read(arm=False)['data']
    d2 = f.snapshots.hmc_readwrite2_ss.read(arm=False)['data']
    d3 = f.snapshots.output_ss.read(arm=False)['data']
    d4 = f.snapshots.output1_ss.read(arm=False)['data']
    d5 = f.snapshots.obuf_info_ss.read(arm=False)['data']
    d6 = f.snapshots.obuf_info1_ss.read(arm=False)['data']
    return [d0, d1, d2, d3, d4, d5, d6]

fpga_data = FPGAS_OP(hosts, 200, read_snaps)
data = fpga_data[error_host.host]

d = data[0]
d.update(data[1])
d.update(data[2])
verbose = True

# old_pkts = []
# last_pkt = []
# busy_pkt = []
# pkt_begins = False
# for ctr in range(len(d['d0'])):
#     prtstr = '%5i' % ctr
#     # write
#     prtstr += ' | d(%4i)' % d['d0'][ctr]
#     prtstr += ' en(%i) addr(%6i, %6i)' % (
#         d['wr_en'][ctr], d['wr_addr_raw'][ctr], d['wr_addr'][ctr])
#     # read
#     prtstr += ' | en(%i) addr(%6i, %6i) tag(%3i) arm(%i)' % (
#         d['rd_en'][ctr], d['rd_addr_raw'][ctr], d['rd_addr'][ctr],
#         d['rd_tag'][ctr], d['rd_arm'][ctr])
#     # hmc status
#     hmc_d0_3 = (d['hmc_d0_3_msb'][ctr] << 9) + d['hmc_d0_3_lsb'][ctr]
#     if d['hmc_dv'][ctr] == 1:
#         prtstr += ' | d(%4i) tag_out(%3i)' % (
#                       d['hmc_d0_0'][ctr], d['hmc_tag'][ctr])
#         if d['wr_rdy'][ctr] == 0 or d['rd_rdy'][ctr] == 0:
#             prtstr += 'RDY_ERROR(%i,%i)' % (d['wr_rdy'][ctr], d['rd_rdy'][ctr])
#         if not d['post_okay'][ctr]:
#             prtstr += 'POST_ERROR'
#         if d['err_pktlen'][ctr] + d['err_dvblock'][ctr] + \
#                 d['err_wrdata_repeat'][ctr] + d['err_wrdata_d4zero'][ctr] > 0:
#             prtstr += 'err(pktlen,dvblk,wrd_rep,wrd_d4z:%i,%i,%i,%i)' % (
#                 d['err_pktlen'][ctr], d['err_dvblock'][ctr],
#                 d['err_wrdata_repeat'][ctr], d['err_wrdata_d4zero'][ctr])
#     else:
#         prtstr += ' | tag_out(%3i)' % d['hmc_tag'][ctr]
#     # data in error
#     if ((d['d1'][ctr] != d['d0'][ctr] + 1) or
#             (d['d4'][ctr] != d['d1'][ctr] + 3)) and d['wr_en'][ctr]:
#         # errors['data_in'].append(ctr)
#         prtstr += ' DATA_IN_ERROR(%4i, %4i, %4i)' % (
#             d['d0'][ctr], d['d1'][ctr], d['d4'][ctr])
#     # hmc_data_out_error
#     if ((d['hmc_d0_1'][ctr] != d['hmc_d0_0'][ctr] + 1) or
#             (d['hmc_d0_2'][ctr] != d['hmc_d0_1'][ctr] + 1) or
#             (hmc_d0_3 != d['hmc_d0_2'][ctr] + 1)) and d['hmc_dv'][ctr]:
#         # errors['hmc_data'].append(ctr)
#         prtstr += ' HMC_OUT_DATA_ERROR(%4i, %4i, %4i, %4i)' % (
#             d['hmc_d0_0'][ctr], d['hmc_d0_1'][ctr], d['hmc_d0_2'][ctr],
#             hmc_d0_3)
#     # sync error?
#     if (d['rd_en'][ctr] and (not d['wr_en'][ctr])) or \
#             ((not d['rd_en'][ctr]) and d['wr_en'][ctr]):
#         # errors['read_write_sync'].append(ctr)
#         prtstr += ' SYNC_ERROR'
#     # ready error?
#     if (not d['rd_rdy'][ctr]) or (not d['wr_rdy'][ctr]):
#         # errors['rdy'].append(ctr)
#         prtstr += ' RDY_ERROR'
#     # catch the aligned zero address
#     # if (d['d0'][ctr] == 0) and (d['wr_addr_raw'][ctr] == 0):
#     #     errors['address_catch'].append(ctr)
#     #     prtstr += ' D0_ZERO'
#     # if d['rd_addr_raw'][ctr] == 1:
#     #     errors['address_catch'].append(ctr)
#     #     prtstr += ' RD_RAW_ONE'
#     if (d['rd_en'][ctr] == 1) and (d['rd_tag'][ctr] == 0):
#         prtstr += '\t\t\tNEW_PKT'
#         old_pkts.append(last_pkt[:])
#         last_pkt = busy_pkt[:]
#         busy_pkt = []
#         pkt_begins = True
#
#     if (d['rd_en'][ctr] == 1) and (d['rd_tag'][ctr] == 256):
#         prtstr += '\t\t\tPKT_BEGINS=FALSE'
#         pkt_begins = False
#
#     if d['hmc_dv'][ctr] == 1:
#         tag = d['hmc_tag'][ctr]
#         if tag >= 256 and pkt_begins:
#             last_pkt.append(tag)
#         else:
#             busy_pkt.append(tag)
#
#     prtstr += '\t\t\tLAST(%i) BUSY(%i)' % (len(last_pkt), len(busy_pkt))
#
#     if (d['rd_en'][ctr] or d['wr_en'][ctr] or d['hmc_dv'][ctr]) and verbose:
#         print(prtstr)
#
# old_pkts.append(last_pkt[:])
# old_pkts.append(busy_pkt[:])
#
# # old_pkts = old_pkts[2:-3]
#
# for pkt in old_pkts:
#     pkt.sort()
#
# print('#' * 100)
# print('Have %i packets.' % len(old_pkts))
# print('#' * 100)
#
# for ctr, pkt in enumerate(old_pkts):
#     if pkt != range(512):
#         missing = []
#         for miss in range(512):
#             if miss not in pkt:
#                 missing.append(miss)
#         print('pkt %i is missing these tags: %s' % (ctr, missing))
#         print('%' * 100)

###################
# output
###################
if True:
    d = data[3]
    d.update(data[4])
    one_lens = {}
    zero_lens = {}
    last_rising = -1
    last_falling = -1
    errors = {
        'one_len': [],
        'data_freqid': [],
        'sync': [],
    }
    verbose_limits = (-1, -1)
    for ctr in range(0, len(d['dv'])):
        prtstr = ''
        if d['sync'][ctr]:
            prtstr += '*' * 100
            prtstr += '\n'
            prtstr += '*' * 100
            prtstr += '\n'
        prtstr += '%5i dv(%i)' % (ctr, d['dv'][ctr])
        prtstr += ' pkt_start(%i) sync(%i)' % (
            d['pkt_start'][ctr], d['sync'][ctr])
        prtstr += ' gen_freq_id(%4i)' % d['gen_freq_id'][ctr]
        pkt_ctr = d['pkt_ctr'][ctr] & 0xfff
        interleaved_freq = (((pkt_ctr >> 3) & 0x0f) << 8) + \
                           (((pkt_ctr >> 7) & 0x1f) << 3) + \
                           (pkt_ctr & 0x07)
        prtstr += ' pkt_ctr(%12i,%4i,%4i)' % (
            d['pkt_ctr'][ctr], pkt_ctr, interleaved_freq)
        prtstr += ' d(%4i)' % d['d0_0'][ctr]


        def _data_error(compare):
            if d['d0_0'][ctr] != compare:
                return ' ERROR(%4i,%4i)' % (d['d0_0'][ctr], compare)
            return ''

        prtstr += _data_error(d['d1_0'][ctr])
        prtstr += _data_error(d['d1_1'][ctr])
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
        if (d['gen_freq_id'][ctr] != d['d0_0'][ctr]) and (d['dv'][ctr]):
            errors['sync'].append(ctr)
            prtstr += ' SYNC(off %i)' % (d['gen_freq_id'][ctr] - d['d0_0'][ctr])
        if verbose:
            if ((verbose_limits[0] == -1) or (ctr > verbose_limits[0])) and \
                    ((verbose_limits[1] == -1) or (ctr < verbose_limits[1])):
                print(prtstr)

###################
# obuf
###################
print('#' * 100)
d = data[5]
d.update(data[6])
rd_en_high = -1
rd_en_low = -1
ones = {}
zeros = {}
for ctr in range(1, len(d['wr_en'])):
    prtstr = ''
    prtstr += '%5i' % ctr
    prtstr += ' | WR en(%i) addr(%6i)' % (d['wr_en'][ctr], d['wr_addr'][ctr])
    prtstr += ' | RD en(%i) addr(%6i) mux(%1i)' % (
        d['rd_en'][ctr], d['rd_addr'][ctr], d['rd_mux'][ctr])
    prtstr += ' go(%1i) done(%1i) busy(%1i) go_err(%1i) addr_msw(%1i)' % (
        d['rd_go'][ctr], d['rd_done'][ctr],
        d['rd_busy'][ctr], d['rd_go_err'][ctr], d['rd_addr_msw'][ctr], )
    raw_ctr = (d['raw_freq_ctr_msw'][ctr] << 32) + d['raw_freq_ctr_lsb'][ctr]
    prtstr += ' | rawctr(%i) fctr(%4i)' % (raw_ctr, raw_ctr & 0xfff)
    prtstr += ' | d(%i)' % d['rd_d0_0'][ctr]
    if d['rd_go'][ctr]:
        prtstr += ' RD_GO'
    if d['rd_en'][ctr] and (not d['rd_en'][ctr-1]):
        zlen = ctr - rd_en_low
        prtstr += ' ZEROS(%i)' % zlen
        if zlen not in zeros:
            zeros[zlen] = 0
        zeros[zlen] += 1
        rd_en_high = ctr
    if d['rd_en'][ctr-1] and (not d['rd_en'][ctr]):
        olen = ctr - rd_en_high
        prtstr += ' ONES(%i)' % olen
        if olen not in ones:
            ones[olen] = 0
        ones[olen] += 1
        rd_en_low = ctr
    print(prtstr)

print('ZEROS: %s' % zeros)
print('ONES: %s' % ones)

IPython.embed()

# end
