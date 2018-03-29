import casperfpga
from casperfpga import spead as casperspead

import feng_utils
import time

FPGAS_OP = casperfpga.utils.threaded_fpga_operation
EXPECTED_PKT_LEN = 35 * 4

DV_MUX = 0


# def temp_pack():
#     a = {
#         'a': 33,
#         'b': 1,
#         'c': 16,
#         'd': 7,
#     }
#     # sum is 57 - the most efficient way is into one 64-bit snapshot
#     # difference is 7. which is smaller than 16.
#     # but also take into account the BRAMs size?
#
#
# raise RuntimeError


xhosts = feng_utils.setup_xhosts()
fhosts = feng_utils.setup_fhosts()


def analyse_preproc_data(f, data=None, verbose=False):
    """
    A TVG is running on the f-engines that places a ramp over the
    corner-turned spectrum. So the x-engine should be receiving packets with
    a counter spread over 2 ** (12 + 8) values.
    Remember that the CT is output interleaved packets, so xeng0 will get
    freqs 0 - 255, but the ramp will jump every 8 freqs.
    """
    if data is None:
        d = f.snapshots.sys0_snap_preproc_ss.read(man_valid=False)['data']
        d['d6'] = []
        d['d7'] = []
        for dword in d['data']:
            d7 = (dword >> 0) & ((2 ** 32) - 1)
            d6 = (dword >> 32) & ((2 ** 32) - 1)
            d['d6'].append(d6)
            d['d7'].append(d7)
        d.pop('data')
    else:
        d = data
    res = {fengctr: {} for fengctr in range(4)}
    for ctr in range(len(d['d6'])):
        fengid = d['fengid'][ctr]
        freq = d['freq'][ctr]
        if freq not in res[fengid]:
            res[fengid][freq] = []
        res[fengid][freq].append(d['d6'][ctr])
    lens = []
    for fengid in res:
        for freq in res[fengid]:
            num_data = len(res[fengid][freq])
            initd0 = res[fengid][freq][0]
            initd1 = res[fengid][freq][32]
            if initd1 - initd0 != (2 ** 20):
                raise RuntimeError(fengid, freq, initd0, initd1)
            for ctr in range(1, 32):
                if res[fengid][freq][ctr] != initd0 + (ctr * 8):
                    raise RuntimeError(ctr, res[fengid][freq][ctr], initd0 + (ctr * 8))
            for ctr in range(32, 64):
                if res[fengid][freq][ctr] != initd1 + ((ctr - 32) * 8):
                    raise RuntimeError(ctr, res[fengid][freq][ctr], initd1 + ((ctr - 32) * 8))
            if num_data != 64:
                print(fengid, freq, num_data)
    # flatten the whole spectrum for each fengine
    for fengid in res:
        lastval = res[fengid][0][0] - 8
        for freq in range(256):
            for val in range(32):
                thisval = res[fengid][freq][val]
                if thisval != lastval + 8:
                    print(fengid, freq, val, thisval, lastval, thisval - lastval)
                lastval = res[fengid][freq][val]
    import IPython
    IPython.embed()


def read_preproc_data(f, data=None, verbose=False):
    if data is None:
        d = f.snapshots.sys0_snap_preproc_ss.read(man_valid=False)['data']
        d['d6'] = []
        d['d7'] = []
        for dword in d['data']:
            d7 = (dword >> 0) & ((2 ** 32) - 1)
            d6 = (dword >> 32) & ((2 ** 32) - 1)
            d['d6'].append(d6)
            d['d7'].append(d7)
        d.pop('data')
    else:
        d = data
    # gbe_packets = casperfpga.Snap.packetise_snapdata(d)
    # # check the data in the packets
    # for pkt in gbe_packets:
    #     prevd = (pkt['data'][0] >> 2) & ((2 ** 62) - 1)
    #     for ctr in range(1, len(pkt['data'])):
    #         dword = (pkt['data'][ctr] >> 2) & ((2 ** 62) - 1)
    #         if dword != prevd + ctr:
    #             diff = pkt['data'][ctr] - (prevd + ctr)
    #             raise RuntimeError(pkt['data'][ctr], prevd + ctr, diff)
    # and print some data
    for ctr in range(len(d['d6'])):
        prtstr = '%5i' % ctr
        prtstr += ' d7(%10i)' % d['d7'][ctr]
        prtstr += ' d6(%10i)' % d['d6'][ctr]
        prtstr += ' time(%12i)' % d['timestamp'][ctr]
        prtstr += ' fengid(%1i)' % d['fengid'][ctr]
        prtstr += ' freq(%4i)' % d['freq'][ctr]
        if d['valid'][ctr]:
            prtstr += ' DV'
        if d['eof'][ctr]:
            prtstr += ' EOF'
        if d['dest_err'][ctr]:
            prtstr += ' ERROR'
        if verbose:
            print(prtstr)
    return d, {}


def analyse_reord_write(f, data=None, verbose=False):
    if data is None:
        f.registers.vacctvg_control.write(
            reord_snap_trig_mux=0, reord_snap_dv_arm=0)
        for ctr in range(2):
            f.snapshots['sys0_snap_reord%1i_ss' % ctr].arm(
                man_valid=False, circular_capture=False)
        f.registers.vacctvg_control.write(reord_snap_dv_arm=1)
        d = {}
        for ctr in range(2):
            snap = f.snapshots['sys0_snap_reord%1i_ss' % ctr]
            d.update(snap.read(arm=False)['data'])
    else:
        d = data
    errors = {'recv': 0, 'recv2': 0, 'data_ctr': 0, 'dest': 0, 'disc': 0,
              'timestamp': 0, 'freqs': 0, 'freq_grp': 0}
    try:
        # check timestamp
        tstamp0 = d['timestamp'][0]
        for ctr in range(len(d['valid'])):
            if d['timestamp'][ctr] != tstamp0:
                errors['timestamp'] += 1
        # check freqs
        for freq in range(0, len(d['valid']), 1024):
            for ctr in range(1024):
                if d['freq'][freq + ctr] != d['freq'][freq]:
                    errors['freqs'] += 1
        # check the counters make sense
        freqlen = 256
        freqlen_all = freqlen * 4
        fgrplen = 8 * freqlen_all
        for fgrp in range(0, len(d['valid']), fgrplen):
            group_end = fgrp + fgrplen
            # print('%s' % str((fgrp, group_end)))
            if fgrp > 0:
                grpdiff = d['data'][fgrp] - (d['data'][fgrp - fgrplen])
                if grpdiff != (2 ** 15):
                    errors['freq_grp'] += 1
            for feng in range(0, 4):
                freqctr = f.brdid * 256
                fctr0 = d['data'][fgrp] - 1
                fstart = fgrp + (feng * freqlen)
                # print('\t%s' % str((fstart, group_end, freqlen_all)))
                for freqpos in range(fstart, group_end, freqlen_all):
                    # print('\t\t%s' % str((freqpos, freqpos + freqlen)))
                    for fctr in range(freqpos, freqpos + freqlen):
                        if d['data'][fctr] != fctr0 + 1:
                            errors['data_ctr'] += 1
                        fctr0 += 1
                    freqctr += 1
        # other errors
        for ctr in range(len(d['valid'])):
            prtstr = '%5i' % ctr
            prtstr += ' tstamp(%10i)' % d['timestamp'][ctr]
            prtstr += ' addr(%6i)' % d['rd_addr'][ctr]
            prtstr += ' freq(%4i)' % d['freq'][ctr]
            prtstr += ' data(%10i)' % d['data'][ctr]
            if d['valid'][ctr]:
                prtstr += ' DV'
            if d['received'][ctr]:
                prtstr += ' RECV'
            if d['pkt_disc'][ctr]:
                errors['disc'] += 1
                prtstr += ' ERR_DISC'
            if d['dest_err'][ctr]:
                errors['dest'] += 1
                prtstr += ' ERR_DEST'
            if d['recv_err'][ctr]:
                errors['recv'] += 1
                prtstr += ' ERR_RECV'
            if (d['valid'][ctr] and (not d['received'][ctr])) or \
               ((not d['valid'][ctr]) and d['received'][ctr]):
                errors['recv2'] += 1
                prtstr += ' ERR_RECV2'
            if verbose:
                print(prtstr)
    except RuntimeError as e:
        print(e.message)
        pass
    return d, errors


def read_reord_data(f, data=None, verbose=False):
    if data is None:
        f.registers.vacctvg_control.write(
            reord_snap_trig_mux=0, reord_snap_dv_arm=0)
        for ctr in range(5):
            f.snapshots['sys0_snap_reord%1i_ss' % ctr].arm(
                man_valid=False, circular_capture=False)
        f.registers.vacctvg_control.write(reord_snap_dv_arm=1)
        d = {}
        for ctr in range(5):
            snap = f.snapshots['sys0_snap_reord%1i_ss' % ctr]
            d.update(snap.read(arm=False)['data'])
    else:
        d = data
    errors = {'recv': 0, 'data': 0, 'dest': 0, 'disc': 0}
    freqlens = {}
    prev_freq = (-1, -1024)
    dvctr = 0
    ctrlist = range(len(d['data']))
    # if DV_MUX == 0:
    #     # reorder the groups of 8
    #     for ctr in range(0, len(d['data']), 8):
    #         for ctr2 in range(4):
    #             aidx = ctr + ctr2
    #             bidx = ctr + 7 - ctr2
    #             for key in d:
    #                 tmp = d[key][bidx]
    #                 d[key][bidx] = d[key][aidx]
    #                 d[key][aidx] = tmp
    dlast = d['data'][0] - 256
    for ctr in ctrlist:
        d32 = d['data'][ctr]

        prtstr = '%5i' % ctr
        prtstr += ' time(%10i)' % d['timestamp'][ctr]
        prtstr += ' freq(%4i)' % d['freq'][ctr]
        if DV_MUX == 0 or DV_MUX == 1:
            calcfreq = (d32 - d['data'][0]) / 256
        else:
            calcfreq = 0
        prtstr += ' calcfreq(%4i)' % calcfreq

        prtstr += '    |   RD'
        prtstr += ' en(%1i)' % d['valid'][ctr]
        prtstr += ' addr(%6i)' % d['rd_addr'][ctr]
        prtstr += ' d32(%12i)' % d32
        prtstr += ' ddiff(%6i)' % (d32 - dlast)

        prtstr += '    |   WR'
        prtstr += ' en(%1i)' % d['wr_en'][ctr]
        prtstr += ' addr(%6i)' % d['wr_addr'][ctr]
        dwr7 = d['d256_lsw'][ctr] & ((2 ** 32) - 1)
        dwr0 = (d['d256_msw'][ctr] >> 96) & ((2 ** 32) - 1)
        dwr1 = (d['d256_msw'][ctr] >> 64) & ((2 ** 32) - 1)
        prtstr += ' d_0(%10i)' % dwr0
        prtstr += ' d_1(%10i)' % dwr1
        prtstr += ' d_7(%10i)' % dwr7

        prtstr += '    |   '
        if d['valid'][ctr]:
            if not d['received'][ctr]:
                errors['recv'] += 1
            if d['freq'][ctr] != d['data'][ctr]:
                errors['data'] += 1
            if d['freq'][ctr] != prev_freq[0]:
                diff = dvctr - prev_freq[1]
                prev_freq = (d['freq'][ctr], dvctr)
                if diff not in freqlens:
                    freqlens[diff] = 0
                freqlens[diff] += 1
                prtstr += ' FREQLEN(%4i)' % diff
            dvctr += 1
        if d['received'][ctr]:
            prtstr += ' RECV'
        if d['pkt_disc'][ctr]:
            prtstr += ' DISC_ERR'
            errors['disc'] += 1
        if d['dest_err'][ctr]:
            prtstr += ' DEST_ERR'
            errors['dest'] += 1

        dlast = d32
        if verbose:
            print(prtstr)
    if freqlens.keys() != [1024]:
        errors['freqlens'] = 1
        if verbose:
            print('Freq pkt len errors: ', freqlens)
    return d, errors


def read_xeng_data(f, data=None, verbose=False):
    if data is None:
        d = f.snapshots.sys0_snap_xeng_ss.read(
            man_valid=False, circular_capture=False)['data']
    else:
        d = data
    errors = {}
    syncs = 0
    prev_data = (-1, -1)
    for ctr in range(len(d['data'])):
        prtstr = '%5i' % ctr
        prtstr += ' mcnt(%16i)' % d['mcnt'][ctr]
        prtstr += ' data(%16i)' % d['data'][ctr]
        if d['sync'][ctr]:
            prtstr += ' SYNC'
            syncs += 1
        if d['valid'][ctr]:
            prtstr += ' DV'
        if d['data'][ctr] != prev_data[0]:
            prtstr += ' NEW_DATA(%i, %i)' % (d['data'][ctr] - prev_data[0],
                                             ctr - prev_data[1])
            prev_data = (d['data'][ctr], ctr)
        if verbose:
            print(prtstr)
    if verbose:
        print('Found %i syncs.' % syncs)
    return d, errors


def read_data(f, data=None, verbose=False):
    if data is None:
        f.registers.gbesnap_control.write(arm=False)
        f.snapshots.gbe_in_msb_ss.arm(man_valid=False, man_trig=False)
        f.snapshots.gbe_in_lsb_ss.arm(man_valid=False, man_trig=False)
        f.snapshots.gbe_in_misc_ss.arm(man_valid=False, man_trig=False)
        f.registers.gbesnap_control.write(arm=True)
        d = f.snapshots.gbe_in_msb_ss.read(arm=False)['data']
        d.update(f.snapshots.gbe_in_lsb_ss.read(arm=False)['data'])
        d.update(f.snapshots.gbe_in_misc_ss.read(arm=False)['data'])
        f.registers.gbesnap_control.write(arm=False)
    else:
        d = data
    # convert the data from 256-bit to 64-bit
    pkt64 = {'data': [], 'eof': [], 'valid': [], 'src_ip': [], 'pktfreq': [],
             'src_port': []}
    for ctr in range(len(d['d_msb'])):
        pkt64['data'].append(d['d_msb'][ctr] >> 64)
        pkt64['data'].append(d['d_msb'][ctr] & ((2**64)-1))
        pkt64['data'].append(d['d_lsb'][ctr] >> 64)
        pkt64['data'].append(d['d_lsb'][ctr] & ((2 ** 64) - 1))
        pkt64['eof'].extend([0, 0, 0, d['eof'][ctr]])
        try:
            pkt64['valid'].extend([d['valid_raw'][ctr]] * 4)
        except KeyError:
            pkt64['valid'].extend([d['valid'][ctr]] * 4)
        pkt64['src_ip'].extend([d['src_ip'][ctr]] * 4)
        pkt64['src_port'].extend([d['src_port'][ctr]] * 4)
        try:
            pkt64['pktfreq'].extend([d['pktfreq'][ctr]] * 4)
        except KeyError:
            pkt64['pktfreq'].extend([-1] * 4)
    try:
        gbe_packets = casperfpga.Snap.packetise_snapdata(pkt64)
    except IndexError as e:
        print('ERROR: %s' % e.message)
        for k in pkt64.keys():
            print('%s: %i' % (k, len(pkt64[k])))
        import IPython
        IPython.embed()
        raise RuntimeError
    for pkt in gbe_packets:
        if len(pkt['data']) != EXPECTED_PKT_LEN:
            raise RuntimeError('Packet length error: %i != %i' % (
                len(pkt), EXPECTED_PKT_LEN))
    # print('Found %i GBE packets in snapshot data.' % len(gbe_packets))
    spead_processor = casperspead.SpeadProcessor(None, None, None, None)
    spead_processor.process_data(gbe_packets)
    errors = {'dest_error': []}
    for ctr, pkt in enumerate(spead_processor.packets):
        xeng_id = pkt.headers[0x4103] / 256
        tvg_freq = pkt.data[0] & 0xffff
        packet_offset = pkt.headers[0x3] / 1024
        prtstr = '%3i' % ctr
        prtstr += ' heap_id(%12x)' % pkt.headers[0x1]
        prtstr += ' time(%12x)' % pkt.headers[0x1600]
        prtstr += ' offset_bytes(%6i)' % pkt.headers[0x3]
        prtstr += ' offset_packets(%3i)' % packet_offset
        prtstr += ' ant_id(%i)' % pkt.headers[0x4101]
        prtstr += ' x_freq_base(%4i)' % pkt.headers[0x4103]
        prtstr += ' xeng_id(%2i)' % xeng_id
        prtstr += ' tvg_freq(%4i)' % tvg_freq
        if packet_offset + pkt.headers[0x4103] != tvg_freq:
            errors['dest_error'].append(ctr)
            prtstr += ' DEST_ERROR'
        if verbose:
            print(prtstr)
    got_error = False
    for k in errors:
        if len(errors[k]) > 0:
            got_error = True
            break

    return d, got_error, errors


def get_status_regs(xhosts):
    data = {
        'reord_status': [],
        'vacc_status': [],
        'status': [],
        'pack_status': [],
    }
    for ctr in range(4):
        for k in data:
            d = FPGAS_OP(
                xhosts, 5,
                lambda f: f.registers['%s%i' % (k, ctr)].read()['data'])
            data[k].append(d)
    prtstr = '%20s' % ''
    for host in xhosts:
        prtstr += '%30s' % host.host
    prtstr += '\n'
    for keyset in data.values():
        for k in keyset[0][xhosts[0].host]:
            prtstr += '%20s' % k
            for host in xhosts:
                valstr = ''
                for ctr in range(4):
                    valstr += '%s,' % keyset[ctr][host.host][k]
                prtstr += '%30s' % valstr[0:-1]
            prtstr += '\n'
    return prtstr

# # this enables the TVG AFTER the CT - so it makes a ramp 2 ** 20 long
# # but INTERLEAVED over the different x-engines.
# # so one x-engine will receiver 0-7 in one section of the ramp, then 8-15 on
# # another distant bit. So each chunk of 8 frequencies is
# # (8 * 256 * 16) = 32768 apart on the TVG ramp.
# FPGAS_OP(fhosts, 5, lambda f: f.registers.ct_control0.write(tvg_en2=1))
#
# # read on read/write or both
# DV_MUX = 1
# FPGAS_OP(xhosts, 5,
#          lambda f: f.registers.vacctvg_control.write(reord_snap_dv_mux=DV_MUX))
#
# # select an x-engine
# f = None
# for host in xhosts:
#     if host.host == 'skarab02030C-01':
#         f = host
#         break
#
#
# def setbrdid(f):
#     f.brdid = f.registers.board_id.read()['data']['reg']
# FPGAS_OP(xhosts, 5, setbrdid)

while True:
    # data = FPGAS_OP(xhosts, 5, analyse_reord_write)
    # errs = False
    # for host in xhosts:
    #     d = data[host.host]
    #     if sum(d[1].values()) > 0:
    #         read_reord_data(xhosts[0], d[0], True)
    #         print('%s has reord errors' % host.host)
    #         errs = True
    #         break
    print('%i\n%s' % (time.time(), get_status_regs(xhosts)))
    errs = False
    if errs:
        break
    time.sleep(1)

raise RuntimeError

loopctr = 0
alldone = False
host_errors = []
while True:
    host_errors = []
    try:
        for f in xhosts:
            data, error, errors = read_data(f)
            if error:
                host_errors.append(f.host)
                print('*' * 50)
                print(f.host)
                read_data(f, data, True)
                print('*' * 50)
                alldone = True
    except KeyboardInterrupt:
        alldone = True
    loopctr += 1
    print('%i: %s' % (time.time(), loopctr))
    if alldone:
        break
print(host_errors)

import IPython
IPython.embed()

# end
