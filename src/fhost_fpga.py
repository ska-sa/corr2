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

    def get_local_time(self,src=0):
        """
        Get the local timestamp of this board, received from the digitiser
        :param: src: 0 for direct (out of unpack), 1 is out of reorder, 2 out of PFB, 3 into pack block.
        :return: time in samples since the digitiser epoch
        """
        self.registers.control.write(local_time_source=src)
        self.registers.control.write(local_time_capture='pulse')
        lsw = self.registers.local_time_lsw.read()['data']['timestamp_lsw']
        msw = self.registers.local_time_msw.read()['data']['timestamp_msw']
        rv = (msw << 32) | lsw
        return rv


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

    def get_cd_status(self):
        """
        Retrieves all the Coarse Delay status registers.
        """
        return self.registers.cd_status.read()['data']

    def get_ct_status(self):
        """
        Retrieve all the Corner-Turner registers.
        returns a list (one per pol on board) of status dictionaries.
        """ 
        rv=[]
        for pol in range(self.num_fengines):
            rv.append(self.registers['hmc_ct_err_status%i' %pol].read()['data'])
        return rv
        
        #rv = self.registers.ct_status0.read()['data']
        #for ctr in range(1, 7):
        #    try:
        #        rv.update(self.registers['ct_status%i' % ctr].read()['data'])
        #    except (AttributeError, KeyError):
        #        pass
        #try:
        #    reg = self.registers.ct_out_dv_rate
        #    rv['out_dv_rate'] = reg.read()['data']['reg']
        #    reg = self.registers.ct_in_dv_rate
        #    rv['in_dv_rate'] = reg.read()['data']['reg']
        #except (AttributeError, KeyError):
        #    pass
        #try:

        #    rv.update(self.registers.ct_dv_err.read()['data'])
        #except (AttributeError, KeyError):
        #    pass
        #return rv

    def check_ct_overflow(self):
        """
        Check the Corner-Turner for overflow errors.
        Stop F-Engine output if overflow error detected.
        :return:
        """

        # define registers to check
        reg = ('rd_not_rdy', 'wr_not_rdy')
        ct_overflow_status = []

        for pol in self.get_ct_status():
            ct_overflow_status.append(any([pol[key] for key in reg]))

        ct_overflow = any(ct_overflow_status)

        # if overflow detected, stop F-engine output
        if ct_overflow:
            LOGGER.warning("corner-turner overflow. stopping Feng %s output"
                           % self.host)
            self.registers.control.write(gbe_txen=False)
            return True
        else:
            LOGGER.info("Feng: %s : no corner-turner overflow errs. ok!" %
                        self.host)
            return False

    def get_pfb_status(self):
        """
        Returns the pfb counters on f-eng
        :return: dict
        """
        return self.registers.pfb_status.read()['data']


    def get_adc_snapshots(self, input_name=None, loadcnt=0, timeout=10):
        """
        Read the ADC snapshots from this Fhost
        :param loadcnt: the trigger/load time in ADC samples.
        :param timeout: timeout in seconds for snapshot read operation.
        :return {'p0': AdcData(), 'p1': AdcData()}
        """
        if input_name != None: 
            fengine = self.get_fengine(input_name)
        if loadcnt>0:
            LOGGER.info("Triggering ADC snapshot at %i"%loadcnt)
            ltime_msw = (loadcnt >> 32) & (2**16 - 1)
            ltime_lsw = loadcnt & ((2**32) - 1)
            self.registers.trig_time_msw.write_int(ltime_msw)
            self.registers.trig_time_lsw.write_int(ltime_lsw)
            self.snapshots.snap_adc0_ss.arm()
            self.snapshots.snap_adc1_ss.arm()
        else:
            self.snapshots.snap_adc0_ss.arm(man_trig=True)
            self.snapshots.snap_adc1_ss.arm(man_trig=True)

        d0 = self.snapshots.snap_adc0_ss.read(arm=False, timeout=timeout)
        d1 = self.snapshots.snap_adc1_ss.read(arm=False, timeout=timeout)
        time48_0 = d0['extra_value']['timestamp']
        time48_1 = d1['extra_value']['timestamp']
        d = d0['data']
        d.update(d1['data'])

        # pack the data into simple lists
        rvp0 = []
        rvp1 = []
        for ctr in range(0, len(d['p0_d0'])):
            for ctr2 in range(8):
                rvp0.append(d['p0_d%i' % ctr2][ctr])
                rvp1.append(d['p1_d%i' % ctr2][ctr])
        rv= {'p0': AdcData(time48_0, rvp0),
             'p1': AdcData(time48_1, rvp1)}
        if input_name != None:
            return rv['p%i' % fengine.offset]
        else:
            return rv


    def get_pack_status(self):
        """
        Read the pack (output) status registers.
        """
        return self.registers.pack_dv_err.read()['data']

    def get_unpack_status(self):
        """
        Returns the SPEAD counters on this FPGA.
        """
        rv = None
        rv = self.registers.unpack_status.read()['data']
        rv.update(self.registers.unpack_status1.read()['data'])
        return rv

    def get_rx_reorder_status(self):
        """
        Read the reorder block counters
        :return:
        """
        if 'reorder_ctrs' in self.registers.names():
            return self.registers.reorder_ctrs.read()['data']
        elif 'reorder_status' in self.registers.names():
            rv=self.registers.reorder_status.read()['data']
        if 'reorder_status1' in self.registers.names():
            rv.update(self.registers.reorder_status1.read()['data'])
        return rv

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
