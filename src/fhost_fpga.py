import time
import logging
import struct
import numpy

import casperfpga.memory as caspermem

import delay as delayops
from utils import parse_slx_params
from digitiser_receiver import DigitiserStreamReceiver

LOGGER = logging.getLogger(__name__)


class InputNotFoundError(ValueError):
    pass


class AdcData(object):
    """
    Container for lists of ADC data
    """
    def __init__(self, timestamp, data):
        """

        :param timestamp: int, system time at which the data was read
        :param data: a list of the data, sample-by-sample
        :return:
        """
        self.timestamp = timestamp
        self.data = data


def delay_get_bitshift():
    """

    :return:
    """
    # TODO should this be in config file?
    bitshift_schedule = 23
    bitshift = (2**bitshift_schedule)
    return bitshift


class Fengine(object):
    """
    An F-engine, acting on a source DataStream
    """
    def __init__(self, input_stream,
                 host=None, offset=-1):
        """

        :param input_stream: the DigitiserStream input for this F-engine
        :param host: the Fpga host on which this input is received
        :param offset: which input on that host is this?
        :return:
        """
        self.input = input_stream
        self.host = host
        self.offset = offset
        self.eq_poly = None
        self.eq_bram_name = 'eq%i' % offset
        self.last_delay = None

    @property
    def name(self):
        return self.input.name

    @name.setter
    def name(self, new_name):
        if new_name == self.name:
            return
        self.input.name = new_name
        # TODO - update delay sensors?

    @property
    def input_number(self):
        return self.input.input_number

    @input_number.setter
    def input_number(self, value):
        raise NotImplementedError('This is not currently defined.')

    def delay_set_calculate_and_write_regs(
            self, loadcnt, delay=None, delay_delta=None,
            phase=None, phase_delta=None):
        """
        Same parameters as for self.delay_set 
        """
        if ((delay is None) and (delay_delta is None)
                and (phase is None) and (phase_delta is None)):
            raise RuntimeError('No delay info supplied to function in any form')
        # only apply the parameters passed in, not the others
        if delay is not None:
            self._delay_write_delay(delay, loadcnt)
        if delay_delta is not None:
            self._delay_write_delay_rate(delay_delta, loadcnt)
        if phase is not None:
            self._delay_write_phase(phase, loadcnt)
        if phase_delta is not None:
            self._delay_write_phase_rate(phase_delta, loadcnt)

    def delay_set_arm_timed_latches(self, loadcnt, load_check=False):
        """
        
        :param loadcnt: 
        :param load_check: 
        :return: 
        """
        cd_tl_name = 'tl_cd%i' % self.offset
        fd_tl_name = 'tl_fd%i' % self.offset
        status = self.host.arm_timed_latches(
            [cd_tl_name, fd_tl_name], mcnt=loadcnt)
        return self.check_timed_latch(status, loadcnt, load_check)

    def check_timed_latch(self, status, loadmcnt, load_check=False):
        """
        Given the results from timed latches being armed, check them and print
        results.
        :param loadmcnt: when were the latches to have armed?
        :param status: A dictionary of load statuses, as returned 
            by self.host.arm_timed_latches()
        :param load_check: 
        :return: 
        """
        infostr = '%s:%i:%i:' % (self.host.host, self.offset, loadmcnt)
        cd_tl_name = 'tl_cd%i' % self.offset
        fd_tl_name = 'tl_fd%i' % self.offset
        cd_before = status['status_before'][cd_tl_name]
        cd_after = status['status_after'][cd_tl_name]
        fd_before = status['status_before'][fd_tl_name]
        fd_after = status['status_after'][fd_tl_name]
        # read the arm and load counts
        # they must increment after the delay has been loaded
        # was the system already armed?
        arm_error = False
        if cd_before['armed']:
            LOGGER.error('%s coarse delay timed latch was already armed. '
                         'Previous load failed.' % infostr)
            arm_error = True
        if fd_before['armed']:
            LOGGER.error('%s phase correction timed latch was already '
                         'armed. Previous load failed.' % infostr)
            arm_error = True
        # did the system arm correctly
        if (not cd_before['armed']) and \
                (cd_before['arm_count'] == cd_after['arm_count']):
            LOGGER.error('%s coarse delay arm count did not '
                         'change.' % infostr)
            LOGGER.error('%s BEFORE: coarse arm_count(%i) ld_count(%i)' % (
                infostr, cd_before['arm_count'], cd_before['load_count']))
            LOGGER.error('%s AFTER:  coarse arm_count(%i) ld_count(%i)' % (
                infostr, cd_after['arm_count'], cd_after['load_count']))
            arm_error = True
        if (not fd_before['armed']) and \
                (fd_before['arm_count'] == fd_after['arm_count']):
            LOGGER.error('%s phase correction arm count did not change.' %
                         infostr)
            LOGGER.error('%s BEFORE: phase correction arm_count(%i) '
                         'ld_count(%i)' % (infostr, fd_before['arm_count'],
                                           fd_before['load_count']))
            LOGGER.error('%s AFTER:  phase correction arm_count(%i) '
                         'ld_count(%i)' % (infostr, fd_after['arm_count'],
                                           fd_after['load_count']))
            arm_error = True
        # did the system load?
        if load_check:
            if cd_before['load_count'] == cd_after['load_count']:
                LOGGER.error('%s coarse delay load count did not change. '
                             'Load failed.' % infostr)
                arm_error = True
            if fd_before['load_count'] == fd_after['load_count']:
                LOGGER.error('%s phase correction load count did not '
                             'change. Load failed.' % infostr)
                arm_error = True
        return arm_error

    def delay_set_actual_values(self, loadcnt):
        """

        :return: 
        """
        actual_delay = self.delay_get()
        actual_delay.load_time = loadcnt
        self.last_delay = actual_delay
        return actual_delay

    def delay_set(self, loadcnt, delay=None, delay_delta=None,
                  phase=None, phase_delta=None):
        """
        Configures a given stream to a delay in samples and phase in degrees.

        The sample count at which this happens can be specified (default is
        immediate if not specified).
        If a load_check_time is specified, function will block until that
        time before checking.
        By default, it will load immediately and verify that things worked
        as expected.

        :return actual values to be loaded
        """
        # set up the delays
        self.delay_set_calculate_and_write_regs(
            loadcnt, delay, delay_delta, phase, phase_delta)
        # arm the timed load latches
        arm_error = self.delay_set_arm_timed_latches(loadcnt)
        # get and return the actual values loaded
        actual_delay = self.delay_set_actual_values(loadcnt)
        if arm_error:
            actual_delay.error.set()
        return actual_delay

    def delay_get(self):
        """
        Read the values actually written to the FPGA
        :return:
        """
        bitshift = delay_get_bitshift()
        delay_reg = self.host.registers['delay%i' % self.offset]
        delay_delta_reg = self.host.registers['delta_delay%i' % self.offset]
        phase_reg = self.host.registers['phase%i' % self.offset]
        act_delay = delay_reg.read()['data']['initial']
        act_delay_delta = delay_delta_reg.read()['data']['delta'] / bitshift
        act_phase_offset = phase_reg.read()['data']['initial']
        act_phase_offset_delta = phase_reg.read()['data']['delta'] / bitshift
        sample_rate = self.host.rx_data_sample_rate_hz
        actual_val = delayops.Delay(act_delay, act_delay_delta,
                                    act_phase_offset, act_phase_offset_delta)
        actual_val.delay /= sample_rate
        actual_val.phase_offset *= numpy.pi
        actual_val.phase_offset_delta *= (numpy.pi * sample_rate)
        return actual_val

    def _delay_write_delay_rate(self, delay_rate, loadcnt):
        """
        """
        infostr = '%s:%i:%i:' % (self.host.host, self.offset, loadcnt)
        bitshift = delay_get_bitshift()
        delay_delta_reg = self.host.registers['delta_delay%i' % self.offset]
        # shift up by amount shifted down by on fpga
        delta_delay_shifted = float(delay_rate) * bitshift
        dds = delta_delay_shifted
        dd = dds / bitshift
        LOGGER.debug('%s attempting delay delta to %e (%e after shift)' %
                     (infostr, delay_rate, delta_delay_shifted))
        reg_info = delay_delta_reg.block_info
        reg_bp = int(parse_slx_params(reg_info['bin_pts'])[0])
        max_positive_delta_delay = 1 - 1 / float(2 ** reg_bp)
        max_negative_delta_delay = -1 + 1 / float(2 ** reg_bp)
        if delta_delay_shifted > max_positive_delta_delay:
            dds = max_positive_delta_delay
            dd = dds / bitshift
            LOGGER.warn('%s largest possible positive delay delta '
                        'is %e data samples/sample' % (infostr, dd))
            LOGGER.warn('%s setting delay delta to %e data '
                        'samples/sample (%e after shift)' %
                        (infostr, dd, dds))
        elif delta_delay_shifted < max_negative_delta_delay:
            dds = max_negative_delta_delay
            dd = dds / bitshift
            LOGGER.warn('%s largest possible negative delay delta is %e '
                        'data samples/sample' % (infostr, dd))
            LOGGER.warn('%s setting delay delta to %e data samples/sample '
                        '(%e after shift)' % (infostr, dd, dds))
            LOGGER.debug('%s writing delay delta to %e (%e after shift)' %
                         (infostr, dd, dds))
        try:
            delay_delta_reg.write(delta=dds)
        except ValueError as e:
            errmsg = '%s writing delay delta (%.8e), error - %s' % \
                     (infostr, dds, e.message)
            LOGGER.error(errmsg)
            raise ValueError(errmsg)

    def _delay_write_delay(self, delay, loadcnt):
        """
        """
        infostr = '%s:%i:%i:' % (self.host.host, self.offset, loadcnt)
        bitshift = delay_get_bitshift()
        delay_reg = self.host.registers['delay%i' % self.offset]
        reg_info = delay_reg.block_info
        reg_bw = int(parse_slx_params(reg_info['bitwidths'])[0])
        reg_bp = int(parse_slx_params(reg_info['bin_pts'])[0])
        max_delay = 2 ** (reg_bw - reg_bp) - 1 / float(2 ** reg_bp)
        LOGGER.debug('%s attempting initial delay of %f samples.' %
                     (infostr, delay))
        if delay < 0:
            LOGGER.warn('%s smallest delay is 0, setting to zero' % infostr)
            delay = 0
        elif delay > max_delay:
            LOGGER.warn('%s largest possible delay is %f data samples' % (
                infostr, max_delay))
            delay = max_delay
        LOGGER.debug('%s setting delay to %f data samples' % (infostr, delay))
        try:
            delay_reg.write(initial=delay)
        except ValueError as e:
            errmsg = '%s writing initial delay range delay(%.8e), error - ' \
                     '%s' % (infostr, delay, e.message)
            LOGGER.error(errmsg)
            raise ValueError(errmsg)

    def _delay_write_phase(self, phase, loadcnt):
        """
        :return:
        """
        infostr = '%s:%i:%i:' % (self.host.host, self.offset, loadcnt)
        bitshift = delay_get_bitshift()
        phase_reg = self.host.registers['phase%i' % self.offset]
        LOGGER.debug('%s attempting to set initial phase to %f' % (
            infostr, phase))
        # setup the phase offset
        reg_info = phase_reg.block_info
        bps = parse_slx_params(reg_info['bin_pts'])
        b = float(2 ** int(bps[0]))
        max_positive_phase = 1 - 1 / b
        max_negative_phase = -1 + 1 / b
        limited = False
        if phase > max_positive_phase:
            phase = max_positive_phase
            LOGGER.warn('%s largest possible positive phase is '
                        '%e pi' % (infostr, phase))
            limited = True
        elif phase < max_negative_phase:
            phase = max_negative_phase
            LOGGER.warn('%s largest possible negative phase is '
                        '%e pi' % (infostr, phase))
            limited = True
        if limited:
            LOGGER.warn('%s setting phase to %e pi' % (infostr, phase))
        # actually write the values to the register
        LOGGER.debug('%s writing initial phase to %f' % (infostr, phase))
        try:
            phase_reg.write(initial=phase)
        except ValueError as e:
            errmsg = '%s writing phase(%.8e), error - %s' % (
                infostr, phase, e.message)
            LOGGER.error(errmsg)
            raise ValueError(errmsg)

    def _delay_write_phase_rate(self, phase_rate, loadcnt):
        """
        :return:
        """
        infostr = '%s:%i:%i:' % (self.host.host, self.offset, loadcnt)
        bitshift = delay_get_bitshift()
        phase_reg = self.host.registers['phase%i' % self.offset]
        # multiply by amount shifted down by on FPGA
        delta_phase_offset_shifted = float(phase_rate) * bitshift
        LOGGER.debug('%s attempting to set phase delta to %e' % (
            infostr, delta_phase_offset_shifted))
        # phase delta
        reg_info = phase_reg.block_info
        bps = parse_slx_params(reg_info['bin_pts'])
        b = float(2 ** int(bps[1]))
        max_positive_delta_phase = 1 - 1 / b
        max_negative_delta_phase = -1 + 1 / b
        dpos = delta_phase_offset_shifted
        dp = dpos / bitshift
        limited = False
        if dpos > max_positive_delta_phase:
            dpos = max_positive_delta_phase
            dp = dpos / bitshift
            LOGGER.warn('%s largest possible positive phase delta is '
                        '%e x pi radians/sample' % (infostr, dp))
            limited = True
        elif dpos < max_negative_delta_phase:
            dpos = max_negative_delta_phase
            dp = dpos / bitshift
            LOGGER.warn('%s largest possible negative phase delta is '
                        '%e x pi radians/sample' % (infostr, dp))
            limited = True
        if limited:
            LOGGER.warn('%s setting phase delta to %e x pi radians/sample '
                        '(%e after shift)' % (infostr, dp, dpos))
        # actually write the values to the register
        LOGGER.debug('%s writing phase delta to %e' % (infostr, dpos))
        try:
            phase_reg.write(delta=dpos)
        except ValueError as e:
            errmsg = '%s writing dpos(%.8e), error - %s' % (
                infostr, dpos, e.message)
            LOGGER.error(errmsg)
            raise ValueError(errmsg)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'Fengine @ input(%s:%i:%i) @ %s -> %s' % (
            self.name, self.input_number, self.offset, self.host,
            self.input)


class FpgaFHost(DigitiserStreamReceiver):
    """
    A Host, that hosts Fengines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, bitstream=None,
                 connect=True, config=None):
        super(FpgaFHost, self).__init__(host=host, katcp_port=katcp_port,
                                        bitstream=bitstream, connect=connect)

        self._config = config

        # list of Fengines received by this F-engine host
        self.fengines = []

        if config is not None:
            self.num_fengines = int(config['f_per_fpga'])
            self.ports_per_fengine = int(config['ports_per_fengine'])
            self.fft_shift = int(config['fft_shift'])
            self.n_chans = int(config['n_chans'])
            self.min_load_time = float(config['min_load_time'])
            self.network_latency_adjust = \
                float(config['network_latency_adjust'])
        else:
            self.num_fengines = None
            self.ports_per_fengine = None
            self.fft_shift = None
            self.n_chans = None
            self.min_load_time = None
            self.network_latency_adjust = None

        self.rx_data_sample_rate_hz = -1

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        bitstream = config_source['bitstream']
        return cls(hostname, katcp_port, bitstream=bitstream,
                   connect=True, config=config_source)

    def cd_okay(self, wait_time=1):
        """
        Is the coarse-delay functioning correctly? Only applicable to the
        QDR-based CD. Non-QDR CD will just return True.
        :param wait_time:
        :return:
        """
        if 'cd_ctrs' not in self.registers.names():
            LOGGER.info('%s: cd_okay() - no QDR-based CD found.' % self.host)
            return True
        cd_ctrs0 = self.registers.cd_ctrs.read()['data']
        time.sleep(wait_time)
        cd_ctrs1 = self.registers.cd_ctrs.read()['data']
        err0_diff = cd_ctrs1['cd_error_cnt0'] - cd_ctrs0['cd_error_cnt0']
        err1_diff = cd_ctrs1['cd_error_cnt1'] - cd_ctrs0['cd_error_cnt1']
        parerr0_diff = cd_ctrs1['cd_parerr_cnt0'] - cd_ctrs0['cd_parerr_cnt0']
        parerr1_diff = cd_ctrs1['cd_parerr_cnt1'] - cd_ctrs0['cd_parerr_cnt1']
        if err0_diff or err1_diff or parerr0_diff or parerr1_diff:
            LOGGER.error('%s: cd_okay() - FALSE, QDR CD error.' % self.host)
            return False
        LOGGER.info('%s: cd_okay() - TRUE.' % self.host)
        return True

    def ct_okay(self, wait_time=1):
        """
        Is the corner turner working?
        :param wait_time - time in seconds to wait between reg reads
        :return: True or False,
        """
        ct_ctrs0 = self.registers.ct_ctrs.read()['data']
        time.sleep(wait_time)
        ct_ctrs1 = self.registers.ct_ctrs.read()['data']
        err0_diff = ct_ctrs1['ct_err_cnt0'] - ct_ctrs0['ct_err_cnt0']
        err1_diff = ct_ctrs1['ct_err_cnt1'] - ct_ctrs0['ct_err_cnt1']
        parerr0_diff = ct_ctrs1['ct_parerr_cnt0'] - ct_ctrs0['ct_parerr_cnt0']
        parerr1_diff = ct_ctrs1['ct_parerr_cnt1'] - ct_ctrs0['ct_parerr_cnt1']
        if err0_diff or err1_diff or parerr0_diff or parerr1_diff:
            LOGGER.error('%s: ct_okay() - FALSE, CT error.' % self.host)
            return False
        LOGGER.info('%s: ct_okay() - TRUE.' % self.host)
        return True

    def host_okay(self):
        """
        Is this host/LRU okay?
        :return:
        """
        if ((not self.check_rx()) or
                (not self.ct_okay()) or
                (not self.cd_okay())):
            LOGGER.debug('%s: host_okay() - FALSE.' % self.host)
            return False
        LOGGER.debug('%s: host_okay() - TRUE.' % self.host)
        return True

    def add_fengine(self, fengine):
        """
        Add a new fengine to this fengine host
        :param fengine: A Fengine object
        :return:
        """
        # check that it doesn't already exist before adding it
        for feng in self.fengines:
            if feng.name == fengine.name:
                raise ValueError(
                    '%s == %s - cannot have two fengines with the same name '
                    'on one fhost' % (feng.name, fengine.name))
        self.fengines.append(fengine)

    def get_fengine(self, feng_name):
        """
        Get a fengine based on its input's name
        :param feng_name: name of the fengine to get
        :return:
        """
        try:
            feng_index = int(feng_name)
        except ValueError:
            feng_index = -1
        for feng in self.fengines:
            if feng_index == -1:
                if feng_name == feng.name:
                    return feng
            else:
                if feng.input_number == feng_index:
                    return feng
        raise InputNotFoundError('{host}: Fengine {feng} not found on this '
                                 'host.'.format(host=self.host, feng=feng_name))

    def read_eq(self, input_name=None, eq_bram=None):
        """
        Read a given EQ BRAM.
        :param input_name: the input name
        :param eq_bram: the name of the EQ BRAM to read
        :return: a list of the complex EQ values from RAM
        """
        if eq_bram is None and input_name is None:
            raise RuntimeError('Cannot have both tuple and name None')
        if input_name is not None:
            eq_bram = self.get_fengine(input_name).eq_bram_name
        # eq vals are packed as 32-bit complex (16 real, 16 imag)
        eqvals = self.read(eq_bram, self.n_chans*4)
        eqvals = struct.unpack('>%ih' % (self.n_chans*2), eqvals)
        eqcomplex = []
        for ctr in range(0, len(eqvals), 2):
            eqcomplex.append(eqvals[ctr] + (1j * eqvals[ctr+1]))
        return eqcomplex

    def write_eq_all(self):
        """
        Write the EQ variables to the device SBRAMs
        :return:
        """
        for feng in self.fengines:
            LOGGER.debug('%s: writing EQ %s' % (self.host, feng.name))
            self.write_eq(input_name=feng.name)

    def write_eq(self, input_name=None, eq_tuple=None):
        """
        Write a given complex eq to the given SBRAM.

        Specify either eq_tuple, a combination of sbram_name and value(s),
        OR input_name, but not both. If input_name is specified, the
        sbram_name and eq value(s) are read from the inputs.

        :param input_name: the name of the input that has the EQ to write
        :param eq_tuple: a tuple of an integer, complex number or list or
        integers or complex numbers and a sbram name
        :return:
        """
        if eq_tuple is None and input_name is None:
            raise RuntimeError('Cannot have both tuple and name None')
        if input_name is not None:
            feng = self.get_fengine(input_name)
            eq_bram = feng.eq_bram_name
            eq_poly = feng.eq_poly
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

    def _delay_arm_all_latches(self, loadmcnt, load_check=False):
        """
        
        :param loadmcnt: 
        :param load_check: 
        :return: 
        """
        latch_names = []
        for feng in self.fengines:
            latch_names.append('tl_cd%i' % feng.offset)
            latch_names.append('tl_fd%i' % feng.offset)
        status = self.arm_timed_latches(latch_names, mcnt=loadmcnt)
        arm_error = False
        for feng in self.fengines:
            arm_error = arm_error or feng.check_timed_latch(status, load_check)
        return arm_error

    def delay_set_all(self, loadmcnt, delay_list):
        """
        Set the delays for all inputs in the system
        :param loadmcnt: the system mcount at which to effect the delays
        :param delay_list: a list of delays for all the hosts in the array
        :return: a dictionary containing the applied delays for all the 
            fengines on this host.
        """
        delays_to_apply = delay_list[self.host]
        # set up the delays on all the f-engines
        an_fengine = None
        for feng in self.fengines:
            delay = delays_to_apply[feng.offset]
            feng.delay_set_calculate_and_write_regs(
                loadmcnt, delay[0][0], delay[0][1], delay[1][0], delay[1][1])
            an_fengine = feng
        # arm them all
        arm_error = self._delay_arm_all_latches(loadmcnt)
        # get and return the actual values loaded per fengine
        rv = {}
        for feng in self.fengines:
            actual_delay = feng.delay_set_actual_values(loadmcnt)
            if arm_error:
                actual_delay.error.set()
            rv[feng.name] = actual_delay
        return rv

    def delays_set(self, input_name, load_mcnt=None, delay=None,
                   delay_rate=None, phase=None, phase_rate=None):
        """
        Set the delay for a given input.
        :param input_name: the name of the input for which to set the delays
        :param load_mcnt: the system count at which to apply the delay
        :param delay: the delay, in seconds
        :param delay_rate: the rate of change
        :param phase:
        :param phase_rate:
        :return:
        """
        fengine = self.get_fengine(input_name)
        return fengine.delay_set(load_mcnt, delay, delay_rate, phase,
                                 phase_rate)

    def delays_get(self, input_name=None):
        """
        Get the applied delays for all f-engines on this host
        :param input_name: name of the input to get
        :return:
        """
        if input_name is None:
            return {feng.name: feng.delay_get() for feng in self.fengines}
        feng = self.get_fengine(input_name)
        return feng.delay_get()

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
        for name in names:
            control_reg = self.registers['%s_control' % name]
            control0_reg = self.registers['%s_control0' % name]
            status_reg = self.registers['%s_status' % name]
            status_before[name] = status_reg.read()['data']
            if mcnt is None:
                control0_reg.write(arm='pulse', load_immediate='pulse')
            else:
                load_time_lsw = mcnt - (int(mcnt/(2**32)))*(2**32)
                load_time_msw = int(mcnt/(2**32))
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
        :param shift_schedule: int representing bit mask. '1' represents a
        shift for that stage. First stage is MSB.
        Use default if None provided
        :param issue_meta: Should SPEAD meta data be sent after the value is
        changed?
        :return: <nothing>
        """
        if shift_schedule is None:
            shift_schedule = self.fft_shift
        self.registers.fft_shift.write(fft_shift=shift_schedule)

    def get_fft_shift(self):
        """
        Get the current FFT shift schedule from the FPGA.
        :return: integer representing the FFT shift schedule for all the FFTs
        on this engine.
        """
        return self.registers.fft_shift.read()['data']['fft_shift']

    def get_quant_snapshots(self):
        """
        Get the quant snapshots for all the inputs on this host.
        :return:
        """
        return {
            feng.name: self.get_quant_snapshot(feng.name)
            for feng in self.fengines
        }

    def get_quant_snapshot(self, input_name):
        """
        Read the post-quantisation snapshot for a given input
        :param input_name: the input name for which to read the quantiser
        snapshot data.
        :return:
        """
        feng = self.get_fengine(input_name)
        if feng.offset == 0:
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
        """

        :param pol:
        :return:
        """
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

    def check_qdr_devices(self, threshold=0):
        """
        Are the QDR devices behaving?
        :param threshold: how many errors are permisible?
        :return:
        """
        return (self.check_ct_parity(threshold) and
                self.check_cd_parity(threshold))

    def check_ct_parity(self, threshold):
        """
        Check the QDR corner turner parity error counters
        :param threshold: how many errors are permisible?
        :return:
        """
        return self._check_qdr_parity(
            qdr_id='CT',
            threshold=threshold,
            reg_name='ct_ctrs',
            reg_field_name='ct_parerr_cnt'
        )

    def get_cd_status(self):
        """
        Retrieves all the Coarse Delay status registers.
        """
        return self.registers.cd_status.read()['data']

    def check_cd(self):
        """
        Check the Coarse Delay, including any host memory errors.
        """
        d0=self.get_cd_status()
        if d0['pol0_parity_err_cnt']>0:
            LOGGER.error('%s: Parity errors on CD0.',self.host)    
            return False
        if d0['pol1_parity_err_cnt']>0:
            LOGGER.error('%s: Parity errors on CD1.',self.host)    
            return False
        d1=self.get_cd_status()
        if d1['hmc_err_cnt'] != d0['hmc_err_cnt']:
            LOGGER.error('%s: HMC err cnt changing.',self.host)    
            return False
        return True

    def get_ct_status(self):
        """
        Retrieve all the Corner-Turner registers.
        """ 
        if 'ct_status0' in self.registers.names():
            rv = self.registers.ct_status0.read()['data']
        else:
            rv = self.registers.ct_status.read()['data']
        try:
            rv.update(self.registers.ct_status1.read()['data'])
            rv.update(self.registers.ct_status2.read()['data'])
        except AttributeError or KeyError:
            pass
        try:
            rv['ct_dv_rate'] = self.registers.ct_dv_rate.read()['data']['reg']
        except AttributeError or KeyError:
            pass
        return rv

    def check_ct(self):
        """
        Check the Coarse Delay, including any host memory errors.
        """
        d0 = self.get_ct_status()
        if not d0['init']:
            LOGGER.error('%s: CT HMC did not init.',self.host)    
            return False
        if not d0['post']:
            LOGGER.error('%s: CT HMC did not POST.',self.host)    
            return False
        d1 = self.get_ct_status()
        if d0['err_bank'] != d1['err_bank']:
            LOGGER.error('%s: CT bank_err is changing.',self.host)    
            return False
        if d0['wr_ctr'] == d1['wr_ctr']:
            LOGGER.error('%s: Write counter is NOT changing.',self.host)    
            return False
        if d0['err_en_sync'] != d1['err_en_sync']:
            LOGGER.error('%s: CT err_en_sync is changing.',self.host)    
            return False
        if d0['err_rdrdy'] != d1['err_rdrdy']:
            LOGGER.error('%s: CT HMC read not ready is spinning.',self.host)
            return False
        if d0['err_wrrdy'] != d1['err_wrrdy']:
            LOGGER.error('%s: CT HMC write not ready is spinning.',self.host)
            return False
        return True 

    def check_cd_parity(self, threshold):
        """
        Check the QDR coarse delay parity error counters
        :param threshold: how many errors are permisible?
        :return:
        """
        if 'cd_ctrs' not in self.registers.names():
            LOGGER.info('check_qdr_parity: CD - no QDR-based coarse '
                        'delay found')
            return True
        return self._check_qdr_parity(
            qdr_id='CD',
            threshold=threshold,
            reg_name='cd_ctrs',
            reg_field_name='cd_parerr_cnt'
        )

    def _check_qdr_parity(self, qdr_id, threshold, reg_name, reg_field_name,):
        """
        Check QDR parity error counters
        :return:
        """
        LOGGER.info('%s: checking %s parity errors (QDR test)' % (
            self.host, qdr_id))
        if threshold == 0:
            _required_bits = 1
        else:
            _required_bits = int(numpy.ceil(numpy.log2(threshold)))
        # does the loaded bitstream have wide-enough counters?
        _register = self.registers[reg_name]
        bitwidth = _register.field_get_by_name(reg_field_name + '0').width_bits
        if bitwidth < _required_bits:
            LOGGER.warn(
                '\t{qdrid} parity error counter is too narrow: {bw} < {rbw}. '
                'NOT running test.'.format(
                    qdrid=qdr_id, bw=bitwidth, rbw=_required_bits))
            return True
        ctrs = self.registers[reg_name].read()['data']
        for pol in [0, 1]:
            fname = reg_field_name + str(pol)
            if (ctrs[fname] > 0) and (ctrs[fname] < threshold):
                LOGGER.warn('\t{h}: {thrsh} > {nm} > 0. Que pasa?'.format(
                    h=self.host, nm=fname, thrsh=threshold))
            elif (ctrs[fname] > 0) and (ctrs[fname] >= threshold):
                LOGGER.error('\t{h}: {nm} > {thrsh}. Problems.'.format(
                    h=self.host, nm=fname, thrsh=threshold))
                return False
        return True

    def check_fft_overflow(self, wait_time=2e-3):
        """
        Checks if pfb counters on f-eng are not incrementing i.e. fft
        is not overflowing
        :param wait_time - time in seconds to wait between reg reads
        :return: True/False
        """
        ctrs0 = self.registers.pfb_status.read()['data']
        time.sleep(wait_time)
        ctrs1 = self.registers.pfb_status.read()['data']
        for cnt in range(0, 1):
            overflow0 = ctrs0['pol%i_or_err_cnt' % cnt]
            overflow1 = ctrs1['pol%i_or_err_cnt' % cnt]
            if overflow0 != overflow1:
            #     LOGGER.info('%s: pol%i_or_err_cnt okay.' % (self.host, cnt))
            # else:
                LOGGER.debug('%s: pol%i_or_err_cnt incrementing.' % (
                    self.host, cnt))
                return False
        LOGGER.info('%s: PFB okay.' % self.host)
        return True

    def get_adc_snapshot_for_input(self, input_name, unix_time=-1):
        """
        Read the small voltage buffer for a input from a host.
        :param input_name: the input name
        :param unix_time: the time at which to read
        :return: AdcData()
        """
        feng = self.get_fengine(input_name)
        if unix_time == -1:
            d = self.get_adc_snapshots_timed(from_now=2)
        else:
            d = self.get_adc_snapshots_timed(loadtime_unix=unix_time)
        return d['p%i' % feng.offset]

    def _get_adc_timed_convert_times(
            self, from_now=2, loadtime_unix=-1,
            loadtime_system=-1, localtime=-1):
        """
        Given trigger times as a number of options, convert them to a
        single system time.
        :param from_now: trigger x seconds from now, default is two
        :param loadtime_unix: the load time as a UNIX time
        :param loadtime_system: the load time as a system board time.
        :param localtime: pass the system localtime, in ticks, to the function
        :return: localtime, system load time
        """
        start_tic = time.time()
        if localtime == -1:
            localtime = self.get_local_time()
        if localtime & ((2**12) - 1) != 0:
            errmsg = 'Bottom 12 bits of local time are not zero? %i' % localtime
            LOGGER.error(errmsg)
            raise ValueError(errmsg)
        if loadtime_system != -1:
            if loadtime_system & ((2**12) - 1) != 0:
                errmsg = 'Time resolution from the digitiser is only 2^12, ' \
                         'trying to trigger at %i would never ' \
                         'work.' % loadtime_system
                LOGGER.error(errmsg)
                raise ValueError(errmsg)
            return localtime, loadtime_system
        if loadtime_unix != -1:
            timediff = loadtime_unix - start_tic
        else:
            timediff = from_now
        timediff_samples = (timediff * 1.0) * self.rx_data_sample_rate_hz
        loadtime = int(localtime + timediff_samples)
        loadtime += 2**12
        loadtime = (loadtime >> 12) << 12
        return localtime, loadtime

    def get_adc_snapshots_timed(self, from_now=2, loadtime_unix=-1,
                                loadtime_system=-1, localtime=-1):
        """
        Get a snapshot of incoming ADC data at a specific time.
        :param from_now: trigger x seconds from now
        :param loadtime_unix: the load time as a UNIX time
        :param loadtime_system: the load time as a system board time.
        :param localtime: pass the system localtime, in ticks, to the function
        Default is 2 seconds in the future.
        :return {'p0': AdcData(), 'p1': AdcData()}
        """
        if self.rx_data_sample_rate_hz == -1:
            raise ValueError('Cannot continue with unknown input sample '
                             'rate. Please set this with: '
                             '\'host.rx_data_sample_rate_hz = xxxx\' first.')

        if 'adc_snap_trig_select' not in self.registers.control.field_names():
            raise NotImplementedError('Timed ADC snapshot support does '
                                      'not exist on older F-engines.')

        tic = time.time()
        localtime, loadtime = self._get_adc_timed_convert_times(
            from_now=from_now, loadtime_unix=loadtime_unix,
            loadtime_system=loadtime_system, localtime=localtime)

        if loadtime <= localtime:
            errmsg = 'A load time in past makes no sense. %i < %i = %i' % (
                loadtime, localtime, loadtime - localtime)
            LOGGER.error(errmsg)
            raise ValueError(errmsg)

        custom_timeout = int((loadtime - localtime) /
                             self.rx_data_sample_rate_hz) + 1

        ltime_msw = (loadtime >> 32) & (2**16 - 1)
        ltime_lsw = loadtime & ((2**32) - 1)
        self.registers.trig_time_msw.write_int(ltime_msw)
        self.registers.trig_time_lsw.write_int(ltime_lsw)
        snap_tic = time.time()
        rv = self.get_adc_snapshots(trig_sel=0, custom_timeout=custom_timeout)
        toc = time.time()
        LOGGER.debug('%s: timed ADC read took %.3f sec, total %.3f sec' % (
            self.host, (toc - snap_tic), (toc - tic)))
        if ((loadtime >> 12) & ((2**32)-1)) != rv['p0'].timestamp:
            errmsg = 'ADC data not read at specified time: %i != %s' % (
                loadtime, str(rv['p0'].timestamp))
            LOGGER.error(errmsg)
            raise RuntimeError(errmsg)
        rv['p0'].timestamp = loadtime
        rv['p1'].timestamp = loadtime
        return rv

    def get_adc_snapshots(self, trig_sel=1, custom_timeout=-1):
        """
        Read the ADC snapshots from this Fhost
        :param trig_sel: 0 for time-trigger, 1 for constant trigger
        :param custom_timeout: should a custom timeout be applied to the
        snapshot read operation?
        :return {'p0': AdcData(), 'p1': AdcData()}
        """
        if 'p1_d3' not in self.snapshots.snap_adc0_ss.field_names():
            return self._get_adc_snapshots_compat()
        if 'adc_snap_trig_select' in self.registers.control.field_names():
            self.registers.control.write(adc_snap_trig_select=trig_sel)
        self.registers.control.write(adc_snap_arm=0)
        self.snapshots.snap_adc0_ss.arm()
        self.snapshots.snap_adc1_ss.arm()
        self.registers.control.write(adc_snap_arm=1)
        if custom_timeout != -1:
            d = self.snapshots.snap_adc0_ss.read(
                arm=False, timeout=custom_timeout)
            time48 = d['extra_value']['data']['timestamp']
            d = d['data']
            d.update(self.snapshots.snap_adc1_ss.read(
                arm=False, timeout=custom_timeout)['data'])
        else:
            d = self.snapshots.snap_adc0_ss.read(arm=False)
            time48 = d['extra_value']['data']['timestamp']
            d = d['data']
            d.update(self.snapshots.snap_adc1_ss.read(arm=False)['data'])
        self.registers.control.write(adc_snap_arm=0)
        # process p1_d4, which was broken up over two snapshots
        d['p1_d4'] = []
        for ctr in range(len(d['p1_d4_u8'])):
            tmp = (d['p1_d4_u8'][ctr] << 2) | d['p1_d4_l2'][ctr]
            d['p1_d4'].append(caspermem.bin2fp(tmp, 10, 9, True))
        # pack the data into simple lists
        rvp0 = []
        rvp1 = []
        for ctr in range(0, len(d['p0_d0'])):
            for ctr2 in range(8):
                rvp0.append(d['p0_d%i' % ctr2][ctr])
                rvp1.append(d['p1_d%i' % ctr2][ctr])
        return {'p0': AdcData(time48, rvp0),
                'p1': AdcData(time48, rvp1)}

    def _get_adc_snapshots_compat(self):
        """
        Old implementations of reading the ADC snapshots, included for
        compatibility.
        :return {'p0': AdcData(), 'p1': AdcData()}
        """
        if 'p1_4' in self.snapshots.snap_adc0_ss.field_names():
            # temp new style
            self.registers.control.write(adc_snap_arm=0)
            self.snapshots.snap_adc0_ss.arm()
            self.snapshots.snap_adc1_ss.arm()
            self.registers.control.write(adc_snap_arm=1)
            d = self.snapshots.snap_adc0_ss.read(arm=False)['data']
            d.update(self.snapshots.snap_adc1_ss.read(arm=False)['data'])
            self.registers.control.write(adc_snap_arm=0)
            p0 = {'d%i' % ctr: d['p0_d%i' % ctr] for ctr in range(8)}
            p1 = {'d%i' % ctr: d['p1_%i' % ctr]
                  for ctr in [0, 1, 2, 4, 5, 6, 7]}
            p1['d3'] = []
            for ctr in range(len(d['p1_3_u8'])):
                _tmp = (d['p1_3_u8'][ctr] << 2) | d['p1_3_l2'][ctr]
                p1['d3'].append(caspermem.bin2fp(_tmp, 10, 9, True))
        else:
            p0 = self.snapshots.snap_adc0_ss.read()['data']
            p1 = self.snapshots.snap_adc1_ss.read()['data']
        # pack the data into simple lists
        rvp0 = []
        rvp1 = []
        for ctr in range(0, len(p0['d0'])):
            for ctr2 in range(8):
                rvp0.append(p0['d%i' % ctr2][ctr])
                rvp1.append(p1['d%i' % ctr2][ctr])
        return {'p0': AdcData(-1, rvp0),
                'p1': AdcData(-1, rvp1)}


    def _skarab_subscribe_to_multicast(self):
        """

        :return:
        """
        logstr = ''
        first_ip = self.fengines[0].input.destination.ip_address
        ip_str = str(first_ip)
        ip_range = 0
        for ctr, feng in enumerate(self.fengines):
            this_ip = feng.input.destination
            if int(this_ip.ip_address) != int(first_ip) + ip_range:
                raise RuntimeError('F-engine input sources IPs are not '
                                   'in a contiguous chunk. This will cause '
                                   'multicast subscription problems.')
            ip_range += this_ip.ip_range
        gbename = self.gbes.names()[0]
        gbe = self.gbes[gbename]
        logstr += ' %s(%s+%i)' % (gbe.name, ip_str, ip_range - 1)
        gbe.multicast_receive(ip_str, ip_range)
        return logstr

    def _roach2_subscribe_to_multicast(self, f_per_fpga):
        """

        :param f_per_fpga:
        :return:
        """
        logstr = ''
        gbe_ctr = 0
        feng_ctr = 0
        for feng in self.fengines:
            input_addr = feng.input.destination
            if not input_addr.is_multicast():
                logstr += ' feng%i[source address %s is not ' \
                          'multicast?]' % (feng_ctr, input_addr.ip_address)
                continue
            rxaddr = str(input_addr.ip_address)
            rxaddr_bits = rxaddr.split('.')
            rxaddr_base = int(rxaddr_bits[3])
            rxaddr_prefix = '%s.%s.%s.' % (
                rxaddr_bits[0], rxaddr_bits[1], rxaddr_bits[2])
            if (len(self.gbes) / f_per_fpga) != input_addr.ip_range:
                raise RuntimeError(
                    '10Gbe ports (%d) do not match sources IPs (%d)' %
                    (len(self.gbes), input_addr.ip_range))
            logstr += ' feng%i[' % feng_ctr
            for ctr in range(0, input_addr.ip_range):
                gbename = self.gbes.names()[gbe_ctr]
                gbe = self.gbes[gbename]
                rxaddress = '%s%d' % (rxaddr_prefix, rxaddr_base + ctr)
                logstr += ' %s(%s)' % (gbe.name, rxaddress)
                gbe.multicast_receive(rxaddress, 0)
                gbe_ctr += 1
            logstr += ']'
            feng_ctr += 1
        return logstr

    def subscribe_to_multicast(self, f_per_fpga):
        """
        
        :return: 
        """
        logstr = '\t%s:' % self.host
        gbe0_name = self.gbes.names()[0]
        if self.gbes[gbe0_name].block_info['tag'] == 'xps:forty_gbe':
            logstr += self._skarab_subscribe_to_multicast()
        else:
            logstr += self._roach2_subscribe_to_multicast(f_per_fpga)
        LOGGER.info(logstr)

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
            return self.host.device_by_name( '%sfft_shift' % self.tag)
        # we can't access Shared BRAMs in the same way as we access registers
        # at the moment, so we access the name and use read/write
        elif name == 'eq0_name':
            return  '%seq  %s' %' (self.tag, self.pol0_offset)
        elif name == 'eq1_name':
            return  '%seq  %s' %' (self.tag, self.pol1_offset)
        # fengines transmit to multiple xengines. Each xengine processes a continuous band of
        # frequencies with the lowest numbered band from all antennas being processed by the first xengine
        # and so on. The xengines have IP addresses starting a txip_base and increasing linearly. Some xengines
        # may share IP addresses
        elif name == 'txip_base':
            return self.host.device_by_name( '%stxip_base  %s' %' (self.tag, self.offset))
        elif name == 'txport':
            return self.host.device_by_name( '%stxport  %s' %' (self.tag, self.offset))
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

        poly = self.config['equalisation']['poly  %s' %' pol_index]
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
