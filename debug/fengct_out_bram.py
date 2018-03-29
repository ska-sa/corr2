import time
import feng_utils
import struct
from casperfpga.network import IpAddress

hosts = feng_utils.setup_hosts()
# feng_utils.ct_tvg(hosts, 1)
# feng_utils.print_err_regs(hosts)
# feng_utils.bypass_cd(hosts, 1)

findex = 0

f = hosts[findex]

ct_sync = f.registers.ct_sync_time.read()['data']['reg']
pack_sync = f.registers.pack_sync_time.read()['data']['reg']
print('CT sync time: %s' % ct_sync)
print('Pack sync time: %s' % pack_sync)
print('Diff: %i' % (pack_sync - ct_sync))
print('\nCtrl+C to continue...\n')

while True:
    try:
        time.sleep(1)
    except KeyboardInterrupt:
        break


def read_all():
    out0 = f.read('gbe_out_bram0', 32768 * 8)
    out1 = f.read('gbe_out_bram1', 32768 * 16)
    out2 = f.read('gbe_out_bram2', 32768 * 16)
    out0 = struct.unpack('>32768Q', out0)
    out1_raw = struct.unpack('>65536Q', out1)
    out2_raw = struct.unpack('>65536Q', out2)
    out1 = []
    out2 = []
    for ctr in range(0, len(out1_raw), 2):
        out1.append((out1_raw[ctr], out1_raw[ctr + 1]))
        out2.append((out2_raw[ctr], out2_raw[ctr + 1]))
    return out0, out1, out2

out0, out1, out2 = read_all()
read_time = int(time.time())


def print_out_sync():
    print('*' * 75)
    dvctr = 0
    for ctr in range(len(out0)):
        dv = (out0[ctr] >> 0) & 0x01
        of = (out0[ctr] >> 1) & 0x01
        eof = (out0[ctr] >> 2) & 0x01
        port = (out0[ctr] >> 3) & 0xffff
        ip = (out0[ctr] >> 19) & 0xffffffff
        ip = IpAddress(ip)
        sync = (out0[ctr] >> 51) & 0x01
        word_msb = (out1[ctr][0] << 64) + out1[ctr][1]
        word_lsb = (out2[ctr][0] << 64) + out2[ctr][1]
        prtstr = '%5i' % ctr
        prtstr += ' sync(%i) dv(%i) eof(%i) of(%i) ip(%s:%i) d(%032x, %032x) ' \
                  'freq(%i)' % (
                    sync, dv, eof, of, str(ip), port, word_msb,
                    word_lsb, word_lsb & 0xfff)
        if eof:
            prtstr += ' EOF'
        if of:
            prtstr += ' ERROR_OF'
        print(prtstr)
        if dv:
            dvctr += 1
        if sync:
            dvctr = 0

import IPython
IPython.embed()

# end
