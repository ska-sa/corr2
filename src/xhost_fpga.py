from logging import INFO
import time
import struct

from host_fpga import FpgaHost
from host_fpga import FpgaHost
from casperfpga.transport_skarab import SkarabTransport
# from corr2LogHandlers import getLogger


class FpgaXHost(FpgaHost):
    """
    A Host, that hosts Xengines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, index, katcp_port=7147, bitstream=None,
                 connect=True, config=None, **kwargs):
        FpgaHost.__init__(self, host=host, katcp_port=katcp_port,
                          bitstream=bitstream, connect=connect, transport=SkarabTransport)
        try:
            descriptor = kwargs['descriptor']
        except KeyError:
            descriptor = 'InstrumentName'

        # This will always be a kwarg
        self.getLogger = kwargs['getLogger']

        logger_name = '{}_xhost-{}-{}'.format(descriptor, str(index), host)
        result, self.logger = self.getLogger(logger_name=logger_name,
                                             log_level=INFO, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        self.logger.debug('Successfully created logger for {}'.format(logger_name))

        self.config = config
        self.index = index
        self.acc_len = None
        self.n_ants = None
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
            self.n_ants = int(ccfg['n_ants'])
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
        #self.x_per_fpga = self._determine_x_per_fpga()
        self._vaccs_per_sec_last_values = [0] * self.x_per_fpga

    @classmethod
    def from_config_source(cls, hostname, index, katcp_port,
                           config_source, **kwargs):
        """

        :param hostname: the hostname of this host
        :param index: which x-host in the system is this?
        :param katcp_port: the katcp port on which to talk to it
        :param config_source: the x-engine config
        :return:
        """
        bitstream = config_source['xengine']['bitstream']
        obj = cls(hostname, index, katcp_port=katcp_port, bitstream=bitstream,
                  connect=True, config=config_source, **kwargs)
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

    def get_status_registers(self):
        """
        Read the status registers on this xhost FPGA
        :return:
        """
        data = {}
        for reg in self.registers:
            if (reg.name.count('status')>0):
                d=reg.read()['data']
                for key,val in d.iteritems():
                    data[reg.name+'_'+key]=val
        return data

    def get_unpack_status(self):
        """
        Returns the SPEAD counters on this FPGA.
        """
        rv = self.registers.spead_status0.read()['data']
        rv.update(self.registers.spead_status1.read()['data'])
        return rv

    def get_hmc_reorder_status(self):
        """
        Retrieve the HMC packet RX reorder status on this board.
        """
        rv={}
        for i in range(3):
            rv.update(self.registers['hmc_pkt_reord_status%i'%i].read()['data'])
        try:
            for i in range(3,4):
                rv.update(self.registers['hmc_pkt_reord_status%i'%i].read()['data'])
        except:
            pass
        return rv

    def get_rx_reorder_status(self):
        """
        Retrieve the RX reorder status from this FPGA's xengines.
        :return:
        """
        data = []
        for ctr in range(0, self.x_per_fpga):
            tmp = self.registers['sys%i_pkt_reord_status' % ctr].read()['data']
            data.append(tmp)
        return data

    def get_pack_status(self, x_indices=None):
        """
        Read the pack block status registers: error count and pkt count
        :param x_indices: a list of x-engine indices to query
        :return: list of dicts
        """
        if x_indices is None:
            x_indices = range(self.x_per_fpga)
        stats = []
        for xnum in x_indices:
            temp = self.registers['sys%i_xeng_pack_out_status' % xnum].read()['data']
            stats.append(temp)
        return stats

    def get_vacc_status(self, x_indices=None):
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
            temp = regs['sys%i_vacc_status' % xnum].read()['data']
            temp.update(timestamp = regs['sys%i_vacc_timestamp' % xnum].read()['data']['vacc_timestamp'])
            stats.append(temp)
        return stats

    def vacc_accumulations_per_second(self, x_indices=None):
        """
        Get the number of accumulatons per second.
        :param x_indices: a list of x-engine indices to read, all if None
        :return: the vaccs per second for the specified xengines on this host
        NOTE: this will be WRONG if the counters wrap!!
        """
        if x_indices is None:
            x_indices = range(0, self.x_per_fpga)
        counts = self.get_vacc_status(x_indices)
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

    def vacc_arm(self):
        """
        Arm the vaccs on this host
        :return:
        """
        self.registers.vacc_time_msw.write(arm='pulse')

    def vacc_set_loadtime(self, load_mcnt):
        """
        Set the vacc load time on this xengine board
        :param loadtime:
        :return:
        """
        ldtime_msw = load_mcnt >> 32
        ldtime_lsw = load_mcnt & 0xffffffff
        self.registers.vacc_time_lsw.write(lsw=ldtime_lsw)
        self.registers.vacc_time_msw.write(msw=ldtime_msw)

    def get_vacc_loadtime(self):
        """
        Get the last VACC loadtime that was set
        :return: a sample clock time
        """
        msw = self.registers.vacc_time_msw.read()['data']['msw'] << 32
        lsw = self.registers.vacc_time_lsw.read()['data']['lsw']
        return msw | lsw

    def vacc_set_acc_len(self, acc_len):
        """
        Set the VACC accumulation length
        :param acc_len:
        :return:
        """
        self.acc_len = acc_len
        self.registers.acc_len.write_int(acc_len)

    def vacc_get_acc_len(self):
        """
        Read the current VACC accumulation length
        :return:
        """
        return self.registers.acc_len.read_uint()

#    def get_beng_status(self, x_indices=None):
#        """
#        Read the beng block status registers: error count and pkt count
#        :param x_indices: a list of x-engine indices to query
#        :return: dict with {error count, pkt count}
#        """
#        if x_indices is None:
#            x_indices = range(self.x_per_fpga)
#        stats = []
#        regs = self.registers
#        for xnum in x_indices:
#            temp0 = regs['bf0_status%d' % xnum].read()['data']
#            temp1 = regs['bf1_status%d' % xnum].read()['data']
#            stats.append((temp0, temp1))
#        return stats
#
    def get_missing_ant_counts(self):
        """
        Get the number of missing packets per input antenna on
        this xhost.
        """
        return struct.unpack('>%iI'%self.n_ants,self.read('missing_ant_cnts',4*self.n_ants,0))

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
