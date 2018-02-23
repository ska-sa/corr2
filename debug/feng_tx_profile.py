from matplotlib import pyplot

import casperfpga
from casperfpga import spead as casperspead

import feng_utils

FPGAS_OP = casperfpga.utils.threaded_fpga_operation

EXPECTED_PKT_LEN = 35 * 4
BASE_IP = casperfpga.network.IpAddress('239.2.1.64')

hosts = feng_utils.setup_fhosts()


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
    errors = {'dest_error': []}
    for ctr, pkt in enumerate(spead_processor.packets):
        prtstr = '%3i' % ctr
        prtstr += ' heap_id(%12x)' % pkt.headers[0x1]
        prtstr += ' time(%12x)' % pkt.headers[0x1600]
        prtstr += ' offset_bytes(%6i)' % pkt.headers[0x3]
        pkt_offset = pkt.headers[0x3] / 1024
        prtstr += ' offset_packets(%3i)' % pkt_offset
        prtstr += ' ant_id(%i)' % pkt.headers[0x4101]
        prtstr += ' x_freq_base(%4i)' % pkt.headers[0x4103]
        prtstr += ' xeng_id(%2i)' % (pkt.headers[0x4103] / 256)
        tvg_freq = pkt.data[0] & 0xfff
        prtstr += ' tvg_freq(%4i)' % tvg_freq
        if pkt_offset + pkt.headers[0x4103] != tvg_freq:
            errors['dest_error'].append(ctr)
            prtstr += ' DEST_ERROR'
        if verbose:
            print(prtstr)
    got_error = False
    for k in errors:
        if len(errors[k]) > 0:
            got_error = True
            break
    rv = {}
    for pkt in gbe_packets:
        ip = pkt['src_ip'][0]
        freq = pkt['pktfreq'][0]
        if ip not in rv:
            rv[ip] = {}
        if freq not in rv[ip]:
            rv[ip][freq] = 0
        rv[ip][freq] += 1
    return d, rv, got_error

loopctr = 0
fig = pyplot.figure()
txp = {
    host.host: {
        'plot': fig.add_subplot(4, 1, fctr + 1),
        'ips': {
            int(BASE_IP) + xctr: {} for xctr in range(16)
        }
    } for fctr, host in enumerate(hosts)
}


def update_subplots():
    for host, data in txp.items():
        prtstr = '%s:\n' % host
        plt = data['plot']
        plt.cla()
        plt.set_title('%s' % host)
        plt.grid(True)
        for ip in txp[host]['ips']:
            ipdiff = ip - int(BASE_IP)
            target_freq_start = ipdiff * 256
            target_freqs = range(target_freq_start, target_freq_start + 256)
            missing = target_freqs[:]
            error_freqs = []
            for freq in data['ips'][ip]:
                if freq not in target_freqs:
                    if freq not in error_freqs:
                        error_freqs.append(freq)
                missing.pop(missing.index(freq))
            if len(error_freqs) > 0:
                print(host)
                print(missing)
                print(error_freqs)
                print('%s has an error in the data' % host)
                import IPython
                IPython.embed()
                raise RuntimeError('%s has an error in the data' % host)
            misstring = '%s' % len(missing)
            if len(missing) < 20:
                misstring = str(misstring)
            prtstr += '\t%s: %s\n' % (
                casperfpga.network.IpAddress(ip), misstring)

            pltdata = [0] * 256
            for freq in data['ips'][ip]:
                pltdata[freq % 256] = data['ips'][ip][freq]
            plt.plot(pltdata)

        prtstr += '#' * 50
        # print(prtstr)


def update_txp_data():
    try:
        snapdata = FPGAS_OP(hosts, 5, lambda f: read_data(f))
    except RuntimeError:
        return
    for host in hosts:
        data = snapdata[host.host]
        h = host.host
        if data[2]:
            read_data(host, data[0], True)
            raise RuntimeError('%s has an error in the data' % h)
        for ip in data[1]:
            for freq, value in data[1][ip].items():
                if freq not in txp[h]['ips'][ip]:
                    try:
                        txp[h]['ips'][ip][freq] = 0
                    except IndexError:
                        print(h)
                        print(ip)
                        print(freq)
                        print txp
                        raise
                txp[h]['ips'][ip][freq] += value


def plot():
    try:
        update_txp_data()
        update_subplots()
        fig.canvas.draw()
    except KeyboardInterrupt:
        return
    fig.canvas.manager.window.after(10, plot)

fig.canvas.manager.window.after(10, plot)
pyplot.show()

import IPython
IPython.embed()

raise RuntimeError

# end
