import IPython
import time
import feng_utils
import casperfpga

BASE_IP = int(casperfpga.network.IpAddress('239.2.1.64'))

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


def calc_ip(d, ctr):
    xeng = d['d12'][ctr] / 256
    cip = BASE_IP + xeng + 2
    if cip > int(casperfpga.network.IpAddress('239.2.1.79')):
        cip -= 15
    cip = casperfpga.network.IpAddress(cip)
    return cip


def get_snap_data(fpga, data=None, verbose=False):
    d = data or fpga.snapshots.txips_ss.read(man_trig=True)['data']
    ip_errors = []
    for ctr in range(len(d['dv'])):
        xeng = d['d12'][ctr] / 256
        ip = casperfpga.network.IpAddress(d['ip'][ctr])
        cip = calc_ip(d, ctr)
        prtstr = '%5i d(%5i) xeng(%2i) calc_ip(%s) sent_ip(%s) dv(%i) eof(%i)' \
                 ' gbe_err(%i,%i,%i)' % (
                     ctr, d['d12'][ctr], xeng, cip, ip, d['dv'][ctr],
                     d['eof'][ctr], d['gbe_full'][ctr], d['gbe_of'][ctr],
                     d['gbe_txerr'][ctr])
        if ip != cip:
            prtstr += ' IP_ERR(%s != %s)' % (ip, cip)
            ip_errors.append(ctr)
        if verbose:
            print(prtstr)
    return d, ip_errors

loopctr = 0
while True:
    tic = time.time()
    d = {
        host.host: get_snap_data(host) for host in hosts
    }
    toc = time.time()
    print loopctr, toc, toc - tic
    error = False
    for host in hosts:
        data, errors = d[host.host]
        if len(errors) > 0:
            errpos = errors[0]
            cip = calc_ip(data, errpos)
            txip = casperfpga.network.IpAddress(data['ip'][errpos])
            print host.host, ':', errpos, cip, txip
            # get_snap_data(host, data, True)
            error = True
    if error:
        break

# end
