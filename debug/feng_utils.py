import time
import casperfpga
import os
import corr2

FPGAS_OP = casperfpga.utils.threaded_fpga_operation

XFPG = None
FFPG = None
fhosts = None
xhosts = None
correlator = None
N_CHANS = None
N_XENG = None
N_XHOSTS = None

HOST_UUT = 0

# PROBLEM_FREQ = 1040


def setup_hosts():
    global XFPG, FFPG, fhosts, xhosts, correlator, N_CHANS, N_XENG, N_XHOSTS
    correlator = corr2.fxcorrelator.FxCorrelator(
        'steven', config_source=os.environ['CORR2INI'])
    correlator.initialise(program=False, configure=False)
    FFPG = correlator.fhosts[0].bitstream
    XFPG = correlator.xhosts[0].bitstream
    fhosts = correlator.fhosts
    xhosts = correlator.xhosts
    N_CHANS = correlator.n_chans
    N_XENG = len(xhosts) * correlator.x_per_fpga
    N_XHOSTS = len(xhosts)


def setup_fhosts():
    global fhosts
    if fhosts is None:
        setup_hosts()
    return fhosts


def setup_xhosts():
    global xhosts
    if xhosts is None:
        setup_hosts()
    return xhosts


def reset_counters(hosts):
    FPGAS_OP(hosts, 5, lambda f: f.registers.control.write(
        cnt_rst='pulse', gbe_cnt_rst='pulse', status_clr='pulse',
        unpack_debug_reset='pulse'))


def reset_fhosts(hosts):
    FPGAS_OP(hosts, 5, lambda f: f.registers.control.write(sys_rst='pulse'))


def bypass_cd(hosts, bypass=0):
    FPGAS_OP(hosts, 5, lambda f: f.registers.control.write(cd_bypass=bypass))


def tvg_tone_gen(hosts):
    f = hosts[0]
    f.registers.tvg_tone_targets.write(p0=2, p1=0)
    f.registers.tvg_tone_levels.write(p0r=0.5)


def ct_tvg(hosts, enable=1):
    """
    Set up the freq-chan-as-data TVG inside the CT.
    :param hosts:
    :param enable:
    :return:
    """
    if hosts[0].registers.ct_control0.read()['data']['tvg_en'] != enable:
        FPGAS_OP(hosts, 5,
                 lambda f: f.registers.ct_control0.write(
                     tvg_en2=0, tvg_en=enable, rst_err_latch='pulse'))
        time.sleep(1)
        FPGAS_OP(hosts, 5,
                 lambda f: f.registers.control.write(
                     cnt_rst='pulse', unpack_debug_reset='pulse'))
        time.sleep(1)


def print_err_regs(hosts):
    """
    Read a bunch of error registers from SKARAB f-engine hosts.
    :param hosts:
    :return:
    """
    def get_d(fpga, reg_name):
        try:
            return fpga.registers[reg_name].read()['data']
        except AttributeError:
            return {}

    def format_d(d):
        rvstr = '['
        for k in d:
            rvstr += '\'%s\': %4i, ' % (k, d[k])
        rvstr = rvstr[:-2]
        rvstr += ']'
        return rvstr

    def host_regs(fpga):
        prtstr = fpga.host
        for ctr in range(6):
            prtstr += '\n\tCT_CONTROL%i: %s' % (
                ctr, get_d(fpga, 'ct_control%i' % ctr))
        prtstr += '\n\tGBE RX ERR: %s' % get_d(fpga, 'gbe0_rxerrctr')
        prtstr += '\n\tQT STATUS: %s' % get_d(fpga, 'quant_status')
        prtstr += '\n\tQT DV ERR: %s' % get_d(fpga, 'qt_dv_err')
        prtstr += '\n\tCT_STATUS0: %s' % get_d(fpga, 'ct_status0')
        prtstr += '\n\tCT_STATUS1: %s' % get_d(fpga, 'ct_status1')
        d = get_d(fpga, 'ct_status2')
        d.update(get_d(fpga, 'ct_status3'))
        prtstr += '\n\tCT_STATUS2,3: %s' % format_d(d)
        d = get_d(fpga, 'ct_status4')
        d.update(get_d(fpga, 'ct_status5'))
        prtstr += '\n\tCT_STATUS4,5: %s' % format_d(d)
        d = get_d(fpga, 'sync_ctrs1')
        d.update(get_d(fpga, 'sync_ctrs2'))
        prtstr += '\n\tSYNC_CTRS: %s' % format_d(d)
        prtstr += '\n\tCT RATE: %s' % get_d(fpga, 'ct_dv_rate')
        prtstr += '\n\tCT TVG_DATA_OUT: %s' % get_d(fpga, 'ct_dout_err0')
        prtstr += '\n\tCT DV_ERR: %s' % get_d(fpga, 'ct_dv_err')
        prtstr += '\n\tPACK DV ERR: %s' % get_d(fpga, 'pack_dv_err')
        prtstr += '\n\tGBE ERR: %s' % get_d(fpga, 'gbe0_txerrctr')
        return prtstr

    print('=================================')
    d = FPGAS_OP(hosts, 5, (host_regs, [], {}))
    for host in hosts:
        print(d[host.host])


def save_to_mat(data, filename=None):
    import scipy.io as sio
    import numpy as np
    datadict = {
        'simin_%s' % k: {
            'time': [], 'signals': {
                'dimensions': 1, 'values': np.array(data[k], dtype=np.uint32)}
            } for k in data.keys()
    }
    for k in data.keys():
        datadict['simin_%s' % k]['signals']['values'].shape = (len(data[k]), 1)
    if filename is None:
        filename = '/tmp/ctdata_%i.mat' % np.random.randint(1000000)
    sio.savemat(filename, datadict)
    return filename


def decode(word, size=32):
    vals = []
    for ctr in range(size):
        bit = (word >> ctr) & 0x01
        vals.append(bit)
    return vals


def calc_interleaved_freq(raw_freq):
    xid = (raw_freq >> 3) & 0x0f
    xid = ((xid & 3) << 2) + (xid >> 2)
    interleaved_freq = (xid << 8) + (((raw_freq >> 7) & 0x1f) << 3) + \
                       (raw_freq & 0x07)
    return interleaved_freq


# end
