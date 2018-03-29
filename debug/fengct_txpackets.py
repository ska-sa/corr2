import time
import feng_utils
import IPython

from casperfpga.network import IpAddress
from casperfpga import snap as caspersnap
from casperfpga import spead as casperspead
from casperfpga import network as caspernetwork

hosts = feng_utils.setup_fhosts()
feng_utils.ct_tvg(hosts, 1)
# feng_utils.print_err_regs(hosts)
# feng_utils.bypass_cd(hosts, 1)

# feng_utils.reset_fhosts(hosts)

while True:
    try:
        feng_utils.print_err_regs(hosts)
        time.sleep(1)
    except KeyboardInterrupt:
        break

print('Board IDs:')
for h in hosts:
    print('\t%s: %s' % (h.host, h.registers.tx_metadata.read()['data']))
    # h.registers.control.write(gbe_txen=0)
    # h.registers.control.write(gbe_rst='pulse')
    # h.registers.control.write(gbe_txen=1)

print('Control regs:')
for h in hosts:
    print('\t%s: %s' % (h.host, h.registers.ct_control0.read()['data']))

# read the packetiser output snapshots
f = hosts[feng_utils.HOST_UUT]

f.registers.ct_debug.write(
    out_stopmux=1,
    # gbe_stopmux=5,
    snap_arm=0,
    snap_trig=0,
    snap_wesel=1,
    snap_trigsel=1,
)


# print f.registers.ct_control4.read()['data']
# print f.registers.ct_control5.read()['data']


ips = []
while True:
    d = f.gbes.gbe0.read_txsnap()
    gbe_packets = caspersnap.Snap.packetise_snapdata(d, 'eof')
    spead_processor = casperspead.SpeadProcessor(None, None, None, None)
    gbe_data = [{'data': pkt['data'], 'ip': pkt['ip']} for pkt in gbe_packets]
    spead_processor.process_data(gbe_data)
    spead_data = []
    for ctr, spead_pkt in enumerate(spead_processor.packets):
        for ip in spead_pkt.ip:
            if ip != spead_pkt.ip[0]:
                raise RuntimeError('IP varies within packet? %i != %i' % (
                    ip, spead_pkt.ip[0]))
        for data in spead_pkt.data:
            if data != spead_pkt.data[0]:
                raise RuntimeError(
                    'Data varies within packet? 0x%016x != 0x%016x' % (
                        data, spead_pkt.data[0]))
        pkt_ip = spead_pkt.ip[0]
        if pkt_ip not in ips:
            if len(ips) == 0:
                ips.append(pkt_ip)
            else:
                pos_ctr = 0
                for ip in ips:
                    if ip < pkt_ip:
                        pos_ctr += 1
                    else:
                        break
                if pos_ctr == 0:
                    start = [pkt_ip]
                    start.extend(ips)
                    ips = start[:]
                else:
                    start = ips[0:pos_ctr]
                    end = ips[pos_ctr:]
                    start.append(pkt_ip)
                    start.extend(end)
                    ips = start[:]
    if len(ips) >= feng_utils.N_XENG:
        break
for ctr, ip in enumerate(ips):
    if ip != ips[0] + ctr:
        print(ips)
        raise RuntimeError('IPs do not follow linearly.')

f_per_x = feng_utils.N_CHANS / feng_utils.N_XENG
xeng_freqs = {}
for xeng_id in range(0, feng_utils.N_XENG):
    range_start = f_per_x * xeng_id
    range_end = f_per_x * xeng_id + f_per_x
    xeng_pkt_range = range(range_start, range_end)
    xeng_freqs[xeng_id] = xeng_pkt_range[:]
    print(xeng_id, range_start, range_end)

print('------------------------------------------------------------------')

# now do it again, collecting freqs sent to each IP
freqs = {ip: {} for ip in ips}
loopctr = 0
spinning = ['|', '/', '-', '\\']
import sys
while True:
    d = f.gbes.gbe0.read_txsnap()
    gbe_packets = caspersnap.Snap.packetise_snapdata(d, 'eof')
    spead_processor = casperspead.SpeadProcessor(None, None, None, None)
    gbe_data = [{'data': pkt['data'], 'ip': pkt['ip']} for pkt in gbe_packets]
    spead_processor.process_data(gbe_data)
    for ctr, spead_pkt in enumerate(spead_processor.packets):
        pkt_ip = spead_pkt.ip[0]
        pkt_data = spead_pkt.data[0]
        for ip in spead_pkt.ip:
            if ip != pkt_ip:
                raise RuntimeError('IP varies within packet? %i != %i' % (
                    ip, pkt_ip))
        for data in spead_pkt.data:
            if data != pkt_data:
                raise RuntimeError(
                    'Data varies within packet? 0x%016x != 0x%016x' % (
                        data, pkt_data))
        xeng_id = ips.index(pkt_ip)
        # print('\n', xeng_id, pkt_data, xeng_freqs[xeng_id][0],
        #       xeng_freqs[xeng_id][-1], '\n')
        pkt_freq = pkt_data & (2**16-1)
        if pkt_freq not in xeng_freqs[xeng_id]:
            print((pkt_data >> 48) & ((2 ** 16) - 1))
            print((pkt_data >> 32) & ((2 ** 16) - 1))
            print((pkt_data >> 16) & ((2 ** 16) - 1))
            print((pkt_data >> 00) & ((2 ** 16) - 1))
            print ips
            print pkt_ip
            print(xeng_id)
            print(pkt_freq)
            print(xeng_freqs[xeng_id][0], xeng_freqs[xeng_id][-1])
            raise RuntimeError('Freq(%i) being sent to xeng(%i), which '
                               'is not correct.' % (pkt_freq, xeng_id))
        if pkt_data not in freqs[pkt_ip]:
            freqs[pkt_ip][pkt_data] = 0
        freqs[pkt_ip][pkt_data] += 1
    loopctr += 1
    if loopctr % 200 == 0:
        print(' %i' % loopctr)
        for ip in ips:
            numfreqs = len(freqs[ip])
            numpkts = 0
            for freq in freqs[ip]:
                numpkts += freqs[ip][freq]
            print('%s: freqs(%5i) pkts(%i)' % (caspernetwork.IpAddress(ip),
                                               numfreqs, numpkts))
    elif loopctr % 2 == 0:
        spindex = (loopctr / 2) % 4
        print '\b\b\b\b\b\b%s' % spinning[spindex],
    sys.stdout.flush()
    # if loopctr % 100 == 0:
    #     print(time.time())

    if loopctr > 1000000:
        break

raise RuntimeError('All done.')


def simple_print_snap(d, limits=None):
    for ctr in range(0, len(d['dv'])):
        prtstr = '%5i' % ctr
        prtstr += ' DV' if d['dv'][ctr] else '   '
        prtstr += ' EOF' if d['eof'][ctr] else '    '
        prtstr += ' OF' if d['of'][ctr] else '   '
        ip = IpAddress(d['ip'][ctr])
        prtstr += ' %s:%i' % (str(ip), d['port'][ctr])
        prtstr += ' %016x' % d['d0'][ctr]
        prtstr += ' %016x' % d['d1'][ctr]
        prtstr += ' %016x' % d['d2'][ctr]
        prtstr += ' %016x' % d['d3'][ctr]
        if limits is not None:
            if ctr < limits[0]:
                continue
        print(prtstr)
        if limits is not None:
            if ctr > limits[1]:
                break


def get_snap_data(d=None, verbose=False):
    if d is None:
        f.registers.ct_debug.write(snap_trig=0)
        for snapctr in range(3):
            f.snapshots['gbe_in%i_ss' % snapctr].arm(
                man_trig=False, man_valid=True)
        f.registers.ct_debug.write(snap_trig='pulse')
        d = {}
        for snapctr in range(3):
            d.update(f.snapshots['gbe_in%i_ss' % snapctr].read(arm=False)['data'])
        d['d0'] = []
        d['d1'] = []
        d['d2'] = []
        d['d3'] = []
        for ctr in range(len(d['dv'])):
            d['d0'].append(d['d_msb'][ctr] >> 64)
            d['d1'].append(d['d_msb'][ctr] & ((2**64)-1))
            d['d2'].append(d['d_lsb'][ctr] >> 64)
            d['d3'].append(d['d_lsb'][ctr] & ((2**64)-1))
        d.pop('d_msb')
        d.pop('d_lsb')
    # process the data
    ctr = 0
    while d['dv'][ctr] == 1:
        ctr += 1
    for k in d.keys():
        d[k] = d[k][ctr:]
    packets = None
    try:
        packets = Snap.packetise_snapdata(d, 'eof', 35, 'dv')
    except Exception as exc:
        print(exc.message)
        IPython.embed()
    return packets
    for ctr in range(0, len(d['dv'])):
        prtstr = '%5i' % ctr
        prtstr += ' DV' if d['dv'][ctr] else '   '
        prtstr += ' EOF' if d['eof'][ctr] else '    '
        prtstr += ' OF' if d['of'][ctr] else '   '
        ip = IpAddress(d['ip'][ctr])
        prtstr += ' %s:%i' % (str(ip), d['port'][ctr])
        prtstr += ' %016x' % d['d0'][ctr]
        prtstr += ' %016x' % d['d1'][ctr]
        prtstr += ' %016x' % d['d2'][ctr]
        prtstr += ' %016x' % d['d3'][ctr]
        print(prtstr)
    f.registers.ct_debug.write(snap_trig=1)
    raise RuntimeError

packets = get_snap_data()
for pkt_idx, pkt in enumerate(packets):
    for port in pkt['port'][1:]:
        if port != pkt['port'][0] or port != 7148:
            print('Port error in packet {}'.format(pkt_idx))
            break
    for ip in pkt['ip'][1:]:
        if ip != pkt['ip'][0]:
            print('IP error in packet {}'.format(pkt_idx))
            break

for pkt in packets:
    pkt['data'] = []
    for ctr in range(len(pkt['d0'])):
        pkt['data'].append(pkt['d0'][ctr])
        pkt['data'].append(pkt['d1'][ctr])
        pkt['data'].append(pkt['d2'][ctr])
        pkt['data'].append(pkt['d3'][ctr])

spead_processor = spead.SpeadProcessor()
spead_processor.process_data(packets)

# print the SPEAD packets
for ctr, pkt in enumerate(spead_processor.packets):
    header_str = ''
    for header in pkt.headers:
        if header == 0:
            continue
        header_str += ' 0x%04x[%s]' % (header, str(pkt.headers[header]))
    ip = IpAddress(pkt.ip[0])
    print('%4i' % ctr, header_str[1:], 'freq(%4i)' % (pkt.data[0] >> 48), str(ip))

print 'boop'

IPython.embed()
