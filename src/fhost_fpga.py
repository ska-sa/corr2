import time
import logging
import struct

from host_fpga import FpgaHost

LOGGER = logging.getLogger(__name__)


class DigitiserDataReceiver(FpgaHost):
    """
    The RX section of a fengine and filter engine are the same - receive the digitiser data
    """

    def __init__(self, host, katcp_port=7147, boffile=None, connect=True):
        super(DigitiserDataReceiver, self).__init__(host, katcp_port=katcp_port,
                                                    boffile=boffile, connect=connect)

    def _get_rxreg_data(self):
        """
        Get the rx register data for this host
        :return:
        """
        data = {}
        if 'reorder_ctrs1' in self.registers.names():
            reorder_ctrs = self.registers.reorder_ctrs.read()['data']
            reorder_ctrs.update(self.registers.reorder_ctrs1.read()['data'])
        else:
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

    def check_rx_reorder(self):
        """
        Is this F host reordering received data correctly?
        :return:
        """
        _required_repetitions = 5
        _sleeptime = 0.2

        num_tengbes = len(self.tengbes)
        if num_tengbes < 1:
            raise RuntimeError('F-host with no 10gbe cores %s?' % self.host)

        test_data = []
        for _ctr in range(0, _required_repetitions):
            test_data.append(self._get_rxreg_data())
            time.sleep(_sleeptime)

        got_errors = False
        for _ctr in range(1, _required_repetitions):
            for gbe in range(num_tengbes):
                if test_data[_ctr]['pktof_ctr%i' % gbe] != test_data[0]['pktof_ctr%i' % gbe]:
                    LOGGER.error('F host %s packet overflow on interface gbe%i. %i -> %i' % (
                        self.host, gbe, test_data[_ctr]['pktof_ctr%i' % gbe],
                        test_data[0]['pktof_ctr%i' % gbe]))
                    got_errors = True
            for pol in range(0, 2):
                if test_data[_ctr]['recverr_ctr%i' % pol] != test_data[0]['recverr_ctr%i' % pol]:
                    LOGGER.error('F host %s pol %i reorder count error. %i -> %i' % (
                        self.host, pol, test_data[_ctr]['recverr_ctr%i' % pol],
                        test_data[0]['recverr_ctr%i' % pol]))
                    got_errors = True
            if test_data[_ctr]['mcnt_relock'] != test_data[0]['mcnt_relock']:
                LOGGER.error('F host %s mcnt_relock is changing. %i -> %i' % (
                    self.host, test_data[_ctr]['mcnt_relock'], test_data[0]['mcnt_relock']))
                got_errors = True
            if test_data[_ctr]['timerror'] != test_data[0]['timerror']:
                LOGGER.error('F host %s timestep error is changing. %i -> %i' % (
                    self.host, test_data[_ctr]['timerror'], test_data[0]['timerror']))
                got_errors = True
            if test_data[_ctr]['discard'] != test_data[0]['discard']:
                LOGGER.error('F host %s discarding packets. %i -> %i' % (
                    self.host, test_data[_ctr]['discard'], test_data[0]['discard']))
                got_errors = True
        if got_errors:
            LOGGER.error('One or more errors detected, check logs.')
            return False
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

    def clear_status(self):
        """
        Clear the status registers and counters on this host
        :return:
        """
        self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse',
                                     cnt_rst='pulse')
        LOGGER.debug('{}: status cleared.'.format(self.host))


class FpgaFHost(DigitiserDataReceiver):
    """
    A Host, that hosts Fengines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, boffile=None,
                 connect=True, config=None):
        super(FpgaFHost, self).__init__(host,
                                        katcp_port=katcp_port,
                                        boffile=boffile,
                                        connect=connect)

        self._config = config

        # list of DataSources received by this f-engine host
        self.data_sources = []

        # dictionary, indexed on source name, containing tuples
        # of poly and bram name
        self.eqs = {}

        # list of dictionaries containing delay settings for each stream
        self.delays = []

        if config is not None:
            self.num_fengines = int(config['f_per_fpga'])
            self.ports_per_fengine = int(config['ports_per_fengine'])
            self.fft_shift = int(config['fft_shift'])
            self.n_chans = int(config['n_chans'])
            self.min_load_time = float(config['min_load_time'])
            self.network_latency_adjust = float(config['network_latency_adjust'])
        else:
            self.num_fengines = None
            self.ports_per_fengine = None
            self.fft_shift = None
            self.n_chans = None
            self.min_load_time = None
            self.network_latency_adjust = None

        if self.num_fengines:
            for offset in range(self.num_fengines):
                self.delays.append({'delay': 0, 'delta_delay': 0,
                                    'phase_offset': 0, 'delta_phase_offset': 0,
                                    'load_time': None, 'load_wait': None,
                                    'load_check': True})

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile,
                   connect=True, config=config_source)

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

    def add_source(self, data_source):
        """
        Add a new data source to this fengine host
        :param data_source: A DataSource object
        :return:
        """
        # check that it doesn't already exist before adding it
        for src in self.data_sources:
            if src.name == data_source.name:
                raise ValueError('%s == %s - cannot have two sources with '
                                 'the same name on one '
                                 'fhost' % (src.name, data_source.name))
        self.data_sources.append(data_source)

    def get_source_eq(self, source_name=None):
        """
        Return a dictionary of all the EQ settings for the sources allocated
        to this fhost
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
            eq_bram = 'eq%i' % self.eqs[eq_name]['bram_num']
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

        Specify either eq_tuple, a combination of sbram_name and value(s),
        OR eq_name, but not both. If eq_name is specified, the sbram_name
        and eq value(s) are read from the self.eqs dictionary.

        :param eq_tuple: a tuple of an integer, complex number or list or
        integers or complex numbers and a sbram name
        :param eq_name: the name of an eq to use, found in the self.eqs
        dictionary
        :return:
        """
        if eq_tuple is None and eq_name is None:
            raise RuntimeError('Cannot have both tuple and name None')
        if eq_name is not None:
            if eq_name not in self.eqs:
                raise ValueError('%s: unknown source name %s' %
                                 (self.host, eq_name))
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

    def write_delays_all(self):
        """
        Goes through all offsets and writes delays with stored delay settings
        """
        act_vals = []
        for offset in range(len(self.delays)):
            coeffs = self.delays[offset]
            act_val = self.write_delay(offset, coeffs['delay'], coeffs['delta_delay'],
                            coeffs['phase_offset'], coeffs['delta_phase_offset'],
                            coeffs['load_time'], coeffs['load_wait'], coeffs['load_check'])
               
            act_vals.append(act_val)

        return act_vals

    def set_delay(self, offset, delay=0.0, delta_delay=0.0, 
                    phase_offset=0.0, delta_phase_offset=0.0, 
                    load_time=None, load_wait=None, load_check=True):
        """
        Update delay settings for data stream at offset specified ready for writing

        :param delay is in samples
        :param delta delay is in samples per sample
        :param phase offset is in fractions of a sample
        :param delta phase offset is in samples per sample
        :return 
        """
        self.delays[offset] = {'delay': delay, 'delta_delay': delta_delay, 
                            'phase_offset': phase_offset, 
                            'delta_phase_offset': delta_phase_offset,
                            'load_time': load_time, 'load_wait': load_wait,
                            'load_check': load_check}

    def write_delay(self, offset, delay=0.0, delta_delay=0.0, 
                    phase_offset=0.0, delta_phase_offset=0.0, 
                    load_mcnt=None, load_wait_delay=None, load_check=True):
        """
        Configures a given stream to a delay in samples and phase in degrees.

        The sample count at which this happens can be specified (default is
        immediate if not specified).
        If a load_check_time is specified, function will block until that
        time before checking.
        By default, it will load immediately and verify that things worked
        as expected.

        :offset is polarisation's offset within FPGA
        :param delay is in samples
        :param delta delay is in samples per sample
        :param phase offset is in fractions of a sample
        :param delta phase offset is in samples per sample
        :param load_mcnt is in samples since epoch
        :param load_wait_delay is seconds to wait for delay values to load
        :param load_check whether to check if load happened
        :return actual values to be loaded
        """

        # TODO should this be in config file?
        bitshift_schedule = 23
        _bshift_val = (2**bitshift_schedule)

        #########
        # delay #
        #########

        #TODO check register parameters to get delay range

        # shift up by amount shifted down by on fpga
        delta_delay_shifted = float(delta_delay) * _bshift_val

        # delay registers
        delay_reg = self.registers['delay%i' % offset]
        delta_delay_reg = self.registers['delta_delay%i' % offset]

        LOGGER.info('%s:%d setting an initial delay of %f samples.' %
                    (self.host, offset, delay))

        # setup the delay
        try:
            delay_reg.write(initial=delay)
        except ValueError as e:
            LOGGER.error('%s:%d initial delay range error - %s' %
                         (self.host, offset, e.message))

            if delay < 0:
                LOGGER.error('%s:%d smallest delay is 0' % (self.host, offset))
                compromise = 0
                LOGGER.error('%s:%d setting delay to %f data samples' %
                             (self.host, offset, compromise))
                delay_reg.write(initial=compromise)
            
            reg_info = delay_reg.block_info
            bw = int(reg_info['bitwidths']) 
            b = int(reg_info['bin_pts'])
            max_delay = 2**(bw - b) - 1/float(2**b)
            if delay > max_delay:
                LOGGER.error('%s:%d largest possible delay is %f data samples' %
                            (self.host, offset, max_delay))
                compromise = max_delay
                LOGGER.error('%s:%d setting delay to %f data samples' %
                             (self.host, offset, compromise))
                delay_reg.write(initial=compromise)

        LOGGER.info('%s:%d setting delay delta to %e' %
                    (self.host, offset, delta_delay))

        try:
            delta_delay_reg.write(delta=delta_delay_shifted)
        except ValueError as e:
            LOGGER.error('%s:%d delay change range error - %s' %
                         (self.host, offset, e.message))

            reg_info = delta_delay_reg.block_info
            bw_str = reg_info['bitwidths']
            bw = int(bw_str[1:len(bw_str)-1]) 
            b_str = reg_info['bin_pts']
            b = int(b_str[1:len(b_str)-1])
    
            max_positive_delta_delay = 1 - 1/float(2**b)
            max_negative_delta_delay = -1 
            if delta_delay_shifted > max_positive_delta_delay:
                compromise = max_positive_delta_delay
                LOGGER.error('%s:%d largest possible positive delta delay is %e data samples/sample' %
                            (self.host, offset, compromise / _bshift_val))
                LOGGER.error('%s:%d setting delay to %e data samples/sample' %
                             (self.host, offset, compromise / _bshift_val))
                delta_delay_reg.write(delta=compromise)
            if delta_delay_shifted < max_negative_delta_delay: 
                compromise = max_negative_delta_delay
                LOGGER.error('%s:%d largest possible negative delta delay is %e data samples/sample' %
                            (self.host, offset, compromise / _bshift_val))
                LOGGER.error('%s:%d setting delay to %e data samples/sample' %
                             (self.host, offset, compromise / _bshift_val))
                delta_delay_reg.write(delta=compromise)

        ################
        # phase offset #
        ################

        phase_reg = self.registers['phase%i' % offset]

        # multiply by amount shifted down by on FPGA
        delta_phase_offset_shifted = float(delta_phase_offset) * _bshift_val

        LOGGER.info('%s:%d writing %f to initial and %f to delta in phase '
                    'register' %
                    (self.host, offset,
                     phase_offset, delta_phase_offset_shifted))

        # setup the phase offset
        try:
            phase_reg.write(initial=phase_offset)
        except ValueError as e:
            LOGGER.error('%s: phase offset range error - %s' %
                         (self.host, e.message))
        try:
            phase_reg.write(delta=delta_phase_offset_shifted)
        except ValueError as e:
            LOGGER.error('%s: phase offset change range error - %s' %
                         (self.host, e.message))

        cd_tl_name = 'tl_cd%i' % offset
        fd_tl_name = 'tl_fd%i' % offset
        status = self.arm_timed_latches([cd_tl_name, fd_tl_name],
                                        mcnt=load_mcnt,
                                        check_time_delay=load_wait_delay)
        cd_status_before = status['status_before'][cd_tl_name]
        cd_status_after = status['status_after'][cd_tl_name]
        fd_status_before = status['status_before'][fd_tl_name]
        fd_status_after = status['status_after'][fd_tl_name]

        # read the arm and load counts
        # they must increment after the delay has been loaded
        cd_arm_count_before = cd_status_before['arm_count']
        cd_ld_count_before = cd_status_before['load_count']
        cd_armed_before = cd_status_before['armed']
        cd_arm_count_after = cd_status_after['arm_count']
        cd_ld_count_after = cd_status_after['load_count']
        fd_arm_count_before = fd_status_before['arm_count']
        fd_ld_count_before = fd_status_before['load_count']
        fd_armed_before = fd_status_before['armed']
        fd_arm_count_after = fd_status_after['arm_count']
        fd_ld_count_after = fd_status_after['load_count']

        # was the system already armed?
        if cd_armed_before == True:
            LOGGER.error('%s:%d coarse delay timed latch was already armed. '
                         'Previous load failed'% (self.host, offset))

        if fd_armed_before == True:
            LOGGER.error('%s:%d phase correction timed latch was already armed. '
                         'Previous load failed'% (self.host, offset))

        # did the system arm correctly
        if cd_arm_count_before == cd_arm_count_after:
            # don't report error if it was already armed as count won't increase
            if cd_armed_before == False:
                LOGGER.error('%s:%d coarse delay arm count did not change.'
                    % (self.host, offset))
                LOGGER.error('%s:%d BEFORE: coarse arm_count(%i) ld_count(%i)'
                    % (self.host, offset, cd_arm_count_before, cd_ld_count_before))
                LOGGER.error('%s:%d AFTER:  coarse arm_count(%i) ld_count(%i)'
                    % (self.host, offset, cd_arm_count_after, cd_ld_count_after))

        if fd_arm_count_before == fd_arm_count_after:
            if fd_armed_before == False:
                LOGGER.error('%s:%d phase correction arm count did not '
                            'change.' % (self.host, offset))
                LOGGER.error('%s:%d BEFORE: phase correction arm_count(%i) ld_count(%i)'
                            % (self.host, offset, fd_arm_count_before, fd_ld_count_before))
                LOGGER.error('%s:%d AFTER: phase correction arm_count(%i) ld_count(%i)'
                            % (self.host, offset, fd_arm_count_after, fd_ld_count_after))

        # did the system load?
        if load_check == True:
            if cd_ld_count_before == cd_ld_count_after:
                LOGGER.error('%s:%d coarse delay load count did not change. '
                             'Load failed.' % (self.host, offset))

            if fd_ld_count_before == fd_ld_count_after:
                LOGGER.error('%s:%d phase correction load count did not '
                             'change. Load failed.' % (self.host, offset))

        #read values back to see what actual values were loaded

        act_delay = delay_reg.read()['data']['initial']
        act_delta_delay = delta_delay_reg.read()['data']['delta'] / _bshift_val
        act_phase_offset = phase_reg.read()['data']['initial']
        act_delta_phase_offset = phase_reg.read()['data']['delta'] / _bshift_val

        return {
            'act_delay': act_delay,
            'act_delta_delay': act_delta_delay,
            'act_phase_offset': act_phase_offset,
            'act_delta_phase_offset': act_delta_phase_offset,
        }

    def arm_timed_latches(self, names, mcnt=None, check_time_delay=None):
        """
        Arms a timed latch.
        :param names: names of latches to trigger
        :param mcnt: sample mcnt to trigger at. If None triggers immediately
        :param check_time_delay: time in seconds to wait after arming
        :return dictionary containing status_before and status_after list
        """
        status_before = {}
        status_after = {}

        if mcnt is not None:
            load_time_lsw = mcnt - (int(mcnt/(2**32)))*(2**32)
            load_time_msw = int(mcnt/(2**32))

        for name in names:
            control_reg = self.registers['%s_control' % name]
            control0_reg = self.registers['%s_control0' % name]
            status_reg = self.registers['%s_status' % name]

            status_before[name] = status_reg.read()['data']

            if mcnt is None:
                control0_reg.write(arm='pulse', load_immediate='pulse')
            else:
                control_reg.write(load_time_lsw=load_time_lsw)
                control0_reg.write(arm='pulse', load_time_msw=load_time_msw,
                                   load_immediate=0)

        if check_time_delay is not None:
            time.sleep(check_time_delay)

        for name in names:
            status_reg = self.registers['%s_status' % name]
            status_after[name] = status_reg.read()['data']

        return {
            'status_before': status_before,
            'status_after': status_after,
        }

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

    def get_quant_snapshots(self):
        """
        Get the quant snapshots for all the sources on this host.
        :return:
        """
        return {src.name: self.get_quant_snapshot(src.name)
                for src in self.data_sources}

    def get_quant_snapshot(self, source_name=None):
        """
        Read the post-quantisation snapshot for a given source
        :return:
        """
        targetsrc = None
        targetsrc_num = -1
        for srcnum, src in enumerate(self.data_sources):
            if src.name == source_name:
                targetsrc = src
                targetsrc_num = srcnum
                break

        if targetsrc is None:
            raise ValueError('Could not find source %s on '
                             'this fhost.' % source_name)

        if targetsrc_num % 2 == 0:
            snapshot = self.snapshots.snap_quant0_ss
        else:
            snapshot = self.snapshots.snap_quant1_ss
        sdata = snapshot.read()['data']
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

    def get_adc_snapshots(self):
        """
        Read the ADC snapshots from this Fhost
        """
        p0 = self.snapshots.snap_adc0_ss.read()['data']
        p1 = self.snapshots.snap_adc1_ss.read()['data']
        return {'p0': p0, 'p1': p1}

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
