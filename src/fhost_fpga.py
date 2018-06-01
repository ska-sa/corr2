import time
import logging
import struct
import numpy

import casperfpga.memory as caspermem

import delay as delayops
from utils import parse_slx_params
from digitiser_receiver import DigitiserStreamReceiver
from casperfpga import CasperLogHandlers


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
    :return: Returns the scale factor used in the delay calculations 
            due to bitshifting (nominally 2**23).
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
                 host=None, offset=-1, **kwargs):
        """

        :param input_stream: the DigitiserStream input for this F-engine
        :param host: the Fpga host on which this input is received
        :param offset: which input on that host is this?
        :return:
        """
        # Just to make sure it doesn't break when logging
        try:
            # Get the counter corresponding to _create_hosts in fxcorrelator.py
            self.feng_id = kwargs['feng_id']
        except KeyError:
            # Couldn't find it in the list of params
            self.feng_id = 0
        try:
            descriptor = kwargs['descriptor']
        except KeyError:
            descriptor = 'InstrumentName'
        
        if host is None:
            logger_name = '{}_feng-{}-{}'.format(descriptor, str(self.feng_id), host)
        else:
            logger_name = '{}_feng-{}'.format(descriptor, str(self.feng_id))
        
        self.logger = logging.getLogger(logger_name)
        console_handler_name = '{}_console'.format(logger_name)
        if not CasperLogHandlers.configure_console_logging(self.logger, console_handler_name):
            errmsg = 'Unable to create ConsoleHandler for logger: {}'.format(logger_name)
            # How are we going to log it anyway!
            self.logger.error(errmsg)

        self.logger.setLevel(logging.INFO)
        debugmsg = 'Successfully created logger for {}'.format(logger_name)
        self.logger.debug(debugmsg)

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

    @property
    def input_number(self):
        return self.input.input_number

    @input_number.setter
    def input_number(self, value):
        raise NotImplementedError('This is not currently defined.')
    
    def log_an_error(self,value):
        self.logger.error("Error logged with value: {}".format(value))

    def delay_set(self, delay_obj):
        """
        Configures a given stream to a delay, defined by a delay.Delay object.
        Delay units should be samples, and phase is in fractions of pi radians.
        This function will also update this feng object's self.last_delay, but note that the units are different.
        :return: nothing!
        """

        # set up the delays
        act_delay = self._delay_write_delay(delay_obj.delay)
        act_delay_delta = self._delay_write_delay_rate(delay_obj.delay_delta)
        act_phase, act_phase_delta = self._delay_write_phase(delay_obj.phase_offset, delay_obj.phase_offset_delta)

        # arm the timed load latches
        cd_tl_name = 'tl_cd%i' % self.offset
        self._arm_timed_latch(cd_tl_name, mcnt=delay_obj.load_mcnt)

        # update the stored value
        self.last_delay = delayops.Delay(act_delay,act_delay_delta,act_phase,
                            act_phase_delta,load_mcnt=delay_obj.load_mcnt)
        self.last_delay.delay /= self.host.rx_data_sample_rate_hz
        self.last_delay.phase_offset *= numpy.pi
        self.last_delay.phase_offset_delta *= (numpy.pi * self.host.rx_data_sample_rate_hz)

    def _arm_timed_latch(self, name, mcnt=None):
        """
        Arms the delay correction timed latch. 
        Optimisations bypass normal register bitfield operations.
        :param names: name of latch to trigger
        :param mcnt: sample mcnt to trigger at. If None triggers immediately
        :return ::
        """
        control_reg = self.host.registers['%s_control' % name]
        control0_reg = self.host.registers['%s_control0' % name]
        ao=control0_reg._fields['arm'].offset
        if mcnt is None:
            lio=control0_reg._fields['load_immediate'].offset
            control0_reg.write_int((1<<ao)+(1<<lio))
            control0_reg.write_int(0)
        else:
            load_time_lsw = mcnt - (int(mcnt/(2**32)))*(2**32)
            load_time_msw = int(mcnt/(2**32))
            control_reg.write_int(load_time_lsw)
            control0_reg.write_int((1<<ao)+(load_time_msw))
            control0_reg.write_int((0<<ao)+(load_time_msw))

    def delay_get(self):
        """
        Store in local variables (and return) the values that were 
        written into the various FPGA load registers.
        :return:
        """
#TODO fix this function!        
#TODO: Only return useful values if they actually loaded!
        
        bitshift = delay_get_bitshift()
        delay_reg = self.host.registers['delay%i' % self.offset]
        delay_delta_reg = self.host.registers['delta_delay%i' % self.offset]
        phase_reg = self.host.registers['phase%i' % self.offset]
        act_delay = delay_reg.read()['data']['initial']
        act_delay_delta = delay_delta_reg.read()['data']['delta'] / bitshift
        act_phase_offset = phase_reg.read()['data']['initial']
        act_phase_offset_delta = phase_reg.read()['data']['delta'] / bitshift

    def _delay_write_delay(self, delay):
        """
        delay is in samples.
        """
        infostr = '%s:%i:' % (self.host.host, self.offset)
        bitshift = delay_get_bitshift()
        delay_reg = self.host.registers['delay%i' % self.offset]

        #figure out register offsets and widths
        reg_bp = delay_reg._fields['initial'].binary_pt
        reg_bw = delay_reg._fields['initial'].width_bits

        max_delay = 2 ** (reg_bw - reg_bp) - 1 / float(2 ** reg_bp)
        if delay < 0:
            self.logger.warn('%s smallest delay is 0. Requested %f samples.' % 
                (infostr,delay))
            delay = 0
        elif delay > max_delay:
            self.logger.warn('%s setting largest possible delay. Requested %f samples, set %f.' %
                (infostr, delay,max_delay))
            delay = max_delay
        
        #prepare the register:
        prep_int=int(delay*(2**reg_bp))&((2**reg_bw)-1)
        act_value = (float(prep_int)/(2**reg_bp))
        self.logger.debug('%s setting delay to %f samples.' % (infostr, act_value))
        delay_reg.write_int(prep_int)
        return act_value

    def _delay_write_delay_rate(self, delay_rate):
        """
        """
        infostr = '%s:%i:' % (self.host.host, self.offset)
        bitshift = delay_get_bitshift()
        delay_delta_reg = self.host.registers['delta_delay%i' % self.offset]
        # shift up by amount shifted down by on fpga
        delta_delay_shifted = float(delay_rate) * bitshift

        #figure out register offsets and widths
        reg_bp = delay_delta_reg._fields['delta'].binary_pt
        reg_bw = delay_delta_reg._fields['delta'].width_bits

        #figure out maximum range, and clip if necessary:
        max_positive_delta_delay = 2 ** (reg_bw - reg_bp - 1) - 1 / float(2 ** reg_bp)
        max_negative_delta_delay = -2 ** (reg_bw - reg_bp - 1) + 1 / float(2 ** reg_bp)
        if delta_delay_shifted > max_positive_delta_delay:
            delta_delay_shifted = max_positive_delta_delay
            self.logger.warn('%s setting largest possible positive delay delta. ' \
                             'Requested: %e samples/sample, set %e.'%
                             (infostr,delay_rate,max_positive_delta_delay/bitshift))
        elif delta_delay_shifted < max_negative_delta_delay:
            delta_delay_shifted = max_negative_delta_delay
            self.logger.warn('%s setting largest possible negative delay delta. ' \
                             'Requested: %e samples/sample, set %e.'%
                             (infostr,delay_rate,max_negative_delta_delay/bitshift))

        #figure out the actual (rounded) register values:
        prep_int=int(delta_delay_shifted*(2**reg_bp))&((2**reg_bw)-1)
        act_value = (float(prep_int)/(2**reg_bp))/bitshift
        if delta_delay_shifted<0: act_value-=(2**reg_bw)
        self.logger.debug('%s setting delay delta to %e samples/sample (reg 0x%08X).' %(infostr, act_value, prep_int))
        delay_delta_reg.write_int(prep_int)
        return act_value


    def _delay_write_phase(self, phase, phase_rate):
        """
        Phase is in fractions of pi radians (-1 to 1 corresponds to -180degrees to +180 degrees).
        Phase rate is in pi radians/sample. (eg value of 0.5 would increment phase by 0.5*pi radians every sample)
        :return:
        """
        infostr = '%s:%i:' % (self.host.host, self.offset)
        bitshift = delay_get_bitshift()
        phase_reg = self.host.registers['phase%i' % self.offset]

        #figure out register offsets and widths
        initial_reg_bp = phase_reg._fields['initial'].binary_pt
        initial_reg_bw = phase_reg._fields['initial'].width_bits
        initial_reg_offset = phase_reg._fields['initial'].offset
        delta_reg_bp = phase_reg._fields['delta'].binary_pt
        delta_reg_bw = phase_reg._fields['delta'].width_bits
        delta_reg_offset = phase_reg._fields['delta'].offset

        # setup the phase offset
        max_positive_phase = 2 ** (initial_reg_bw - initial_reg_bp - 1) - 1 / float(2 ** initial_reg_bp)
        max_negative_phase = -2 ** (initial_reg_bw - initial_reg_bp - 1) + 1 / float(2 ** initial_reg_bp)
        if phase > max_positive_phase:
            self.logger.warn('%s setting largest possible positive phase. '
                        'Requested: %e*pi radians, set %e.' % 
                        (infostr, phase, max_positive_phase))
            phase = max_positive_phase
        elif phase < max_negative_phase:
            self.logger.warn('%s setting largest possible negative phase. '
                        'Requested: %e*pi radians, set %e.' % 
                        (infostr, phase, max_negative_phase))
            phase = max_negative_phase

        #setup phase delta/rate:
        # shift up by amount shifted down by on fpga
        max_positive_delta_phase = 2 ** (delta_reg_bw - delta_reg_bp - 1) - 1 / float(2 ** delta_reg_bp)
        max_negative_delta_phase = -2 ** (delta_reg_bw - delta_reg_bp - 1) + 1 / float(2 ** delta_reg_bp)
        delta_phase_shifted = float(phase_rate) * bitshift
        if delta_phase_shifted > max_positive_delta_phase:
            dp = max_positive_delta_phase / bitshift
            self.logger.warn('%s setting largest possible positive phase delta. '
                        'Requested %e*pi radians/sample, set %e.' % (infostr, phase_rate, dp))
            delta_phase_shifted = max_positive_delta_phase
        elif delta_phase_shifted < max_negative_delta_phase:
            dp = max_negative_delta_phase / bitshift
            self.logger.warn('%s setting largest possible negative phase delta. '
                        'Requested %e*pi radians/sample, set %e.' % (infostr, phase_rate, dp))
            delta_phase_shifted = max_negative_delta_phase

        prep_int_initial=int(phase*(2**initial_reg_bp))&((2**initial_reg_bw)-1)
        prep_int_delta=int(delta_phase_shifted*(2**delta_reg_bp))&((2**delta_reg_bw)-1)

        act_value_initial = (float(prep_int_initial)/(2**initial_reg_bp))
        if phase<0: act_value_initial-=(2**initial_reg_bw)
        act_value_delta = (float(prep_int_delta)/(2**delta_reg_bp))/bitshift
        if delta_phase_shifted<0: act_value_delta-=(2**delta_reg_bw)
        self.logger.debug('%s writing initial phase to %e*pi radians.' % (infostr, act_value_initial))
        self.logger.debug('%s writing %e*pi radians/sample phase delta.' % (infostr, act_value_delta))

        # actually write the values to the register
        prep_int = (prep_int_initial<<initial_reg_offset) + (prep_int_delta<<delta_reg_offset)
        phase_reg.write_int(prep_int)
        return act_value_initial,act_value_delta

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
                 connect=True, config=None, **kwargs):
        super(FpgaFHost, self).__init__(host=host, katcp_port=katcp_port,
                                        bitstream=bitstream, connect=connect)

        self._config = config

        try:
            # Get the counter corresponding to _create_hosts in fxcorrelator.py
            self.fhost_index = kwargs['host_id']
        except KeyError:
            # Couldn't find it in the list of params
            self.fhost_index = 0
        try:
            descriptor = kwargs['descriptor']
        except KeyError:
            descriptor = 'InstrumentName'
        
        logger_name = '{}_fhost-{}-{}'.format(descriptor, str(self.fhost_index), host)
        self.logger = logging.getLogger(logger_name)
        console_handler_name = '{}_console'.format(logger_name)
        self.logger, result = CasperLogHandlers.configure_console_logging(self.logger, console_handler_name)
        if not result:
            errmsg = 'Unable to create ConsoleHandler for logger: {}'.format(descriptor)
            # How are we going to log it anyway!
            self.logger.error(errmsg)

        self.logger.setLevel(logging.ERROR)
        debugmsg = 'Successfully created logger for {}'.format(logger_name)
        self.logger.debug(debugmsg)

        # list of Fengines received by this F-engine host
        self.fengines = []

        if config is not None:
            self.num_fengines = int(config['f_per_fpga'])
            self.fft_shift = int(config['fft_shift'])
            self.n_chans = int(config['n_chans'])
            self.min_load_time = float(config['min_load_time'])
        else:
            self.num_fengines = None
            self.fft_shift = None
            self.n_chans = None
            self.min_load_time = None

        self.rx_data_sample_rate_hz = -1

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source, **kwargs):
        bitstream = config_source['bitstream']
        return cls(hostname, katcp_port, bitstream=bitstream,
                   connect=True, config=config_source, **kwargs)

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
            self.logger.debug('%s: writing EQ %s' % (self.host, feng.name))
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
        self.logger.debug('%s: wrote EQ to sbram %s' % (self.host, eq_bram))
        return len(ss)


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

    def tx_disable(self):
        self.registers.control.write(gbe_txen=False)

    def tx_enable(self):
        self.registers.control.write(gbe_txen=True)

    def get_cd_status(self):
        """
        Retrieves all the Coarse Delay status registers.
        """
        rv={}
        for i in range(6):
            rv.update(self.registers['cd_hmc_hmc_delay_status%i'%i].read()['data'])
        return rv

    def get_ct_status(self):
        """
        Retrieve all the Corner-Turner registers.
        returns a list (one per pol on board) of status dictionaries.
        """ 
        rv={}
        for i in range(5):
            rv.update(self.registers['hmc_ct_status%i' %i].read()['data'])
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
            self.logger.info("Triggering ADC snapshot at %i"%loadcnt)
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
        self.logger.info(logstr)

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
            log_runtime_error(self.logger, "Something's wrong. I have %i eq coefficients when I should have %i."  % (len(eq_coeffs), n_coeffs))
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
            self.logger.warn("You specified %i EQ coefficients but your system only supports %i actual values. Only writing every %ith value." % (n_chans ,n_coeffs, decimation))
        elif len(init_coeffs) > 0:
            log_runtime_error(self.logger, 'You specified %i coefficients, but there are %i EQ coefficients required for this engine' % (len(init_coeffs), n_coeffs))
        else:
            coeffs = numpy.polyval(init_poly, range(n_chans))[decimation/2::decimation]
            coeffs = numpy.array(coeffs, dtype=complex)

        n_bytes = self.config['equalisation']['n_bytes_coeffs']
        bin_pt = self.config['equalisation']['bin_pt_coeffs']

        coeffs_str = self.float2str(coeffs, n_bytes*8, bin_pt)

        # finally write to the bram
        self.host.write(reg_name, coeffs_str)

'''
