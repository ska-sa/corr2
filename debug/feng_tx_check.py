import time

import casperfpga
from casperfpga import spead as casperspead

import feng_utils

FPGAS_OP = casperfpga.utils.threaded_fpga_operation

EXPECTED_PKT_LEN = 35 * 4
BASE_IP = casperfpga.network.IpAddress('239.2.1.64')

hosts = feng_utils.setup_fhosts()

# FPGAS_OP(hosts, 5, lambda f: f.registers.control.write(sys_rst='pulse'))


def read_data(f, data=None, verbose=False):
    if data is None:
        f.registers.x_setup.write(snap_arm=False)
        f.snapshots.gbe_in_msb_ss.arm(man_valid=False, man_trig=False)
        f.snapshots.gbe_in_lsb_ss.arm(man_valid=False, man_trig=False)
        f.snapshots.gbe_in_misc_ss.arm(man_valid=False, man_trig=False)
        f.registers.x_setup.write(snap_arm=True)
        d = f.snapshots.gbe_in_msb_ss.read(arm=False)['data']
        d.update(f.snapshots.gbe_in_lsb_ss.read(arm=False)['data'])
        d.update(f.snapshots.gbe_in_misc_ss.read(arm=False)['data'])
        f.registers.x_setup.write(snap_arm=False)
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
    errors = {'dest_error': [], 'sync_error': []}
    for ctr, pkt in enumerate(spead_processor.packets):
        offset_packets = pkt.headers[0x3] / 1024
        xeng_id = pkt.headers[0x4103] / 256
        tvg_freq = pkt.data[0] & 0xfff
        calc_freq = pkt.headers[0x4103] + offset_packets
        prtstr = '%3i' % ctr
        prtstr += ' heap_id(%12x)' % pkt.headers[0x1]
        prtstr += ' time(%12x)' % pkt.headers[0x1600]
        prtstr += ' offset_bytes(%6i)' % pkt.headers[0x3]
        prtstr += ' offset_packets(%3i)' % offset_packets
        prtstr += ' ant_id(%i)' % pkt.headers[0x4101]
        prtstr += ' x_freq_base(%4i)' % pkt.headers[0x4103]
        prtstr += ' xeng_id(%2i)' % xeng_id
        prtstr += ' calc_freq(%4i)' % calc_freq
        prtstr += ' tvg_freq(%4i)' % tvg_freq
        ip = casperfpga.network.IpAddress(gbe_packets[ctr]['src_ip'][0])
        prtstr += ' ip(%s)' % str(ip)
        if tvg_freq != calc_freq:
            prtstr += ' SYNC_ERROR'
            errors['sync_error'].append(ctr)
        if int(ip) != int(BASE_IP) + (pkt.headers[0x4103] / 256):
            prtstr += 'DEST_ERROR'
            errors['dest_error'].append(ctr)
        if verbose:
            print(prtstr)
    got_error = False
    for k in errors:
        if len(errors[k]) > 0:
            got_error = True
            break
    return d, gbe_packets, spead_processor.packets, got_error, errors

# for host in hosts:
#     print('*' * 50)
#     print(host.host)
#     data, gbe_packets, spead_packets, error, errors = read_data(host, None, True)
#     print(errors)
# raise RuntimeError

loopctr = 0
alldone = False
host_errors = []

# new_hosts = []
# for host in hosts:
#     if host.host == 'skarab020309-01':
#         new_hosts.append(host)
#         break
# hosts = new_hosts

while True:
    host_errors = []
    try:
        for f in hosts:
            print(f.host)
            data, gbe_packets, spead_packets, error, errors = read_data(f)
            if error:
                host_errors.append(f.host)
                read_data(f, data, True)
                print(errors)
                alldone = True
    except KeyboardInterrupt:
        alldone = True
    print('%i: %i' % (time.time(), loopctr))
    loopctr += 1
    if alldone:
        break
print('These hosts had errors: ' + str(host_errors))
if len(host_errors) > 0:
    f = None
    for host in hosts:
        if host.host == host_errors[0]:
            f = host
            break
    for ctr in range(10):
        print('%.3f: %s' % (time.time(), f.registers.ct_status2.read()))
        time.sleep(0.2)


import IPython
IPython.embed()

# end
