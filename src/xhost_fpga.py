import logging
import time
import casperfpga

from host_fpga import FpgaHost
from host_fpga import FpgaHost
from casperfpga.transport_skarab import SkarabTransport

LOGGER = logging.getLogger(__name__)


class FpgaXHost(FpgaHost):
    """
    A Host, that hosts Xengines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, index, katcp_port=7147, bitstream=None,
                 connect=True, config=None):
        FpgaHost.__init__(self, host=host, katcp_port=katcp_port,
                          bitstream=bitstream, connect=connect, transport=SkarabTransport)
        self.config = config
        self.index = index
        self.acc_len = None
        self.x_per_fpga = None
        self.xeng_accumulation_len = None
        self.n_chans = None
        self.sample_rate_hz = None
        if self.config is not None:
            xcfg = self.config['xengine']
            fcfg = self.config['fengine']
            ccfg = self.config['FxCorrelator']
            self.x_per_fpga = int(xcfg['x_per_fpga'])
            self.acc_len = int(xcfg['accumulation_len'])
            self.xeng_accumulation_len = int(xcfg['xeng_accumulation_len'])
            self.n_chans = int(fcfg['n_chans'])
            self.sample_rate_hz = int(ccfg['sample_rate_hz'])
        self._vaccs_per_sec_last_readtime = None
        self._vaccs_per_sec_last_values = None

    def get_system_information(self, filename=None, fpg_info=None):
        """
        Get information about the design running on the FPGA.
        If filename is given, get it from file, otherwise query
        the host via KATCP.
        :param filename: fpg filename
        :param fpg_info: a tuple containing device_info and
        coreinfo dictionaries
        :return: <nothing> the information is populated in the class
        """
        super(FpgaXHost, self).get_system_information(filename, fpg_info)
        self.x_per_fpga = self._determine_x_per_fpga()
        self._vaccs_per_sec_last_values = [0] * self.x_per_fpga

    @classmethod
    def from_config_source(cls, hostname, index, katcp_port,
                           config_source):
        """

        :param hostname: the hostname of this host
        :param index: which x-host in the system is this?
        :param katcp_port: the katcp port on which to talk to it
        :param config_source: the x-engine config
        :return:
        """
        bitstream = config_source['xengine']['bitstream']
        obj = cls(hostname, index, katcp_port=katcp_port, bitstream=bitstream,
                  connect=True, config=config_source)
        return obj

    def _determine_x_per_fpga(self):
        """
        Query registers to find out how many x-engines there are on this host
        :return:
        """
        regs = self.registers.names()
        if len(regs) <= 0:
            raise RuntimeError('Running this on an unprogrammed FPGA'
                               'is not going to work.')
        ctr = 0
        while ('vacc_status%i' % ctr) in regs:
            ctr += 1
            if ctr == 64:
                break
        LOGGER.info('%s: Found %i X-engines.' % (self.host, ctr))
        return ctr

    def clear_status(self):
        """
        Clear the status registers and counters on this x-engine host
        :return:
        """
        self.registers.control.write(status_clr='pulse', cnt_rst='pulse',
                                     gbe_debug_rst='pulse')

    def host_okay(self):
        """
        Is this host/LRU okay?
        :return:
        """
        if not (self.check_rx_reorder() and self.vacc_okay()):
            LOGGER.error('%s: host_okay() - FALSE.' % self.host)
            return False
        LOGGER.info('%s: host_okay() - TRUE.' % self.host)
        return True

    def get_status_registers(self):
        """
        Read the status registers on this xhost FPGA
        :return:
        """
        data = []
        for ctr in range(self.x_per_fpga):
            _xdata = self.registers['status%i' % ctr].read()['data']
            data.append(_xdata)
        return data

    def get_rx_reorder_status(self):
        """
        Retrieve the RX reorder status from this FPGA's xengines.
        :return:
        """
        data = []
        for ctr in range(0, self.x_per_fpga):
            tmp = self.registers['reord_status%i' % ctr].read()['data']
            regdata = {
                'last_missed_ant%i' % ctr: tmp['last_missed_ant'],
                'sync_cnt%i' % ctr: tmp['sync_cnt'],
                'ercv%i' % ctr: tmp['missed_err_cnt'],
                'etim%i' % ctr: tmp['timeout_err_cnt'],
                'edisc%i' % ctr: tmp['discard_err_cnt'],
            }
            data.append(regdata)
        return data

    def check_rx_reorder(self, sleeptime=1):
        """
        Is this X host reordering received data correctly?
        :param sleeptime - time, in seconds, to wait between register reads
        :return: a list of results for the xengines on this host: 0 no error,
        1 error, 2 warning
        """
        rxregs0 = self.get_rx_reorder_status()
        time.sleep(sleeptime)
        rxregs1 = self.get_rx_reorder_status()
        # compare old and new - rx counts must change and may wrap, error
        # counts must remain the same
        rv = []
        for ctr in range(self.x_per_fpga):
            status1 = rxregs0[ctr]
            status0 = rxregs1[ctr]
            if ((status1['ercv%i' % ctr] != status0['ercv%i' % ctr]) or
                    (status1['etim%i' % ctr] != status0['etim%i' % ctr])):  # or
                # (status1['edisc%i' % ctr] != status0['edisc%i' % ctr])):
                errmsg = '%s: reports reorder errors on engine %i: ercv(%i) ' \
                         'etime(%i) edisc(%i)' % (
                             self.host, ctr,
                             status1['ercv%i' % ctr] - status0['ercv%i' % ctr],
                             status1['etim%i' % ctr] - status0['etim%i' % ctr],
                             status1['edisc%i' % ctr] - status0[
                                 'edisc%i' % ctr])
                LOGGER.error(errmsg)
                rv.append(1)
            elif status1['sync_cnt%i' % ctr] == status0['sync_cnt%i' % ctr]:
                errmsg = '%s: not receiving reordered data.' % self.host
                LOGGER.error(errmsg)
                rv.append(2)
            else:
                LOGGER.info('%s: reordering data okay on engine %i.' % (
                    self.host, ctr))
                rv.append(0)
        return rv

    def pack_get_status(self, x_indices=None):
        """
        Read the pack block status registers: error count and pkt count
        :param x_indices: a list of x-engine indices to query
        :return: dict with {error count, pkt count}
        """
        if x_indices is None:
            x_indices = range(self.x_per_fpga)
        stats = []
        regs = self.registers
        for xnum in x_indices:
            temp = regs['pack_status%d' % xnum].read()['data']
            stats.append(temp)
        return stats

    def vacc_get_status(self, x_indices=None):
        """
        Read the vacc status registers, error count, accumulation count and
        load status
        :param x_indices: a list of x-engine indices to query
        :return: dict with errors, count, arm count and load count
        """
        if x_indices is None:
            x_indices = range(self.x_per_fpga)
        stats = []
        regs = self.registers
        for xnum in x_indices:
            temp = regs['vacc_status%d' % xnum].read()['data']
            xengdata = {
                'errors': temp['err_cnt'],
                'count': temp['acc_cnt'],
                'armcount': temp['arm_cnt'],
                'loadcount': temp['ld_cnt']
            }
            stats.append(xengdata)
        return stats

    def vacc_get_acc_counters(self, x_indices=None):
        """
        Read the vacc counter registers on this host.
        :param x_indices: a list of x-engine indices to query
        :return:
        """
        return [res['count'] for res in self.vacc_get_status(x_indices)]

    def vacc_get_error_detail(self, x_indices=None):
        """
        Read the vacc error counter registers
        :return: dictionary with error counters
        """
        return [res['errors'] for res in self.vacc_get_status(x_indices)]

    def vacc_accumulations_per_second(self, x_indices=None):
        """
        Get the number of accumulatons per second.
        :param x_indices: a list of x-engine indices to read, all if None
        :return: the vaccs per second for the specified xengines on this host
        NOTE: this will be WRONG if the counters wrap!!
        """
        if x_indices is None:
            x_indices = range(0, self.x_per_fpga)
        counts = self.vacc_get_acc_counters(x_indices)
        time1 = time.time()
        vals = [0] * len(counts)
        time2 = time.time()
        newtime = (time1 + time2) / 2.0
        oldtime = self._vaccs_per_sec_last_readtime
        self._vaccs_per_sec_last_readtime = newtime
        if oldtime is None:
            return [-1] * self.x_per_fpga
        timediff = newtime - oldtime
        for xidx in x_indices:
            tic = counts[xidx]
            toc = self._vaccs_per_sec_last_values[xidx]
            self._vaccs_per_sec_last_values[xidx] = tic
            vals[xidx] = tic - toc
        return [v / timediff for v in vals]

    def _get_checktime(self):
        return self.acc_len * self.xeng_accumulation_len * \
            self.n_chans * 2.0 / self.sample_rate_hz * 1.1

    def check_pack(self, x_indices=None):
        """
        ERROR if the errors are incrementing
        WARNING if pkt_cnt is not incrementing
        :param x_indices: a list of the xeng indices to check
        :return:
        """
        if x_indices is None:
            x_indices = range(self.x_per_fpga)
        stat0 = self.pack_get_status(x_indices)
        time.sleep(self._get_checktime())
        stat1 = self.pack_get_status(x_indices)
        rv = []
        for xeng in x_indices:
            if stat0[xeng]['err_cnt'] != stat1[xeng]['err_cnt']:
                msg = '{host}: xeng{index} pack errors incrementing'.format(
                    host=self.host, index=xeng)
                LOGGER.error(msg)
                rv.append(1)
            elif stat0[xeng]['pkt_cnt'] == stat1[xeng]['pkt_cnt']:
                msg = '{host}: xeng{index} not sending packets'.format(
                    host=self.host, index=xeng)
                LOGGER.error(msg)
                rv.append(2)
            else:
                rv.append(0)
        return rv

    def check_vacc(self, x_indices=None):
        """
        ERROR if the errors are incrementing
        WARNING if acc_cnt is not incrementing or arm_cnt != load_cnt
        :param x_indices: a list of the xeng indices to check
        :return:
        """
        if x_indices is None:
            x_indices = range(self.x_per_fpga)
        checktime = self._get_checktime()
        if checktime <= 0:
            raise RuntimeError('Checktime calculated as < 0?')
        stat0 = self.vacc_get_status(x_indices)
        time.sleep(checktime)
        stat1 = self.vacc_get_status(x_indices)
        rv = []
        for xeng in x_indices:
            if stat0[xeng]['errors'] != stat1[xeng]['errors']:
                msg = '{host}: xeng{index} acc errors incrementing'.format(
                    host=self.host, index=xeng)
                LOGGER.error(msg)
                rv.append(1)
            elif stat0[xeng]['count'] == stat1[xeng]['count']:
                msg = '{host}: xeng{index} not accumulating'.format(
                    host=self.host, index=xeng)
                LOGGER.error(msg)
                rv.append(2)
            elif stat0[xeng]['armcount'] != stat1[xeng]['loadcount']:
                msg = '{host}: xeng{index} acc arm != load'.format(
                    host=self.host, index=xeng)
                LOGGER.error(msg)
                rv.append(2)
            else:
                rv.append(0)
        return rv

    def vacc_okay(self, x_index=None):
        """
        Are the vaccs, or one vacc, okay?
        :param x_index: a specific xengine's vacc
        :return: True or False
        """
        regs = self.registers
        if x_index is not None:
            x_indices = [x_index]
        else:
            x_indices = range(self.x_per_fpga)
        # is this an older bitstream with old registers?
        if 'vaccerr0' in regs.names():
            for xnum in x_indices:
                if regs['vaccerr%d' % xnum].read()['data']['reg'] > 0:
                    return False
        elif 'vacc_cnt0' in regs.names():
            for xnum in x_indices:
                if regs['vacc_cnt%d' % xnum].read()['data']['err'] > 0:
                    return False
        else:
            for xnum in x_indices:
                if regs['vacc_status%d' % xnum].read()['data']['err_cnt'] > 0:
                    return False
        return True

    def vacc_check_arm_load_counts(self):
        status = self.vacc_get_status()
        reset_required = False
        for xengctr, xengdata in enumerate(status):
            if xengdata['armcount'] != xengdata['loadcount']:
                # self.logger.warning('vacc on xengine %i needs resetting, '
                #                     'armcount(%i) loadcount(%i).' % (
                #     xengctr, xengdata['armcount'], xengdata['loadcount']))
                reset_required = True
                break
        return reset_required

    def vacc_check_reset_status(self):
        status = self.vacc_get_status()
        reset_okay = True
        for xengctr, xengdata in enumerate(status):
            if (xengdata['armcount'] != 0) or (xengdata['loadcount'] != 0):
                # self.logger.warning('vacc on xengine %i failed to '
                #                     'reset.' % xengctr)
                reset_okay = False
                break
        return reset_okay

    def vacc_reset(self):
        """
        Reset the vector accumulator
        :return:
        """
        self.registers.vacc_time_msw.write(immediate='pulse')
        self.registers.control.write(vacc_rst='pulse')

    def vacc_arm(self):
        """
        Arm the vaccs on this host
        :return:
        """
        self.registers.vacc_time_msw.write(arm='pulse')

    def vacc_set_loadtime(self, loadtime):
        """
        Set the vacc load time on this xengine board
        :param loadtime:
        :return:
        """
        ldtime_msw = loadtime >> 32
        ldtime_lsw = loadtime & 0xffffffff
        self.registers.vacc_time_lsw.write(lsw=ldtime_lsw)
        self.registers.vacc_time_msw.write(msw=ldtime_msw)

    def vacc_get_loadtime(self):
        """
        Get the last VACC loadtime that was set
        :return: a sample clock time
        """
        msw = self.registers.vacc_time_msw.read()['data']['msw'] << 32
        lsw = self.registers.vacc_time_lsw.read()['data']['lsw']
        return msw | lsw

    def vacc_set_acc_len(self, acc_len):
        """

        :param acc_len:
        :return:
        """
        self.acc_len = acc_len
        self.registers.acc_len.write_int(acc_len)

    def vacc_get_acc_len(self):
        """
        Read the current VACC setting
        :return:
        """
        return self.acc_len
        # return self.registers.acc_len.read_uint()

    def beng_get_status(self, x_indices=None):
        """
        Read the beng block status registers: error count and pkt count
        :param x_indices: a list of x-engine indices to query
        :return: dict with {error count, pkt count}
        """
        if x_indices is None:
            x_indices = range(self.x_per_fpga)
        stats = []
        regs = self.registers
        for xnum in x_indices:
            temp0 = regs['bf0_status%d' % xnum].read()['data']
            temp1 = regs['bf1_status%d' % xnum].read()['data']
            stats.append((temp0, temp1))
        return stats

    # def set_accumulation_length(self, accumulation_length, issue_meta=True):
    #     """ Set the accumulation time for the vector accumulator
    #     @param accumulation_length: the accumulation time in spectra.
    #     @param issue_meta: issue SPEAD meta data indicating the change in time
    #     @returns: the actual accumulation time in seconds
    #     """
    #     vacc_len = self.config['vacc_len']
    #     acc_len = self.config['acc_len']
    #     # figure out how many pre-accumulated spectra this is (rounding up)
    #     vacc_len = numpy.ceil(float(vacc_len)/float(acc_len))
    #     self.xeng_acc_len.write(reg=vacc_len)
    #
    #     return vacc_len*acc_len
    #
    # def get_accumulation_length(self):
    #     """ Get the current accumulation time of the vector accumulator
    #     @returns: the accumulation time in spectra
    #     """
    #     acc_len = self.config['acc_len']
    #     vacc_len = self.xeng_acc_len.read()['data']['reg']
    #     return vacc_len * acc_len


class FpgaXHostVaccDebug(FpgaXHost):
    """
    Some extra debug functionality to help with VACC development.
    """

    # methods enable TVG operations
    TVG_KEY_ORIGINAL = {
        'en': 0,
        'data_sel': 1,
        'valid_sel': 2,
        'inj_vector': 3,
        'inj_counter': 4,
        'rst': 5,
    }

    @staticmethod
    def encode_tvg_control(**kwargs):
        """
        Encode arguments to the old tvg_control register.
        :param kwargs:
        :return:
        """
        rv = 0
        for k, p in FpgaXHostVaccDebug.TVG_KEY_ORIGINAL.items():
            if k in kwargs:
                if kwargs[k]:
                    rv |= (1 << p)
        return rv

    @staticmethod
    def decode_tvg_control(raw):
        """
        Decode the raw int from the old tvg_control register to its fields.
        :param raw:
        :return:
        """
        return {
            k: ((raw >> p) & 0x01)
            for k, p in FpgaXHostVaccDebug.TVG_KEY_ORIGINAL.items()
        }

    def tvg_vector(self, location, value):
        """

        :param location: Where should the vector be replaced?
        :param value: What should its value be?
        :return:
        """
        for nx in range(self.x_per_fpga):
            locname = 'sys%i_vacc_tvg0_ins_vect_loc' % nx
            valname = 'sys%i_vacc_tvg0_ins_vect_val' % nx
            self.registers[locname].write_int(location)
            self.registers[valname].write_int(value)

    def tvg_data_value(self, value):
        """

        :param value:
        :return:
        """
        for nx in range(self.x_per_fpga):
            regname = 'sys%i_vacc_tvg0_write' % nx
            self.registers[regname].write_int(value)

    def tvg_control(self, **kwargs):
        """

        :param kwargs:
        :return:
        """
        rawval = self.encode_tvg_control(**kwargs)
        self.registers.tvg_control.write(vacc=rawval)
        rd = self.registers.tvg_control.read()['data']['vacc']
        return self.decode_tvg_control(rd)

# end
