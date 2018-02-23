from matplotlib import pyplot
import time

import casperfpga
from casperfpga import spead as casperspead

import feng_utils

EXPECTED_PKT_LEN = 35 * 4

hosts = feng_utils.setup_xhosts()


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
        prtstr = '%3i' % ctr
        prtstr += ' heap_id(%12x)' % pkt.headers[0x1]
        prtstr += ' time(%12x)' % pkt.headers[0x1600]
        prtstr += ' offset_bytes(%6i)' % pkt.headers[0x3]
        prtstr += ' offset_packets(%3i)' % (pkt.headers[0x3] / 1024)
        prtstr += ' ant_id(%i)' % pkt.headers[0x4101]
        prtstr += ' x_freq_base(%4i)' % pkt.headers[0x4103]
        prtstr += ' xeng_id(%2i)' % (pkt.headers[0x4103] / 256)
        prtstr += ' tvg_freq(%4i)' % (pkt.data[0] & 0xfff)
        if (pkt.headers[0x3] / 1024) + pkt.headers[0x4103] != (pkt.data[0] & 0xfff):
            errors['dest_error'].append(ctr)
            prtstr += ' DEST_ERROR'
        if verbose:
            print(prtstr)
    got_error = False
    for k in errors:
        if len(errors[k]) > 0:
            got_error = True
            break
    return d, gbe_packets, spead_processor.packets, got_error, errors

loopctr = 0
fig = pyplot.figure()
subplots = [fig.add_subplot(4, 1, fctr+1) for fctr in range(4)]
specdata = {ctr: {} for ctr in range(4)}


def update_specdata():
    alldone = False
    for fctr, f in enumerate(hosts):
        data, gbe_packets, spead_packets, error, errors = read_data(f)
        for ctr, pkt in enumerate(spead_packets):
            freq = (pkt.headers[0x3] / 1024) + pkt.headers[0x4103]
            if freq not in specdata[fctr]:
                specdata[fctr][freq] = [-1, -1]
            for datapkt in pkt.data:
                p0_0_32 = datapkt >> 48
                p1_0_32 = (datapkt >> 32) & 0xffff
                p0_1_32 = (datapkt >> 16) & 0xffff
                p1_1_32 = (datapkt >> 0) & 0xffff
                # if (p0_0_32 != p0_1_32) or (p0_0_32 != freq):
                #     raise RuntimeError('AAAIIEEEEE')
                # if (p1_0_32 != p1_1_32) or (p1_0_32 != freq):
                #     raise RuntimeError('AAAIIEEEEE')
            specdata[fctr][freq][0] = freq
            specdata[fctr][freq][1] = freq
        if error:
            read_data(f, data, True)
            print(f.host)
            alldone = True
            break
        if alldone:
            break


def plot():
    update_specdata()
    plotdata = {fctr: [0] * 4096 for fctr in range(4)}
    for fctr in range(4):
        for freq in specdata[fctr]:
            plotdata[fctr][freq] = specdata[fctr][freq][0]
    for fctr in range(4):
        plt = subplots[fctr]
        plt.cla()
        plt.set_title('%i: %s' % (fctr, hosts[fctr].host))
        plt.grid(True)
        plt.plot(plotdata[fctr])
    lens = [len(specdata[fctr]) for fctr in range(4)]
    print('%i: %s' % (time.time(), lens))
    fig.canvas.draw()
    if sum(lens) < 4096:
        fig.canvas.manager.window.after(10, plot)
    else:
        print('All frequency data accounted for. Done.')

fig.canvas.manager.window.after(10, plot)
pyplot.show()

import IPython
IPython.embed()

# end
