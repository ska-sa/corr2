__author__ = 'paulp'

import time
import logging
import struct

from host_fpga import FpgaHost

LOGGER = logging.getLogger(__name__)

class FpgaFHost(FpgaHost):
    """
    A Host, that hosts Fengines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, boffile=None, connect=True, config=None):
        FpgaHost.__init__(self, host, katcp_port=katcp_port, boffile=boffile, connect=connect)
        self._config = config
        self.data_sources = []  # a list of DataSources received by this f-engine host
        self.eqs = {}  # a dictionary, indexed on source name, containing tuples of poly and bram name
        if config is not None:
            self.num_fengines = int(config['f_per_fpga'])
            self.ports_per_fengine = int(config['ports_per_fengine'])
            self.fft_shift = int(config['fft_shift'])
            self.n_chans = int(config['n_chans'])
        else:
            self.num_fengines = None
            self.ports_per_fengine = None
            self.fft_shift = None
            self.n_chans = None

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile, connect=True, config=config_source)

    def clear_status(self):
        """
        Clear the status registers and counters on this f-engine host
        :return:
        """
        self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse', cnt_rst='pulse')

    def ct_okay(self, sleeptime=1):
        """
        Is the corner turner working?
        :return: True or False,
        """
        ct_ctrs0 = self.registers.ct_ctrs.read()['data']
        time.sleep(sleeptime)
        ct_ctrs1 = self.registers.ct_ctrs.read()['data']

        err0_diff = ct_ctrs1['ct_err_cnt0'] - ct_ctrs0['ct_err_cnt0']
        err1_diff = ct_ctrs1['ct_err_cnt1'] - ct_ctrs0['ct_err_cnt1']
        parerr0_diff = ct_ctrs1['ct_parerr_cnt0'] - ct_ctrs0['ct_parerr_cnt0']
        parerr1_diff = ct_ctrs1['ct_parerr_cnt1'] - ct_ctrs0['ct_parerr_cnt1']

        if err0_diff or err1_diff or parerr0_diff or parerr1_diff:
            LOGGER.error('%s: ct_status() - FALSE, CT error.' % self.host)
            return False
        LOGGER.info('%s: ct_status() - TRUE.' % self.host)
        return True

    def host_okay(self):
        """
        Is this host/LRU okay?
        :return:
        """
        if (not self.check_rx()) or (not self.ct_okay()):
            LOGGER.error('%s: host_okay() - FALSE.' % self.host)
            return False
        LOGGER.info('%s: host_okay() - TRUE.' % self.host)
        return True

    def check_rx_reorder(self):
        """
        Is this F host reordering received data correctly?
        :return:
        """
        def get_gbe_data():
            data = {}
            reorder_ctrs = self.registers.reorder_ctrs.read()['data']
            data['mcnt_relock'] = reorder_ctrs['mcnt_relock']
            data['timerror'] = reorder_ctrs['timestep_error']
            data['discard'] = reorder_ctrs['discard']
            num_tengbes = len(self.tengbes)
            for gbe in range(num_tengbes):
                data['pktof_ctr%i' % gbe] = reorder_ctrs['pktof%i' % gbe]
            for pol in range(0, 2):
                data['recverr_ctr%i' % pol] = reorder_ctrs['recverr%i' % pol]
            return data
        _sleeptime = 1
        rxregs = get_gbe_data()
        time.sleep(_sleeptime)
        rxregs_new = get_gbe_data()
        num_tengbes = len(self.tengbes)
        if num_tengbes < 1:
            raise RuntimeError('F-host with no 10gbe cores %s' % self.host)
        for gbe in range(num_tengbes):
            if rxregs_new['pktof_ctr%i' % gbe] != rxregs['pktof_ctr%i' % gbe]:
                raise RuntimeError('F host %s packet overflow on interface gbe%i. %i -> %i' % (
                    self.host, gbe, rxregs_new['pktof_ctr%i' % gbe], rxregs['pktof_ctr%i' % gbe]))
        for pol in range(0, 2):
            if rxregs_new['recverr_ctr%i' % pol] != rxregs['recverr_ctr%i' % pol]:
                raise RuntimeError('F host %s pol %i reorder count error. %i -> %i' % (
                    self.host, pol, rxregs_new['recverr_ctr%i' % pol], rxregs['recverr_ctr%i' % pol]))
        if rxregs_new['mcnt_relock'] != rxregs['mcnt_relock']:
            raise RuntimeError('F host %s mcnt_relock is changing. %i -> %i' % (
                self.host, rxregs_new['mcnt_relock'], rxregs['mcnt_relock']))
        if rxregs_new['timerror'] != rxregs['timerror']:
            raise RuntimeError('F host %s timestep error is changing. %i -> %i' % (
                self.host, rxregs_new['timerror'], rxregs['timerror']))
        if rxregs_new['discard'] != rxregs['discard']:
            raise RuntimeError('F host %s discarding packets. %i -> %i' % (
                self.host, rxregs_new['discard'], rxregs['discard']))
        LOGGER.info('%s: is reordering data okay.' % self.host)
        return True

    def read_spead_counters(self):
        """
        Read the SPEAD rx and error counters for this F host
        :return:
        """
        rv = []
        spead_ctrs = self.registers.spead_ctrs.read()['data']
        for core_ctr in range(0, len(self.tengbes)):
            counter = spead_ctrs['rx_cnt%i' % core_ctr]
            error = spead_ctrs['err_cnt%i' % core_ctr]
            rv.append((counter, error))
        return rv

    def get_local_time(self):
        """
        Get the local timestamp of this board, received from the digitiser
        :return: time in samples since the digitiser epoch
        """
        first_msw = self.registers.local_time_msw.read()['data']['timestamp_msw']
        while self.registers.local_time_msw.read()['data']['timestamp_msw'] == first_msw:
            time.sleep(0.01)
        lsw = self.registers.local_time_lsw.read()['data']['timestamp_lsw']
        msw = self.registers.local_time_msw.read()['data']['timestamp_msw']
        assert msw == first_msw + 1  # if this fails the network is waaaaaaaay slow
        return (msw << 32) | lsw

    def add_source(self, data_source):
        """
        Add a new data source to this fengine host
        :param data_source: A DataSource object
        :return:
        """
        # check that it doesn't already exist before adding it
        for source in self.data_sources:
            assert source.source_number != data_source.source_number
            assert source.name != data_source.name
        self.data_sources.append(data_source)

    def get_source_eq(self, source_name=None):
        """
        Return a dictionary of all the EQ settings for the sources allocated to this fhost
        :return:
        """
        if source_name is not None:
            return self.eqs[source_name]
        return self.eqs

    def read_eq(self, eq_bram=None, eq_name=None):
        """
        Read a given EQ BRAM.
        :param eq_bram:
        :return: a list of the complex EQ values from RAM
        """
        if eq_bram is None and eq_name is None:
            raise RuntimeError('Cannot have both tuple and name None')
        if eq_name is not None:
            eq_bram = 'eq%i' % self.eqs[eq_name][1]
        # eq vals are packed as 32-bit complex (16 real, 16 imag)
        eqvals = self.read(eq_bram, self.n_chans*4)
        eqvals = struct.unpack('>%ih' % (self.n_chans*2), eqvals)
        eqcomplex = []
        for ctr in range(0, len(eqvals), 2):
            eqcomplex.append(eqvals[ctr] + (1j * eqvals[ctr+1]))
        return eqcomplex

    def write_eq_all(self):
        """
        Write the self.eq variables to the device SBRAMs
        :return:
        """
        for eqname in self.eqs.keys():
            LOGGER.debug('%s: writing EQ %s' % (self.host, eqname))
            self.write_eq(eq_name=eqname)

    def write_eq(self, eq_tuple=None, eq_name=None):
        """
        Write a given complex eq to the given SBRAM.

        Specify either eq_tuple, a combination of sbram_name and value(s), OR eq_name, but not both. If eq_name
                is specified, the sbram_name and eq value(s) are read from the self.eqs dictionary.

        :param eq_tuple: a tuple of an integer, complex number or list or integers or complex numbers and a sbram name
        :param eq_name: the name of an eq to use, found in the self.eqs dictionary
        :return:
        """
        if eq_tuple is None and eq_name is None:
            raise RuntimeError('Cannot have both tuple and name None')
        if eq_name is not None:
            if eq_name not in self.eqs.keys():
                raise ValueError('Unknown source name %s' % eq_name)
            eq_poly = self.eqs[eq_name]['eq']
            eq_bram = 'eq%i' % self.eqs[eq_name]['bram_num']
        else:
            eq_poly = eq_tuple[0]
            eq_bram = eq_tuple[1]
        if len(eq_poly) == 1:
            # single complex
            creal = self.n_chans * [int(eq_poly[0].real)]
            cimag = self.n_chans * [int(eq_poly[0].imag)]
        elif len(eq_poly) == self.n_chans:
            # list - one for each channel
            creal = [num.real for num in eq_poly]
            cimag = [num.imag for num in eq_poly]
        else:
            # polynomial
            raise NotImplementedError('Polynomials are not yet complete.')
        coeffs = (self.n_chans * 2) * [0]
        coeffs[0::2] = creal
        coeffs[1::2] = cimag
        ss = struct.pack('>%ih' % (self.n_chans * 2), *coeffs)
        self.write(eq_bram, ss, 0)
        LOGGER.debug('%s: wrote EQ to sbram %s' % (self.host, eq_bram))
        return len(ss)

    def set_fft_shift(self, shift_schedule=None, issue_meta=True):
        """
        Set the FFT shift schedule.
        :param shift_schedule: int representing bit mask. '1' represents a shift for that stage. First stage is MSB.
        Use default if None provided
        :param issue_meta: Should SPEAD meta data be sent after the value is changed?
        :return: <nothing>
        """
        if shift_schedule is None:
            shift_schedule = self.fft_shift
        self.registers.fft_shift.write(fft_shift=shift_schedule)

    def get_fft_shift(self):
        """
        Get the current FFT shift schedule from the FPGA.
        :return: integer representing the FFT shift schedule for all the FFTs on this engine.
        """
        return self.registers.fft_shift.read()['data']['fft_shift']

    def get_quant_snapshot(self, source_name=None):
        """
        Read the post-quantisation snapshot for a given source
        :return:
        """
        raise NotImplementedError
        """
        source_names = []
        if source_name is None:
            for src in self.data_sources:
                source_names.append(src.name)
        else:
            for src in self.data_sources:
                if src.name == source_name:
                    source_names.append(source_name)
                    break
        if len(source_names) == 0:
            raise RuntimeError('Could not find source %s on this f-engine host or no sources given' % source_name)
        targetsrc.host.snapshots.snapquant_ss.arm()
        targetsrc.host.registers.control.write(snapquant_arm='pulse')
        sdata = targetsrc.host.snapshots.snapquant_ss.read(arm=False)['data']
        self.snapshots.snapquant_ss.arm()
        self.registers.control.write(snapquant_arm='pulse')
        snapdata = self.snapshots.snapquant_ss.read(arm=False)['data']
        raise RuntimeError
        """
        targetsrc = None
        for src in self.fengine_sources:
            if src.name == source_name:
                targetsrc = src
                break
        if targetsrc is None:
            raise RuntimeError('Could not find source %s' % source_name)

        if targetsrc.source_number % 2 == 0:
            snapshot = targetsrc.host.snapshots.snap_quant0_ss
        else:
            snapshot = targetsrc.host.snapshots.snap_quant1_ss

        snapshot.arm()
        sdata = snapshot.read(arm=False)['data']
        compl = []
        for ctr in range(0, len(sdata['real0'])):
            compl.append(complex(sdata['real0'][ctr], sdata['imag0'][ctr]))
            compl.append(complex(sdata['real1'][ctr], sdata['imag1'][ctr]))
            compl.append(complex(sdata['real2'][ctr], sdata['imag2'][ctr]))
            compl.append(complex(sdata['real3'][ctr], sdata['imag3'][ctr]))
        return compl

    def get_pfb_snapshot(self, pol=0):
        # select the pol
        self.registers.control.write(snappfb_dsel=pol)

        # arm the snaps
        self.snapshots.snappfb_0_ss.arm()
        self.snapshots.snappfb_1_ss.arm()

        # allow them to trigger
        self.registers.control.write(snappfb_arm='pulse')

        # read the data
        r0_to_r3 = self.snapshots.snappfb_0_ss.read(arm=False)['data']
        i3 = self.snapshots.snappfb_1_ss.read(arm=False)['data']

        # reorder the data
        p_data = []
        for ctr in range(0, len(i3['i3'])):
            p_data.append(complex(r0_to_r3['r0'][ctr], r0_to_r3['i0'][ctr]))
            p_data.append(complex(r0_to_r3['r1'][ctr], r0_to_r3['i1'][ctr]))
            p_data.append(complex(r0_to_r3['r2'][ctr], r0_to_r3['i2'][ctr]))
            p_data.append(complex(r0_to_r3['r3'][ctr], i3['i3'][ctr]))
        return p_data

    def qdr_okay(self):
        """
        Checks if parity bits on f-eng are zero
        :return: True/False
        """
        for cnt in range(0, 1):
            err = self.registers.ct_ctrs.read()['data']['ct_parerr_cnt%d' % cnt]
            if err == 0:
                LOGGER.info('%s: ct_parerr_cnt%d okay.' % (self.host, cnt))
            else:
                LOGGER.error('%s: ct_parerr_cnt%d not zero.' % (self.host, cnt))
                return False
        LOGGER.info('%s: QDR okay.' % self.host)
        return True

    def check_fft_overflow(self, wait_time=2e-3):
        """
        Checks if pfb counters on f-eng are not incrementing i.e. fft is not overflowing
        :return: True/False
        """
        for cnt in range(0, 1):
            overflow0 = self.registers.pfb_ctrs.read()['data']['pfb_of%d_cnt' % cnt]
            time.sleep(wait_time)
            overflow1 = self.registers.pfb_ctrs.read()['data']['pfb_of%d_cnt' % cnt]
            if overflow0 == overflow1:
                LOGGER.info('%s: pfb_of%d_cnt okay.' % (self.host, cnt))
            else:
                LOGGER.error('%s: pfb_of%d_cnt incrementing.' % (self.host, cnt))
                return False
        LOGGER.info('%s: PFB okay.' % self.host)
        return True

#     def fr_delay_set(self, pol_id, delay=0, delay_rate=0, fringe_phase=0, fringe_rate=0, ld_time=-1, ld_check = True, extra_wait_time = 0):
#         """
#         Configures a given antenna to a delay in seconds using both the coarse and the fine delay. Also configures the fringe rotation components. This is a blocking call. \n
#         By default, it will wait 'till load time and verify that things worked as expected. This check can be disabled by setting ld_check param to False. \n
#         Load time is optional; if not specified, load ASAP.\n
#         \t Fringe offset is in degrees.\n
#         \t Fringe rate is in cycles per second (Hz).\n
#         \t Delay is in seconds.\n
#         \t Delay rate is in seconds per second.\n
#         Notes: \n
#         IS A ONCE-OFF UPDATE (no babysitting by software)\n"""
#         #Fix to fine delay calc on 2010-11-19
# 	if pol_id == 0:
# 		fd_status_reg = self.registers.tl_fd0_status
# 		fd_control_reg = self.registers.tl_fd0_control
# 		fd_control0_reg = self.registers.tl_fd0_control0
# 		cd_status_reg = self.registers.tl_cd0_status
# 		cd_control_reg = self.registers.tl_cd0_control
# 		cd_control0_reg = self.registers.tl_cd0_control0
# 		coarse_delay_reg = self.registers.coarse_delay0
# 		fractional_delay_reg = self.registers.fractional_delay0
# 		delay_delta_reg = self.registers.delay_delta0
# 		phase_offset_reg = self.registers.phase_offset0
# 		phase_offset_delta_reg = self.registers.phase_offset_delta0
# 	else:
# 		fd_status_reg = self.registers.tl_fd1_status
# 		fd_control_reg = self.registers.tl_fd1_control
# 		fd_control0_reg = self.registers.tl_fd1_control0
# 		cd_status_reg = self.registers.tl_cd1_status
# 		cd_control_reg = self.registers.tl_cd1_control
# 		cd_control0_reg = self.registers.tl_cd1_control0
# 		coarse_delay_reg = self.registers.coarse_delay1
# 		fractional_delay_reg = self.registers.fractional_delay1
# 		delay_delta_reg = self.registers.delay_delta1
# 		phase_offset_reg = self.registers.phase_offset1
# 		phase_offset_delta_reg = self.registers.phase_offset_delta1
#
#         fine_delay_bits =       16
#         coarse_delay_bits =     16
#         fine_delay_rate_bits =  16
#         fringe_offset_bits =    16
#         fringe_rate_bits =      16
#         bitshift_schedule =     23
#         min_ld_time = 0.1 # assume we're able to set and check all the registers in 100ms
#         network_latency_adjust = 0.015
#
#         # delays in terms of ADC clock cycles:
#         delay_n = delay * self.sample_rate_hz                   # delay in clock cycles
#         coarse_delay = int(delay_n)                             # delay in whole clock cycles #testing for rev370
#         fine_delay = (delay_n-coarse_delay)                     # delay remainder. need a negative slope for positive delay
#         fine_delay_i = int(fine_delay*(2**(fine_delay_bits)))   # 16 bits of signed data over range 0 to +pi
#
#         fine_delay_rate = int(float(delay_rate) * (2**(bitshift_schedule + fine_delay_rate_bits-1)))
#
#         # figure out the fringe as a fraction of a cycle
#         fr_offset = int(fringe_phase/float(360) * (2**(fringe_offset_bits)))
#         # figure out the fringe rate. Input is in cycles per second (Hz). 1) divide by brd clock rate to get cycles per clock. 2) multiply by 2**20
# 	# TODO adc_demux_factor
# 	feng_clk = (self.sample_rate_hz/8)
#         fr_rate = int(float(fringe_rate) / feng_clk * (2**(bitshift_schedule + fringe_rate_bits-1)))
#
#         # read the arm and load counts - they must increment after the delay has been loaded
# 	status = fd_status_reg.read()
#         arm_count_before = status['arm_count']
#         ld_count_before = status['load_count']
#
#         act_delay = (coarse_delay + float(fine_delay_i)/2**fine_delay_bits)/self.sample_rate_hz
#         act_fringe_offset = float(fr_offset)/(2**fringe_offset_bits)*360
#         act_fringe_rate = float(fr_rate)/(2**(fringe_rate_bits+bitshift_schedule-1))*feng_clk
#         act_delay_rate = float(fine_delay_rate)/(2**(bitshift_schedule + fine_delay_rate_bits-1))
# # TODO
#         if (delay != 0):
#             if (fine_delay_i == 0) and (coarse_delay == 0):
#                 LOGGER.info('Requested delay is too small for this configuration (our resolution is too low). Setting delay to zero.')
#             elif abs(fine_delay_i) > 2**(fine_delay_bits):
#                 raise RuntimeError('Internal logic error calculating fine delays.')
#             elif abs(coarse_delay) > (2**(coarse_delay_bits)):
#                 raise RuntimeError('Requested coarse delay (%es) is out of range (+-%es).' % (float(coarse_delay)/self.sample_rate_hz, float(2**(coarse_delay_bits-1))/self.sample_rate_hz))
#             else:
#                 LOGGER.debug('Delay actually set to %e seconds.' % act_delay)
#         if (delay_rate != 0):
#             if fine_delay_rate == 0:
#                 LOGGER.info('Requested delay rate too slow for this configuration. Setting delay rate to zero.')
#             if (abs(fine_delay_rate) > 2**(fine_delay_rate_bits-1)):
#                 raise RuntimeError('Requested delay rate out of range (+-%e).' % (2**(bitshift_schedule-1)))
#             else:
#                 LOGGER.debug('Delay rate actually set to %e seconds per second.' % act_delay_rate)
#
#         if fringe_phase != 0:
#             if fr_offset == 0:
#                 LOGGER.info('Requested fringe phase is too small for this configuration (we do not have enough resolution). Setting fringe phase to zero.')
#             else:
#                 LOGGER.debug('Fringe offset actually set to %6.3f degrees.' % act_fringe_offset)
#
#         if fringe_rate != 0:
#             if fr_rate == 0:
#                 LOGGER.info('Requested fringe rate is too slow for this configuration. Setting fringe rate to zero.')
#             else:
#                 LOGGER.debug('Fringe rate actually set to %e Hz.' % act_fringe_rate)
#
#         # get the current mcnt for this feng
# #        mcnt_before = self.mcnt_current_get(ant_str)
# #
# #        # figure out the load time
# #        if ld_time < 0:
# #            # User did not ask for a specific time; load now!
# #            # figure out the load-time mcnt:
# #            mcnt_ld = int(mcnt_before + (self.config['mcnt_scale_factor'] * min_ld_time))
# #            mcnt_ld = mcnt_ld + (self.config['mcnt_scale_factor'] * extra_wait_time)
# #        else:
# #            if (ld_time < (time.time() + min_ld_time)):
# #                log_runtimeerror(self.syslogger, "Cannot load at a time in the past.")
# #            mcnt_ld = self.mcnt_from_time(ld_time)
#
# ##        if (mcnt_ld < (mcnt_before + self.config['mcnt_scale_factor']*min_ld_time)):
# ##            log_runtimeerror(self.syslogger, "This works out to a loadtime in the past! Logic error :(")
#
#         # setup the delays:
#         coarse_delay_reg.write(coarse_delay = coarse_delay)
#         LOGGER.debug("Set a coarse delay of %i clocks." % coarse_delay)
#
#         # fine delay (LSbs) is fraction of a cycle * 2^15 (16 bits allocated, signed integer).
#         # increment fine_delay by MSbs much every FPGA clock cycle shifted 2**20???
#         fractional_delay_reg.write(fractional_delay = fine_delay_i)
# 	delay_delta_reg.write(fractional_delay = fine_delay_rate)
# 	LOGGER.debug("Wrote %4x to fractional_delay and %4x to delay_delta register" % (fine_delay_i, fine_delay_rate))
#
#         # setup the fringe rotation
#         # LSbs is offset as a fraction of a cycle in fix_16_15 (1 = pi radians ; -1 = -1radians).
#         # MSbs is fringe rate as fractional increment to fr_offset per FPGA clock cycle as fix_16.15. FPGA divides this rate by 2**20 internally.
#         phase_offset_reg.write(fractional_delay = fr_offset)
#         phase_offset_delta_reg.write(fractional_delay = fr_rate)
#         LOGGER.debug("Wrote %4x to phase_offset and %4x to phase_offset_delta register a0_fd%i."%(fr_offset,fr_rate))
#
# # TODO change from immediate
#
# #        # set the load time:
# #        # MSb (load-it! bit) is pos-edge triggered.
# #        self.ffpgas[ffpga_n].write_int('ld_time_lsw%i' % feng_input, (mcnt_ld&0xffffffff))
# #        self.ffpgas[ffpga_n].write_int('ld_time_msw%i' % feng_input, (mcnt_ld>>32)&0x7fffffff)
# #        self.ffpgas[ffpga_n].write_int('ld_time_msw%i' % feng_input, (mcnt_ld>>32)|(1<<31))
# 	cd_control0_reg.write(arm = 'pulse', load_immediate = 'pulse')
# 	fd_control0_reg.write(arm = 'pulse', load_immediate = 'pulse')
#
#         if ld_check == False:
#             return {
#                 'act_delay': act_delay,
#                 'act_fringe_offset': act_fringe_offset,
#                 'act_fringe_rate': act_fringe_rate,
#                 'act_delay_rate': act_delay_rate}
#
# # TODO
#
# #        # check that it loaded correctly
# #        # wait until the time has elapsed
# #        sleep_time = self.time_from_mcnt(mcnt_ld) - self.time_from_mcnt(mcnt_before) + network_latency_adjust
# #        self.floggers[ffpga_n].debug('waiting %2.3f seconds (now: %i, ldtime: %i)' % (sleep_time, self.time_from_mcnt(mcnt_ld), self.time_from_mcnt(mcnt_before)))
# #        print 'waiting %2.3f seconds (now: %i, ldtime: %i)' % (sleep_time, self.time_from_mcnt(mcnt_ld), self.time_from_mcnt(mcnt_before))
# #        sys.stdout.flush()
# #        time.sleep(sleep_time)
#
#         # get the arm and load counts after the fact
#         status_after = fd_status_reg.read()
#         arm_count_after = status_after['arm_count']
#         ld_count_after = status_after['load_count']
#         LOGGER.info('BEFORE: arm_count(%10i) ld_count(%10i)' % (arm_count_before, ld_count_before, ))
#         LOGGER.info('AFTER:  arm_count(%10i) ld_count(%10i)' % (arm_count_after, ld_count_after, ))
#
#         # did the system arm?
#         if (arm_count_before == arm_count_after):
#             if arm_count_after == 0:
#                 raise RuntimeError('delay arm count stays zero. Load failed.')
#             else:
#                 raise RuntimeError('arm count = %i. Load failed.' % (arm_count_after))
#
# #        # did the system arm but not load?
# #        if (ld_count_before >= ld_count_after):
# #            mcnt_after = self.mcnt_current_get(ant_str)
# #            print 'MCNT: before: %10i, target: %10i, after: %10i, after-target(%10i)' % (mcnt_before, mcnt_ld, mcnt_after, mcnt_after - mcnt_ld, )
# #            print 'TIME: before: %10.3f, target: %10.3f, after: %10.3f, after-target(%10.3f)' % (self.time_from_mcnt(mcnt_before), self.time_from_mcnt(mcnt_ld), self.time_from_mcnt(mcnt_after), self.time_from_mcnt(mcnt_after - mcnt_ld), )
# #            if mcnt_after > mcnt_ld:
# #                log_runtimeerror(self.floggers[ffpga_n], 'We missed loading the registers by about %4.1f ms.' % ((mcnt_after - mcnt_ld)/self.config['mcnt_scale_factor']*1000.0))
# #            else:
# #                log_runtimeerror(self.floggers[ffpga_n], 'Ant %s (Feng %i on %s) did not load correctly for an unknown reason.' % (ant_str, feng_input, self.fsrvs[ffpga_n]))
#
#         return {
#             'act_delay': act_delay,
#             'act_fringe_offset': act_fringe_offset,
#             'act_fringe_rate': act_fringe_rate,
#             'act_delay_rate': act_delay_rate}

'''
    def _get_fengine_fpga_config(self):

        # constants for accessing polarisation specific registers 'x' even, 'y' odd
        self.pol0_offset =  '%s' % (str(self.id*2))
        self.pol1_offset =  '%s' % (str(self.id*2+1))

        # default fft shift schedule
        self.config['fft_shift']                        = self.config_portal.get_int([ '%s '%self.descriptor, 'fft_shift'])

        # output data resolution after requantisation
        self.config['n_bits_output']                    = self.config_portal.get_int([ '%s '%self.descriptor, 'n_bits_output'])
        self.config['bin_pt_output']                    = self.config_portal.get_int([ '%s '%self.descriptor, 'bin_pt_output'])

        # equalisation (only necessary in FPGA based fengines)
        self.config['equalisation'] = {}
        # TODO this may not be constant across fengines (?)
        self.config['equalisation']['decimation']       = self.config_portal.get_int(['equalisation', 'decimation'])
        # TODO what is this?
        self.config['equalisation']['tolerance']        = self.config_portal.get_float(['equalisation', 'tolerance'])
        # coeffs
        self.config['equalisation']['n_bytes_coeffs']   = self.config_portal.get_int(['equalisation', 'n_bytes_coeffs'])
        self.config['equalisation']['bin_pt_coeffs']    = self.config_portal.get_int(['equalisation', 'bin_pt_coeffs'])
        # default equalisation polynomials for polarisations
        self.config['equalisation']['poly0']            = self.config_portal.get_int_list([ '%s '%self.descriptor, 'poly0'])
        self.config['equalisation']['poly1']            = self.config_portal.get_int_list([ '%s '%self.descriptor, 'poly1'])

    def __getattribute__(self, name):
        """Overload __getattribute__ to make shortcuts for getting object data.
        """

        # fft_shift is same for all fengine_fpgas of this type on device
        # (overload in child class if this changes)
        if name == 'fft_shift':
            return self.host.device_by_name( '%sfft_shift'   %self.tag)
        # we can't access Shared BRAMs in the same way as we access registers
        # at the moment, so we access the name and use read/write
        elif name == 'eq0_name':
            return  '%seq  %s'  % (self.tag, self.pol0_offset)
        elif name == 'eq1_name':
            return  '%seq  %s'  % (self.tag, self.pol1_offset)
        # fengines transmit to multiple xengines. Each xengine processes a continuous band of
        # frequencies with the lowest numbered band from all antennas being processed by the first xengine
        # and so on. The xengines have IP addresses starting a txip_base and increasing linearly. Some xengines
        # may share IP addresses
        elif name == 'txip_base':
            return self.host.device_by_name( '%stxip_base  %s'  % (self.tag, self.offset))
        elif name == 'txport':
            return self.host.device_by_name( '%stxport  %s'  % (self.tag, self.offset))
        # two polarisations
        elif name == 'snap_adc0':
            return self.host.device_by_name( '%ssnap_adc  %s_ss' % (self.tag, self.pol0_offset))
        elif name == 'snap_adc1':
            return self.host.device_by_name( '%ssnap_adc  %s_ss' % (self.tag, self.pol1_offset))
        elif name == 'snap_quant0':
            return self.host.device_by_name( '%sadc_quant  %s_ss' % (self.tag, self.pol0_offset))
        elif name == 'snap_quant1':
            return self.host.device_by_name( '%sadc_quant  %s_ss' % (self.tag, self.pol1_offset))

        # if attribute name not here try parent class
        return EngineFpga.__getattribute__(self, name)

    ##############################################
    # Equalisation before re-quantisation stuff  #
    ##############################################

    def get_equalisation(self, pol_index):
        """ Get current equalisation values applied pre-quantisation
        """

        reg_name = getattr(self, 'eq  %s_name' % pol_index)
        n_chans = self.config['n_chans']
        decimation = self.config['equalisation']['decimation']
        n_coeffs = n_chans/decimation * 2

        n_bytes = self.config['equalisation']['n_bytes_coeffs']
        bin_pt = self.config['equalisation']['bin_pt_coeffs']

        #read raw bytes
        # we cant access brams like registers, so use old style read
        coeffs_raw = self.host.read(reg_name, n_coeffs*n_bytes)

        coeffs = self.str2float(coeffs_raw, n_bytes*8, bin_pt)

        #pad coeffs out by decimation factor
        coeffs_padded = numpy.reshape(numpy.tile(coeffs, [decimation, 1]), [1, n_chans], 'F')

        return coeffs_padded[0]

    def get_default_equalisation(self, pol_index):
        """ Get default equalisation settings
        """

        decimation = self.config['equalisation']['decimation']
        n_chans = self.config['n_chans']
        n_coeffs = n_chans/decimation

        poly = self.config['equalisation']['poly  %s'  % pol_index]
        eq_coeffs = numpy.polyval(poly, range(n_chans))[decimation/2::decimation]
        eq_coeffs = numpy.array(eq_coeffs, dtype=complex)

        if len(eq_coeffs) != n_coeffs:
            log_runtime_error(LOGGER, "Something's wrong. I have %i eq coefficients when I should have %i."  % (len(eq_coeffs), n_coeffs))
        return eq_coeffs

    def set_equalisation(self, pol_index, init_coeffs=None, init_poly=None, issue_spead=True):
        """ Set equalisation values to be applied pre-requantisation
        """

        reg_name = getattr(self, 'eq  %s_name' % pol_index)
        n_chans = self.config['n_chans']
        decimation = self.config['equalisation']['decimation']
        n_coeffs = n_chans / decimation

        if init_coeffs is None and init_poly is None:
            coeffs = self.get_default_equalisation(pol_index)
        elif len(init_coeffs) == n_coeffs:
            coeffs = init_coeffs
        elif len(init_coeffs) == n_chans:
            coeffs = init_coeffs[0::decimation]
            LOGGER.warn("You specified %i EQ coefficients but your system only supports %i actual values. Only writing every %ith value." % (n_chans ,n_coeffs, decimation))
        elif len(init_coeffs) > 0:
            log_runtime_error(LOGGER, 'You specified %i coefficients, but there are %i EQ coefficients required for this engine' % (len(init_coeffs), n_coeffs))
        else:
            coeffs = numpy.polyval(init_poly, range(n_chans))[decimation/2::decimation]
            coeffs = numpy.array(coeffs, dtype=complex)

        n_bytes = self.config['equalisation']['n_bytes_coeffs']
        bin_pt = self.config['equalisation']['bin_pt_coeffs']

        coeffs_str = self.float2str(coeffs, n_bytes*8, bin_pt)

        # finally write to the bram
        self.host.write(reg_name, coeffs_str)

'''
