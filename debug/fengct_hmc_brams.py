import time
import feng_utils
import struct


hosts = feng_utils.setup_hosts()
# feng_utils.ct_tvg(hosts, 1)
feng_utils.print_err_regs(hosts)
# feng_utils.bypass_cd(hosts, 1)

while True:
    try:
        feng_utils.print_err_regs(hosts)
        time.sleep(1)
    except KeyboardInterrupt:
        break

findex = 0

f = hosts[findex]

ct_sync = (f.registers.ct_sync_time_msw.read()['data']['reg'] << 32) + \
          f.registers.ct_sync_time_lsw.read()['data']['reg']
pack_sync = (f.registers.pack_sync_time_msw.read()['data']['reg'] << 32) + \
            f.registers.pack_sync_time_lsw.read()['data']['reg']
print('CT sync time: %s' % ct_sync)
print('Pack sync time: %s' % pack_sync)
print('Diff: %i' % (pack_sync - ct_sync))
print('\nCtrl+C to continue...\n')
while True:
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        break


def read_bram(name):
    data = f.read(name, 4096 * 4)
    data = struct.unpack('>4096I', data)
    return data


def read_all():
    qt_out = f.read('qt_sync_out', 4096 * 2)
    qt_out = struct.unpack('>4096H', qt_out)
    hmc_in = read_bram('hmc_in_bram')
    hmc_out = read_bram('hmc_out_bram')
    obuf_out = read_bram('obuf_out_bram')
    obuf_out1 = f.read('obuf_out_bram1', 4096)
    obuf_out1 = struct.unpack('>4096B', obuf_out1)
    pack_in = f.read('pack_in_sbram', 32768 * 8)
    pack_in = struct.unpack('>32768Q', pack_in)
    return qt_out, hmc_in, hmc_out, obuf_out, obuf_out1, pack_in

qt_out, hmc_in, hmc_out, obuf_out, obuf_out1, pack_in = read_all()
read_time = int(time.time())


def print_qt_sync():
    print('*' * 75)
    rvdict = {
        'sync': [],
        'dv': [],
        'd0': [],
        'd0_msb': [],
    }
    dvctr = 0
    for ctr, dword in enumerate(qt_out):
        sync = (dword >> 14) & 0x01
        d0_msb = (dword >> 13) & 0x01
        d0 = (dword >> 1) & 0xfff
        dv = (dword >> 0) & 0x01
        prtstr = '%5i' % ctr
        prtstr += ' sync(%i) dv(%i) d0(%4i) d0_msb(%i) %i' % (
            sync, dv, d0, d0_msb, dvctr)
        print(prtstr)
        if dv:
            dvctr += 1
        if sync:
            dvctr = 0
        rvdict['sync'].append(sync)
        rvdict['dv'].append(dv)
        rvdict['d0'].append((d0_msb << 15) + d0)
    feng_utils.save_to_mat(rvdict, 'qt_out_%i.mat' % read_time)


def print_hmc_in():
    # HMC in
    print('*' * 75)
    rvdict = {
        'sync': [],
        'dv': [],
        'd0': [],
        'd1': [],
        'd0_msb': [],
        'd1_msb': [],
    }
    dvctr = 0
    for ctr, dword in enumerate(hmc_in):
        sync = dword >> 27
        dv = (dword >> 26) & 0x01
        d0 = (dword >> 14) & 0xfff
        d1 = (dword >> 2) & 0xfff
        d0_msb = (dword >> 1) & 0x01
        d1_msb = (dword >> 0) & 0x01
        prtstr = '%5i' % ctr
        prtstr += ' sync(%i) dv(%i) d0(%4i) d1(%4i) d0_msb(%i) ' \
                  'd1_msb(%i) %i' % (
                    sync, dv, d0, d1, d0_msb, d1_msb, dvctr)
        print(prtstr)
        if dv:
            dvctr += 1
        rvdict['sync'].append(sync)
        rvdict['dv'].append(dv)
        rvdict['d0'].append((d0_msb << 15) + d0)
        rvdict['d1'].append((d1_msb << 15) + d1)
    feng_utils.save_to_mat(rvdict, 'hmc_in_%i.mat' % read_time)


def print_hmc_out():
    # HMC out
    print('*' * 75)
    rvdict = {
        'sync': [],
        'dv': [],
        'tag': [],
        'd0': [],
    }
    for ctr, dword in enumerate(hmc_out):
        sync = dword >> 23
        dv = (dword >> 22) & 0x01
        tag = (dword >> 13) & 0x1ff
        d0 = (dword >> 1) & 0xfff
        d0_msb = (dword >> 0) & 0x01
        prtstr = '%5i' % ctr
        prtstr += ' sync(%i) dv(%i) tag(%4i) d0(%4i) d0_msb(%i)' % (
            sync, dv, tag, d0, d0_msb)
        rvdict['sync'].append(sync)
        rvdict['dv'].append(dv)
        rvdict['tag'].append(tag)
        rvdict['d0'].append((d0_msb << 15) + d0)
        print(prtstr)
    feng_utils.save_to_mat(rvdict, 'hmc_out_%i.mat' % read_time)


def print_obuf_out():
    # obuf out
    print('*' * 75)
    rvdict = {
        'sync': [],
        'dv': [],
        'pktfreq': [],
        'pktstart': [],
        'd0': [],
    }
    for ctr, dword in enumerate(obuf_out):
        sync = dword >> 27
        dv = (dword >> 26) & 0x01
        d0 = (dword >> 14) & 0xfff
        d0_msb = (dword >> 13) & 0x01
        pktstart = (dword >> 12) & 0x01
        pktfreq = (dword >> 0) & 0xfff
        rd_addr = (obuf_out1[ctr]) & 127
        prtstr = '%5i' % ctr
        prtstr += ' sync(%i) dv(%i) pkt_start(%i) d0(%4i) d0_msb(%i) ' \
                  'pkt_freq(%4i) rd_addr(%3i)' % (
                    sync, dv, pktstart, d0, d0_msb, pktfreq, rd_addr)
        print(prtstr)
        rvdict['sync'].append(sync)
        rvdict['dv'].append(dv)
        rvdict['d0'].append((d0_msb << 15) + d0)
        rvdict['pktfreq'].append(pktfreq)
        rvdict['pktstart'].append(pktstart)
    feng_utils.save_to_mat(rvdict, 'obuf_out_%i.mat' % read_time)


def print_pack_in():
    # obuf out
    print('*' * 75)
    rvdict = {
        'sync': [],
        'dv': [],
        'sync_time': [],
        'd0': [],
    }
    for ctr, dword in enumerate(pack_in):
        sync = dword >> 46
        dv = (dword >> 45) & 0x01
        sync_time = (dword >> 13) & 0xffffffff
        d0 = (dword >> 1) & 0xfff
        d0_msb = (dword >> 0) & 0x01
        prtstr = '%5i' % ctr
        prtstr += ' sync(%i) dv(%i) sync_time(%i) d0(%4i) d0_msb(%i)' % (
            sync, dv, sync_time, d0, d0_msb)
        print(prtstr)
        rvdict['sync'].append(sync)
        rvdict['dv'].append(dv)
        rvdict['d0'].append((d0_msb << 15) + d0)
        rvdict['sync_time'].append(sync_time)
    feng_utils.save_to_mat(rvdict, 'pack_in_%i.mat' % read_time)


import IPython
IPython.embed()

# end
