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
                          bitstream=bitstream, connect=connect,transport=SkarabTransport)
        self.config = config
        self.index = index
        if self.config is not None:
            self.vacc_len = int(self.config['xeng_accumulation_len'])
            self.x_per_fpga = int(self.config['x_per_fpga'])
        else:
            self.x_per_fpga = -1
        self._vaccs_per_sec_last_readtime = None
        self._vaccs_per_sec_last_values = None

    def get_system_information(self, filename=None, fpg_info=None):
        """
        Get information about the design running on the FPGA.
        If filename is given, get it from file, otherwise query the host via KATCP.
        :param filename: fpg filename
        :param fpg_info: a tuple containing device_info and coreinfo dictionaries
        :return: <nothing> the information is populated in the class
        """
        super(FpgaXHost, self).get_system_information(filename, fpg_info)
        self.x_per_fpga = self._determine_x_per_fpga()
        self._vaccs_per_sec_last_values = [0] * self.x_per_fpga

    @classmethod
    def from_config_source(cls, hostname, index, katcp_port, config_source):
        bitstream = config_source['bitstream']
        return cls(hostname, index, katcp_port=katcp_port, bitstream=bitstream,
                   connect=True, config=config_source)

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
        LOGGER.info('%s: Found %i X-engines.' % (self.host,ctr))
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
        :return:
        """
        rxregs = self.get_rx_reorder_status()
        time.sleep(sleeptime)
        rxregs_new = self.get_rx_reorder_status()
        rv=True
        # compare old and new - rx counts must change and may wrap, error
        # counts must remain the same
        for ctr in range(0, self.x_per_fpga):
            _new = rxregs_new[ctr]
            _old = rxregs[ctr]
            if _new['sync_cnt%i' % ctr] == _old['sync_cnt%i' % ctr]:
                LOGGER.error('%s: not receiving reordered data.' % self.host)
                rv=False
            if ((_new['ercv%i' % ctr] != _old['ercv%i' % ctr]) or
                    (_new['etim%i' % ctr] != _old['etim%i' % ctr])):  # or
                    # (_new['edisc%i' % ctr] != _old['edisc%i' % ctr])):
                LOGGER.error(
                    '%s: reports reorder errors on engine %i: ercv(%i) etime(%i) edisc(%i)' %
                    (self.host, ctr,
                     _new['ercv%i' % ctr] - _old['ercv%i' % ctr],
                     _new['etim%i' % ctr] - _old['etim%i' % ctr],
                     _new['edisc%i' % ctr] - _old['edisc%i' % ctr]))
                rv=False
            else:
                LOGGER.info('%s: reordering data okay on engine %i.' % (self.host,ctr))
        return rv

        def read_reg(_xengnum):
            if 'vacccnt0' in regs.names():
                return regs['vacccnt%d' % _xengnum].read()['data']['reg']
            elif 'vacc_cnt0' in regs.names():
                return regs['vacc_cnt%d' % _xengnum].read()['data']['cnt']
            elif 'vacc_status0' in regs.names():
                return regs['vacc_status%d' % _xengnum].read()['data']['acc_cnt']

        return [read_reg(xnum) for xnum in xnums]

    def vacc_accumulations_per_second(self, xnums=None):
        """
        Get the number of accumulatons per second.
        :param xnums: a list of x-engine indices to read, all if None
        :return: the vaccs per second for the specified xengines on this host
        NOTE: this will be WRONG if the counters wrap!!
        """
        if xnums is None:
            xnums = range(0, self.x_per_fpga)
        counts = self.vacc_counters_get(xnums)

        time1 = time.time()
        vals = [0] * len(counts)
        time2 = time.time()
        newtime = (time1 + time2) / 2.0
        oldtime = self._vaccs_per_sec_last_readtime
        self._vaccs_per_sec_last_readtime = newtime
        if oldtime is None:
            return [-1] * self.x_per_fpga
        timediff = newtime - oldtime
        for xidx in xnums:
            tic = counts[xidx]
            toc = self._vaccs_per_sec_last_values[xidx]
            self._vaccs_per_sec_last_values[xidx] = tic
            vals[xidx] = tic - toc
        return [v / timediff for v in vals]

    def vacc_okay(self, xnum=-1):
        """
        Are the vaccs, or one vacc, okay?
        :param xnum: a specific xengine's vacc
        :return: True or False
        """
        regs = self.registers
        if xnum > -1:
            xnums = [xnum]
        else:
            xnums = range(self.x_per_fpga)
        # is this an older bitstream with old registers?
        if 'vaccerr0' in regs.names():
            for xnum in xnums:
                if regs['vaccerr%d' % xnum].read()['data']['reg'] > 0:
                    return False
        elif "vacc_cnt0" in regs.names():
            for xnum in xnums:
                if regs['vacc_cnt%d' % xnum].read()['data']['err'] > 0:
                    return False
        else:
            for xnum in xnums:
                if regs['vacc_status%d' % xnum].read()['data']['err_cnt'] > 0:
                    return False
        return True

    def vacc_get_status(self):
        """
        Read the vacc status registers, error count, accumulation count and load status
        :return: tuple with errors, count, arm count and load count
        """
        stats = []
        regs = self.registers
        for xnum in range(0, self.x_per_fpga):
            temp = regs['vacc_status%d' % xnum].read()['data']
            xengdata = {
                'errors': temp['err_cnt'],
                'count': temp['acc_cnt'],
                'armcount': temp['arm_cnt'],
                'loadcount': temp['ld_cnt']}
            stats.append(xengdata)
        return stats

    def vacc_get_error_detail(self):
        """
        Read the vacc error counter registers
        :return: dictionary with error counters
        """
        errors = []
        regs = self.registers
        for xnum in range(0, self.x_per_fpga):
            if 'vaccerr0' in regs.names():
                temp = self.registers['vacc_errors%i' % xnum].read()['data']
            elif 'vacc_status0' in regs.names():
                temp = self.registers['vacc_status%i' % xnum].read()['data']['err_cnt']
            errors.append(temp)
        return errors

    def vacc_check_arm_load_counts(self):
        status = self.vacc_get_status()
        reset_required = False
        for xengctr, xengdata in enumerate(status):
            if xengdata['armcount'] != xengdata['loadcount']:
                # self.logger.warning('vacc on xengine %i needs resetting, '
                #                     'armcount(%i) loadcount(%i).' % (xengctr, xengdata['armcount'],
                #                                                      xengdata['loadcount']))
                reset_required = True
                break
        return reset_required

    def vacc_check_reset_status(self):
        status = self.vacc_get_status()
        reset_okay = True
        for xengctr, xengdata in enumerate(status):
            if (xengdata['armcount'] != 0) or (xengdata['loadcount'] != 0):
                # self.logger.warning('vacc on xengine %i failed to reset.' % xengctr)
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
    #     self.vacc_len.write(reg=vacc_len)
    #
    #     return vacc_len*acc_len
    #
    # def get_accumulation_length(self):
    #     """ Get the current accumulation time of the vector accumulator
    #     @returns: the accumulation time in spectra
    #     """
    #     acc_len = self.config['acc_len']
    #     vacc_len = self.vacc_len.read()['data']['reg']
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
