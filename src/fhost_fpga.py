import time
import logging
import struct

import casperfpga.memory as caspermem

from delay import Delay
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


class Fengine(object):
    """
    An F-engine, acting on a source DataStream
    """
    def __init__(self, input_stream,
                 host=None, offset=-1,
                 sensor_manager=None):
        """

        :param input_stream: the DigitiserStream input for this F-engine
        :param host: the Fpga host on which this input is received
        :param offset: which input on that host is this?
        :param sensor_manager: a SensorManager instance
        :return:
        """
        self.input = input_stream
        self.host = host
        self.offset = offset
        self.eq_poly = None
        self.eq_bram_name = 'eq%i' % offset
        self.delay = Delay()
        self.sensor_manager = sensor_manager

        # TODO - sensors, sensors, sensors - does this level of object know about them?! I should think not...
        # if sensor_manager is not None:
        #     create_input_delay_sensors(self)

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
    
    def set_delay(self, delay=0.0, delay_delta=0.0,
                  phase_offset=0.0, phase_offset_delta=0.0,
                  load_time=None, load_wait=None, load_check=True):
        """
        Update delay settings for data stream at offset specified
        ready for writing

        :param delay is in samples
        :param delay_delta is in samples per sample
        :param phase_offset is in fractions of a sample
        :param phase_offset_delta is in samples per sample
        :param load_time is in samples since epoch
        :param load_wait is seconds to wait for delay values to load
        :param load_check whether to check if load happened
        :return 
        """
        self.delay.delay = delay
        self.delay.delay_delta = delay_delta
        self.delay.phase_offset = phase_offset
        self.delay.phase_offset_delta = phase_offset_delta
        self.delay.load_time = load_time
        self.delay.load_wait = load_wait
        self.delay.load_check = load_check
        if self.sensor_manager is not None:
            self.sensor_manager.sensor_set(
                sensor=('%s-delay-set' % self.name).replace('_', '-'),
                value='%.5f,%.5f' % (self.delay.delay, self.delay.delay_delta))
            self.sensor_manager.sensor_set(
                sensor=('%s-phase-set' % self.name).replace('_', '-'),
                value='%.5f,%.5f' % (self.delay.phase_offset,
                                     self.delay.phase_offset_delta))
            self.sensor_manager.sensor_set(
                sensor=('%s-loadtime' % self.name).replace('_', '-'),
                value=self.delay.load_time)

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
    def __init__(self, host, katcp_port=7147, boffile=None,
                 connect=True, config=None):
        super(FpgaFHost, self).__init__(host,
                                        katcp_port=katcp_port,
                                        boffile=boffile,
                                        connect=connect)

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
        boffile = config_source['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile,
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
            LOGGER.error('%s: host_okay() - FALSE.' % self.host)
            return False
        LOGGER.info('%s: host_okay() - TRUE.' % self.host)
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
        for feng in self.fengines:
            if feng.name == feng_name:
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

    def _delay_get_status_registers(self):
        """
        Get the status registers for the delay operations on this f-host
        :return:
        """
        num_pols = len(self.fengines)
        rv = []
        for pol in range(num_pols):
            rv.append(self.registers['tl_cd%i_status' % pol].read()['data'])
        return rv

    def delay_check_loadcounts(self):
        """
        Are new delays being loaded on this fhost?
        :return: True is the load counts are increasing, false if not
        """
        new_status = self._delay_get_status_registers()
        rv = True
        for feng in self.fengines:
            new_val = new_status[feng.offset]['load_count']
            old_val = feng.delay.load_count
            if old_val != -1:
                if old_val == new_val:
                    rv = False
            feng.delay.load_count = new_val
        return rv

    def check_delays(self):
        """
        Check the delay error events
        :return: True for all okay, False for errors present
        """
        okay = True
        for feng in self.fengines:
            okay = okay and (not feng.delay.error.is_set())
        return okay

    def write_delays_all(self):
        """
        Goes through all offsets and writes delays with stored delay settings
        """
        act_vals = []
        for feng in self.fengines:
            act_val = self.write_delay(fengine=feng)
            act_vals.append(act_val)
        return act_vals

    @staticmethod
    def _write_delay_delay(infostr, bitshift, delay_reg, delay_delta_reg,
                           delay, delay_delta):
        """
        Do the delta delay portion of write_delay
        :return:
        """
        # TODO check register parameters to get delay range

        reg_info = delay_reg.block_info
        reg_bw = int(parse_slx_params(reg_info['bitwidths'])[0])
        reg_bp = int(parse_slx_params(reg_info['bin_pts'])[0])
        max_delay = 2**(reg_bw - reg_bp) - 1/float(2**reg_bp)

        LOGGER.info('%s attempting initial delay of %f samples.' %
                    (infostr, delay))
        if delay < 0:
            LOGGER.warn('%s smallest delay is 0, setting to zero' % infostr)
            delay = 0
        elif delay > max_delay:
            LOGGER.warn('%s largest possible delay is %f data samples' % (
                infostr, max_delay))
            delay = max_delay
        LOGGER.info('%s setting delay to %f data samples' % (infostr, delay))
        try:
            delay_reg.write(initial=delay)
        except ValueError as e:
            _err = '%s writing initial delay range delay(%.8e), error - %s' % (
                infostr, delay, e.message)
            LOGGER.error(_err)
            raise ValueError(_err)

        # shift up by amount shifted down by on fpga
        delta_delay_shifted = float(delay_delta) * bitshift
        dds = delta_delay_shifted
        dd = dds / bitshift

        LOGGER.info('%s attempting delay delta to %e (%e after shift)' %
                    (infostr, delay_delta, delta_delay_shifted))
        reg_info = delay_delta_reg.block_info
        b = int(reg_info['bin_pts'])

        max_positive_delta_delay = 1 - 1/float(2**b)
        max_negative_delta_delay = -1 + 1/float(2**b)
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
        LOGGER.info('%s writing delay delta to %e (%e after shift)' %
                    (infostr, dd, dds))
        try:
            delay_delta_reg.write(delta=dds)
        except ValueError as e:
            _err = '%s writing delay delta (%.8e), error - %s' % \
                   (infostr, dds, e.message)
            LOGGER.error(_err)
            raise ValueError(_err)

    @staticmethod
    def _write_delay_phase(infostr, bitshift, phase_reg, phase_offset,
                           phase_offset_delta):
        """
        :return:
        """
        # multiply by amount shifted down by on FPGA
        delta_phase_offset_shifted = float(phase_offset_delta) * bitshift

        LOGGER.info('%s attempting to set initial phase to %f and phase '
                    'delta to %e' % (infostr, phase_offset,
                                     delta_phase_offset_shifted))
        # setup the phase offset
        reg_info = phase_reg.block_info
        bps = parse_slx_params(reg_info['bin_pts'])
        b = float(2**int(bps[0]))
        max_positive_phase_offset = 1 - 1/b
        max_negative_phase_offset = -1 + 1/b
        if phase_offset > max_positive_phase_offset:
            phase_offset = max_positive_phase_offset
            LOGGER.warn('%s largest possible positive phase offset is '
                        '%e pi' % (infostr, phase_offset))
            LOGGER.warn('%s setting phase offset to %e pi' % (
                infostr, phase_offset))
        elif phase_offset < max_negative_phase_offset:
            phase_offset = max_negative_phase_offset
            LOGGER.warn('%s largest possible negative phase_offset is '
                        '%e pi' % (infostr, phase_offset))
            LOGGER.warn('%s setting phase offset to %e pi' % (
                infostr, phase_offset))

        # phase delta
        b = float(2**int(bps[1]))
        max_positive_delta_phase = 1 - 1/b
        max_negative_delta_phase = -1 + 1/b
        dpos = delta_phase_offset_shifted
        dp = dpos / bitshift
        if dpos > max_positive_delta_phase:
            dpos = max_positive_delta_phase
            dp = dpos / bitshift
            LOGGER.warn('%s largest possible positive phase delta is '
                        '%expi radians/sample' % (infostr, dp))
            LOGGER.warn('%s setting phase delta to %expi radians/sample '
                        '(%e after shift)' % (infostr, dp, dpos))
        elif dpos < max_negative_delta_phase:
            dpos = max_negative_delta_phase
            dp = dpos / bitshift
            LOGGER.warn('%s largest possible negative phase delta is '
                        '%expi radians/sample' % (infostr, dp))
            LOGGER.warn('%s setting phase delta to %expiradians/sample '
                        '(%e after shift)' % (infostr, dp, dpos))

        # actually write the values to the register
        LOGGER.info('%s writing initial phase to %f' % (infostr, phase_offset))
        LOGGER.info('%s writing phase delta to %e' % (infostr, dpos))
        try:
            phase_reg.write(initial=phase_offset, delta=dpos)
        except ValueError as e:
            _err = '%s writing phase(%.8e) dpos(%.8e), error - %s' % \
                   (infostr, phase_offset, dpos, e.message)
            LOGGER.error(_err)
            raise ValueError(_err)

    @staticmethod
    def _get_delay_bitshift():
        """

        :return:
        """
        # TODO should this be in config file?
        bitshift_schedule = 23
        bitshift = (2**bitshift_schedule)
        return bitshift

    def _get_delay_regs(self, offset):
        """
        What are the registers associated with delays at this offset?
        :param offset:
        :return: a tuple of delay, delta and phase registers
        """
        delay_reg = self.registers['delay%i' % offset]
        delay_delta_reg = self.registers['delta_delay%i' % offset]
        phase_reg = self.registers['phase%i' % offset]
        return delay_reg, delay_delta_reg, phase_reg

    def write_delay(self, fengine):
        """
        Configures a given stream to a delay in samples and phase in degrees.

        The sample count at which this happens can be specified (default is
        immediate if not specified).
        If a load_check_time is specified, function will block until that
        time before checking.
        By default, it will load immediately and verify that things worked
        as expected.

        :param fengine: the fengine for which to apply delays
        :return actual values to be loaded
        """
        bitshift = self._get_delay_bitshift()
        offset = fengine.offset
        dly = fengine.delay

        delay_reg, delay_delta_reg, phase_reg = self._get_delay_regs(offset)

        _infstr = '%s:%i:%i:' % (self.host, offset, dly.load_time)
        self._write_delay_delay(_infstr, bitshift, delay_reg, delay_delta_reg,
                                dly.delay, dly.delay_delta)
        self._write_delay_phase(_infstr, bitshift, phase_reg, dly.phase_offset,
                                dly.phase_offset_delta)

        cd_tl_name = 'tl_cd%i' % offset
        fd_tl_name = 'tl_fd%i' % offset
        status = self.arm_timed_latches(
            [cd_tl_name, fd_tl_name],
            mcnt=dly.load_time,
            check_time_delay=dly.load_wait)
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
        if cd_armed_before:
            LOGGER.error('%s coarse delay timed latch was already armed. '
                         'Previous load failed.' % _infstr)
            dly.error.set()

        if fd_armed_before:
            LOGGER.error('%s phase correction timed latch was already '
                         'armed. Previous load failed.' % _infstr)
            dly.error.set()

        # did the system arm correctly
        if (not cd_armed_before) and (cd_arm_count_before == cd_arm_count_after):
            LOGGER.error('%s coarse delay arm count did not change.' % _infstr)
            LOGGER.error('%s BEFORE: coarse arm_count(%i) ld_count(%i)' %
                         (_infstr, cd_arm_count_before, cd_ld_count_before))
            LOGGER.error('%s AFTER:  coarse arm_count(%i) ld_count(%i)' %
                         (_infstr, cd_arm_count_after, cd_ld_count_after))
            dly.error.set()

        if (not fd_armed_before) and (fd_arm_count_before == fd_arm_count_after):
            LOGGER.error('%s phase correction arm count did not change.' %
                         _infstr)
            LOGGER.error('%s BEFORE: phase correction arm_count(%i) '
                         'ld_count(%i)' %
                         (_infstr, fd_arm_count_before, fd_ld_count_before))
            LOGGER.error('%s AFTER:  phase correction arm_count(%i) '
                         'ld_count(%i)' %
                         (_infstr, fd_arm_count_after, fd_ld_count_after))
            dly.error.set()

        # did the system load?
        if dly.load_check:
            if cd_ld_count_before == cd_ld_count_after:
                LOGGER.error('%s coarse delay load count did not change. '
                             'Load failed.' % _infstr)
                dly.error.set()

            if fd_ld_count_before == fd_ld_count_after:
                LOGGER.error('%s phase correction load count did not '
                             'change. Load failed.' % _infstr)
                dly.error.set()

        # read values back to see what actual values were loaded
        act_delay = delay_reg.read()['data']['initial']
        act_delay_delta = delay_delta_reg.read()['data']['delta'] / bitshift
        act_phase_offset = phase_reg.read()['data']['initial']
        act_phase_offset_delta = phase_reg.read()['data']['delta'] / bitshift
        return {
            'act_delay': act_delay,
            'act_delay_delta': act_delay_delta,
            'act_phase_offset': act_phase_offset,
            'act_phase_offset_delta': act_phase_offset_delta,
        }

    # def read_delay(self, source):
    #     """
    #     Read registers containing delay values actually set in hardware.
    #     :return: dictionary
    #     """
    #     bitshift = self._get_delay_bitshift()
    #     delay_reg, delay_delta_reg, phase_reg = self._get_delay_regs(source.offset)
    #
    #     # read values back to see what actual values were loaded
    #     act_delay = delay_reg.read()['data']['initial']
    #     act_delay_delta = delay_delta_reg.read()['data']['delta'] / bitshift
    #     act_phase_offset = phase_reg.read()['data']['initial']
    #     act_phase_offset_delta = phase_reg.read()['data']['delta'] / bitshift
    #     return {
    #         'act_delay': act_delay,
    #         'act_delay_delta': act_delay_delta,
    #         'act_phase_offset': act_phase_offset,
    #         'act_phase_offset_delta': act_phase_offset_delta,
    #     }

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
        err_data = self.registers.ct_ctrs.read()['data']
        for cnt in range(0, 1):
            err = err_data['ct_parerr_cnt%d' % cnt]
            if err == 0:
                LOGGER.info('%s: ct_parerr_cnt%d okay.' % (self.host, cnt))
            else:
                LOGGER.error('%s: ct_parerr_cnt%d not zero.' % (self.host, cnt))
                return False
        LOGGER.info('%s: QDR okay.' % self.host)
        return True

    def check_fft_overflow(self, wait_time=2e-3):
        """
        Checks if pfb counters on f-eng are not incrementing i.e. fft
        is not overflowing
        :param wait_time - time in seconds to wait between reg reads
        :return: True/False
        """
        ctrs0 = self.registers.pfb_ctrs.read()['data']
        time.sleep(wait_time)
        ctrs1 = self.registers.pfb_ctrs.read()['data']
        for cnt in range(0, 1):
            overflow0 = ctrs0['pfb_of%d_cnt' % cnt]
            overflow1 = ctrs1['pfb_of%d_cnt' % cnt]
            if overflow0 == overflow1:
                LOGGER.info('%s: pfb_of%d_cnt okay.' % (self.host, cnt))
            else:
                LOGGER.error('%s: pfb_of%d_cnt incrementing.' % (
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
            LOGGER.exception('Bottom 12 bits of local time are not '
                             'zero? %i' % localtime)
            raise ValueError('Bottom 12 bits of local time are not '
                             'zero? %i' % localtime)
        if loadtime_system != -1:
            if loadtime_system & ((2**12) - 1) != 0:
                LOGGER.exception('Time resolution from the digitiser is '
                                 'only 2^12, trying to trigger at %i would '
                                 'never work.' % loadtime_system)
                raise ValueError('Time resolution from the digitiser is '
                                 'only 2^12, trying to trigger at %i would '
                                 'never work.' % loadtime_system)
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
            LOGGER.exception(
                'A load time in past makes no sense. %i < %i = %i' % (
                    loadtime, localtime, loadtime - localtime))
            raise ValueError(
                'A load time in past makes no sense. %i < %i = %i' % (
                    loadtime, localtime, loadtime - localtime))

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
            err_str = 'ADC data not read at specified time: %i != %s' % (
                loadtime, str(rv['p0'].timestamp))
            LOGGER.error(err_str)
            raise RuntimeError(err_str)
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
            _tmp = (d['p1_d4_u8'][ctr] << 2) | d['p1_d4_l2'][ctr]
            d['p1_d4'].append(caspermem.bin2fp(_tmp, 10, 9, True))
        # pack the data into simple lists
        rvp0 = []
        rvp1 = []
        for ctr in range(0, len(d['p0_d0'])):
            for ctr2 in range(0, 8):
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
            for ctr2 in range(0, 8):
                rvp0.append(p0['d%i' % ctr2][ctr])
                rvp1.append(p1['d%i' % ctr2][ctr])
        return {'p0': AdcData(-1, rvp0),
                'p1': AdcData(-1, rvp1)}

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
