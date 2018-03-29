import time
import casperfpga
from casperfpga import spead as casperspead

f = casperfpga.KatcpFpga('roach020815')
f.get_system_information()


f.registers.gbesnapctrl.write(snap_arm=0)
f.snapshots.gbedata0_ss.arm(circular_capture=True)
f.snapshots.gbedata1_ss.arm(circular_capture=True)
f.registers.gbesnapctrl.write(snap_arm=1)

time.sleep(2)

d0 = f.snapshots.gbedata0_ss.read(arm=False)['data']
d1 = f.snapshots.gbedata1_ss.read(arm=False)['data']

d0.update(d1)

# for ctr in range(len(d0[d0.keys()[0]])):
#     print('%5i' % ctr,
#     for key in d0.keys():
#         print('%s(%i)' % (key, d0[key][ctr]),
#     print(''

gbe_packets = casperfpga.snap.Snap.packetise_snapdata(d0, 'eof')
gbe_data = []
pkt_lens = []

# print(len(gbe_packets)
pktctr = 1
broken_pkt = -1
for pkt in gbe_packets[1:-1]:
    pktlen = len(pkt['eof'])
    if pktlen not in pkt_lens:
        pkt_lens.append(pktlen)
    gbe_data.append(d0['gbedata'])
    if pkt['gbedata'][0] != 5981908429847920651L:
        print('BROKEN PACKET AT ', pktctr, '-', pktlen)
        broken_pkt = pktctr
    pktctr += 1

if broken_pkt != -1:
    for ctr in range(broken_pkt-2, broken_pkt+3):
        pktdata = gbe_packets[ctr]['gbedata']
        hdrs = casperspead.SpeadPacket.decode_headers(pktdata)[0]
        # print(ctr, pktdata[0]
        # for hdritem, hdrval in hdrs.items():
        #     print('\t', '0x%05x' % hdritem), hdrval

# spead_processor = casperspead.SpeadProcessor(4, '64,48')
# spead_processor.process_data(gbe_data)

import IPython
IPython.embed()

# end
