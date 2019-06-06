import time
from logging import INFO
import struct

import casperfpga.memory as caspermem
from casperfpga.transport_skarab import SkarabTransport

import delay as delayops
from utils import parse_slx_params
from host_fpga import FpgaHost
# from corr2LogHandlers import getLogger

#TODO: move snapshots from fhost obj to feng obj?
#   -> not sensible while trig_time registers are shared for adc snapshots.


class InputStreamDetails():
    def __init__(self,name,destination,input_number):
        self.name=name;
        self.input_number = input_number;
        self.destination = destination;

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


def delay_get_bitshift(bitshift_schedule=23):
    """
    :return: Returns the scale factor used in the delay calculations
            due to bitshifting (nominally 2**23).
    """
    # TODO should this be in config file?
    bitshift = (2**bitshift_schedule)
    return bitshift


class Fengine(object):
    """
    An F-engine, acting on a source DataStream
    """
    def __init__(self, input_stream, host=None,
                 offset=-1, *args, **kwargs):
        """

        :param input_stream: an InputStreamDetails object with the details to the input for this F-engine
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

        # This will always be a kwarg
        self.getLogger = kwargs['getLogger']

        logger_name = '{}_feng{}-{}'.format(descriptor, str(self.feng_id), input_stream.name)
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)
        result, self.logger = self.getLogger(logger_name=logger_name,
                                             log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        debugmsg = 'Successfully created logger for {}'.format(logger_name)
        self.logger.debug(debugmsg)

        self.input = input_stream
        self.host = host
        self.offset = offset
        self.eq_bram_name = 'eq%i' % offset
        self.last_delay = delayops.Delay()
        self.last_eq = None

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

    def get_quant_snapshot(self, channel_select=-1):
        """
        Read the post-quantisation snapshot for this fengine.
        snapshot data.
        :param channel_select: If a value is passed here, a time-series of a single channel is returned, if not, a spectrum is returned.
        :return: a numpy array of complex values
        """
        import numpy
        if channel_select != -1:
            if channel_select < 0 or channel_select >= self.host.n_chans:
                raise ValueError("channel_select should be between 0 and {}, but received {}!".format(self.host.n_chans, channel_select))
            chan_group = int(channel_select) / 4
            which_chan = int(channel_select) % 4
            self.host.registers.quant_snap_ctrl.write(single_channel=True, channel_select=chan_group)
            snapshot = self.host.snapshots['snap_quant%i_ss' % self.offset]
            sdata = snapshot.read()['data']
            compl = numpy.vectorize(complex)(sdata['real{}'.format(which_chan)], sdata['imag{}'.format(which_chan)])
            return compl
        else:
            snapshot = self.host.snapshots['snap_quant%i_ss'%self.offset]
            #calculate number of snapshot reads required:
            n_reads=float(self.host.n_chans)/(2**int(snapshot.block_info['snap_nsamples']))/4
            compl = []
            for read_n in range(int(numpy.ceil(n_reads))):
                offset = read_n * (2**int(snapshot.block_info['snap_nsamples']))
                sdata = snapshot.read(offset=offset)['data']
                for ctr in range(0, len(sdata['real0'])):
                    compl.append(complex(sdata['real0'][ctr], sdata['imag0'][ctr]))
                    compl.append(complex(sdata['real1'][ctr], sdata['imag1'][ctr]))
                    compl.append(complex(sdata['real2'][ctr], sdata['imag2'][ctr]))
                    compl.append(complex(sdata['real3'][ctr], sdata['imag3'][ctr]))
            return compl[0:self.host.n_chans]

    def delay_set(self, delay_obj):
        """
        Configures a given stream to a delay, defined by a delay.Delay object.
        Delay units should be samples, and phase is in fractions of pi radians.
        This function will also update this feng object's self.last_delay.
        :return: nothing!
        """
        self.logger.debug("Processing request for delay model: {}.".format(delay_obj.__str__()))
        rv=True
        self.last_delay.last_load_success=False
        # set up the delays and update the stored values
        self.last_delay.delay = self._delay_write_delay(delay_obj.delay)
        self.last_delay.delay_delta = self._delay_write_delay_rate(delay_obj.delay_delta)
        self.last_delay.phase_offset, self.last_delay.phase_offset_delta = self._delay_write_phase(delay_obj.phase_offset, delay_obj.phase_offset_delta)

        # arm the timed load latches
        cd_tl_name = 'tl_cd%i' % self.offset
        status=self.host.registers['%s_status'%cd_tl_name].read()['data']
        load_count=status['load_count']
        arm_count=status['arm_count']
        if load_count != self.last_delay.load_count:
            self.last_delay.last_load_success=True
            self.logger.debug("Last delay successfully loaded at mcnt %i"%self.last_delay.load_mcnt)
        else:
            self.logger.error('Failed to load last delay model;' \
                ' arm_cnt before: %i, after: %i.' \
                ' load_cnt before: %i, after: %i.' \
                ' Last requested load mcnt %i, time now %f.'%(
                self.last_delay.arm_count,arm_count,
                self.last_delay.load_count,load_count,
                self.last_delay.load_mcnt,time.time()))
            self.last_delay.last_load_success=False
        self.last_delay.load_count = load_count
        self.last_delay.arm_count = arm_count
        self.last_delay.load_mcnt=self._arm_timed_latch(cd_tl_name, mcnt=delay_obj.load_mcnt)
        self.logger.debug("New delay model applied: {}".format(self.last_delay.__str__()))
        return self.last_delay.last_load_success

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
        #if mcnt is None:
        #    self.logger.info('Loadtime not specified; loading immediately.')
        #    lio=control0_reg._fields['load_immediate'].offset
        #    control0_reg.write_int((1<<ao)+(1<<lio))
        #    control0_reg.write_int(0)
        #    return -1
        #else:
        self.logger.debug('Requested load mcnt %i.'%mcnt)
        load_time_lsw = mcnt - (int(mcnt/(2**32)))*(2**32)
        load_time_msw = int(mcnt/(2**32))
        control_reg.write_int(load_time_lsw)
        control0_reg.write_int((1<<ao)+(load_time_msw))
        control0_reg.write_int((0<<ao)+(load_time_msw))
        return mcnt

##TODO reimplement this function.
## Won't do for now; doesn't seem like anyone needs it. CAM/SDP use the sensors instead.
##TODO: Only return useful values if they actually loaded?
#    def delay_get(self):
#        """
#        Store in local variables (and return) the values that were
#        written into the various FPGA load registers.
#        :return:
#        """
#
#        bitshift = delay_get_bitshift()
#        delay_reg = self.host.registers['delay%i' % self.offset]
#        delay_delta_reg = self.host.registers['delta_delay%i' % self.offset]
#        phase_reg = self.host.registers['phase%i' % self.offset]
#        act_delay = delay_reg.read()['data']['initial']
#        act_delay_delta = delay_delta_reg.read()['data']['delta'] / bitshift
#        act_phase_offset = phase_reg.read()['data']['initial']
#        act_phase_offset_delta = phase_reg.read()['data']['delta'] / bitshift
#
    def _delay_write_delay(self, delay):
        """
        delay is in samples. Can be fractional.
        """
        
        """
        Split out whole and fractional part
        """
        
        print 'Running delay_write'
        delay_whole = int(delay)
        delay_frac = delay - int(delay)
        
        delay_reg_whole = self.host.registers['delay_whole%i' % self.offset]
        delay_reg_frac = self.host.registers['delay_frac%i' % self.offset]

        #figure out register offsets and widths
        reg_bp = delay_reg_frac._fields['initial'].binary_pt + 1
        reg_bw = delay_reg_whole._fields['initial'].width_bits + reg_bp

        max_delay = 2 ** (reg_bw - reg_bp) - 1 / float(2 ** reg_bp)
        if delay < 0:
            self.logger.warn('Setting smallest delay of 0. Requested %f samples(whole) and %f samples(frac).' %
                (delay_whole,delay_frac))
            delay_whole = 0
            delay_frac = 0
        elif delay > max_delay:
            self.logger.warn('Setting largest possible delay. Requested %f samples, set delay_whole %f and delay_frac %f.' %
                (delay_whole,max_delay,delay_frac))
            delay_whole = max_delay
            delay_frac = 0;

        #prepare the register:
        #prep_int=int(delay*(2**reg_bp))&((2**reg_bw)-1)

        prep_int_frac=int(delay_frac*(2**(reg_bw-reg_bp-1)))&(2**(reg_bp-1)-1)
        act_value_frac = (float(prep_int_frac)/(2**(reg_bw-reg_bp-1)))
        
        prep_int_whole=int(delay_whole)&((2**(reg_bw-reg_bp))-1)
        act_value_whole = float(prep_int_whole)        
        self.logger.debug('Setting delay_whole to %f samples, from request for %f samples.' % (act_value_whole,delay_whole))
        self.logger.debug('Setting delay_frac to %f samples, from request for %f samples.' % (act_value_frac,delay_frac))
        
        delay_reg_whole.write_int(prep_int_whole)
        delay_reg_frac.write_int(prep_int_frac)
        
        act_value = act_value_whole + act_value_frac

        return act_value

    def _delay_write_delay_rate(self, delay_rate):
        """
        Split out whole and fractional part
        """
        delay_rate_whole = int(delay_rate)
        delay_rate_frac = delay_rate - int(delay_rate)
        
        bitshift = delay_get_bitshift(bitshift_schedule=23)
        delay_delta_reg_whole = self.host.registers['delta_delay_whole%i' % self.offset]
        delay_delta_reg_frac = self.host.registers['delta_delay_frac%i' % self.offset]
        
        # shift up by amount shifted down by on fpga
        # Use input value
        delta_delay_shifted = float(delay_rate) * bitshift
        #delta_delay_shifted_whole = float(delay_rate_whole) * bitshift
        #delta_delay_shifted_frac = float(delay_rate_frac) * bitshift
        delta_delay_shifted_whole = float(delay_rate_whole)
        delta_delay_shifted_frac = float(delay_rate_frac)
        
       
        #figure out register offsets and widths
        reg_bp = delay_delta_reg_frac._fields['initial'].binary_pt + 1

        reg_bw = delay_delta_reg_whole._fields['initial'].width_bits + reg_bp


        #figure out maximum range, and clip if necessary:
        max_positive_delta_delay = 2 ** (reg_bw - reg_bp) - 1 / float(2 ** reg_bp)
        max_negative_delta_delay = -2 ** (reg_bw - reg_bp) + 1 / float(2 ** reg_bp)
        if delta_delay_shifted > max_positive_delta_delay:
            delta_delay_shifted = max_positive_delta_delay
            self.logger.warn('Setting largest possible positive delay delta. ' \
                             'Requested: %e samples/sample, set %e.'%
                             (delay_rate,max_positive_delta_delay/bitshift))
        elif delta_delay_shifted < max_negative_delta_delay:
            delta_delay_shifted = max_negative_delta_delay
            self.logger.warn('Setting largest possible negative delay delta. ' \
                             'Requested: %e samples/sample, set %e.'%
                             (delay_rate,max_negative_delta_delay/bitshift))

        
   
        #prep_int=int(delta_delay_shifted*(2**reg_bp))
        #act_value = (float(prep_int)/(2**reg_bp))/bitshift
                
        prep_int_whole=int(delta_delay_shifted_whole*(2**reg_bp))
        act_value_whole = (float(prep_int_whole)/(2**reg_bp))
        
        prep_int_frac=int(delta_delay_shifted_frac*(2**(reg_bp-1)))&(2**(reg_bp)-1)
        act_value_frac = (float(prep_int_frac)/(2**(reg_bp-1)))
        
        self.logger.debug('Setting delay delta whole to %e samples/sample (reg 0x%08X), mapped from %e samples/sample request.' %(act_value_whole, prep_int_whole,delay_rate_whole))
        self.logger.debug('Setting delay delta frac to %e samples/sample (reg 0x%08X), mapped from %e samples/sample request.' %(act_value_frac, prep_int_frac,delay_rate_frac))
        
        delay_delta_reg_whole.write_int(prep_int_whole)
        delay_delta_reg_frac.write_int(prep_int_frac)
                
        act_value = act_value_whole + act_value_frac
        
        return act_value


    def _delay_write_phase(self, phase, phase_rate):
        """
        Phase is in fractions of pi radians (-1 to 1 corresponds to -180degrees to +180 degrees).
        Phase rate is in pi radians/sample. (eg value of 0.5 would increment phase by 0.5*pi radians every sample)
        :return:
        """
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
            self.logger.warn('Setting largest possible positive phase. '
                        'Requested: %e*pi radians, set %e.' %
                        (phase, max_positive_phase))
            phase = max_positive_phase
        elif phase < max_negative_phase:
            self.logger.warn('Setting largest possible negative phase. '
                        'Requested: %e*pi radians, set %e.' %
                        (phase, max_negative_phase))
            phase = max_negative_phase

        #setup phase delta/rate:
        # shift up by amount shifted down by on fpga
        max_positive_delta_phase = 2 ** (delta_reg_bw - delta_reg_bp - 1) - 1 / float(2 ** delta_reg_bp)
        max_negative_delta_phase = -2 ** (delta_reg_bw - delta_reg_bp - 1) + 1 / float(2 ** delta_reg_bp)
        delta_phase_shifted = float(phase_rate) * bitshift
        if delta_phase_shifted > max_positive_delta_phase:
            dp = max_positive_delta_phase / bitshift
            self.logger.warn('Setting largest possible positive phase delta. '
                        'Requested %e*pi radians/sample, set %e.' % (phase_rate, dp))
            delta_phase_shifted = max_positive_delta_phase
        elif delta_phase_shifted < max_negative_delta_phase:
            dp = max_negative_delta_phase / bitshift
            self.logger.warn('Setting largest possible negative phase delta. '
                        'Requested %e*pi radians/sample, set %e.' % (phase_rate, dp))
            delta_phase_shifted = max_negative_delta_phase

        prep_int_initial=int(phase*(2**initial_reg_bp))
        prep_int_delta=int(delta_phase_shifted*(2**delta_reg_bp))

        act_value_initial = (float(prep_int_initial)/(2**initial_reg_bp))
        #if phase<0: act_value_initial-=(2**initial_reg_bw)  # Seems to me as though this shouldn't be here. (JS)
        act_value_delta = (float(prep_int_delta)/(2**delta_reg_bp))/bitshift
        self.logger.debug('Writing initial phase to %e*pi radians (reg: %i), mapped from %e request.' % (act_value_initial,prep_int_initial,phase))
        self.logger.debug('Writing %e*pi radians/sample phase delta (reg: %i), mapped from %e*pi request.' % (act_value_delta,prep_int_delta,phase_rate))
        
        import numpy
        prep_array = numpy.array([prep_int_initial, prep_int_delta], dtype=numpy.int16)
        prep_array = prep_array.view(dtype=numpy.uint16)
        # actually write the values to the register
        prep_int = (prep_array[0]<<initial_reg_offset) + (prep_array[1]<<delta_reg_offset)
        phase_reg.write_int(prep_int)

        return act_value_initial,act_value_delta

    def eq_get(self):
        """
        Read a given EQ BRAM.
        :return: a list of the complex EQ values from RAM
        """
        # eq vals are packed as 32-bit complex (16 real, 16 imag)
        eqvals = self.host.read(self.eq_bram_name, self.host.n_chans*4)
        eqvals = struct.unpack('>%ih' % (self.host.n_chans*2), eqvals)
        eqcomplex = []
        for ctr in range(0, len(eqvals), 2):
            eqcomplex.append(eqvals[ctr] + (1j * eqvals[ctr+1]))
        self.last_eq=eqcomplex
        return self.last_eq

    def eq_set(self, eq_poly=None):
        """
        Write a given complex eq to the given SBRAM.
        WARN: hardcoded for 16b values!

        :param eq_poly: a list of polynomial coefficients, or list of float values (must be n_chans long) to write to bram. Set to string 'auto' to have system attempt to automatically set gains (requires sane values to have been set beforehand!).
        :return:
        """
        coeffs = (self.host.n_chans * 2) * [0]
        if eq_poly==None:
            self.logger.info('Setting default eq')
            eq_poly=int(self.host._config['default_eq_poly'])
        try:
            if eq_poly == 'auto':
                import numpy
                target_output=0.1 #this is the goal for numpy.abs(complex_snapshot). For 8.7bit meerkat, total range is thus sqrt((abs(1+1j)))=1.4
                n_averages=30

                #get an estimate of the current spectrum:
                chans = range(self.host.n_chans)
                quant_snapshot = numpy.abs(self.get_quant_snapshot())
                for i in range(n_averages):
                    quant_snapshot += numpy.abs(self.get_quant_snapshot())
                quant_snapshot /= n_averages

                error=target_output/quant_snapshot

                #ignore band edges; only use central 80%:
                start_chan=int(self.host.n_chans*0.1)
                stop_chan=int(self.host.n_chans*0.9)
                eq_poly=numpy.polyfit(chans[start_chan:stop_chan],error[start_chan:stop_chan],3)
                poly_coeffs=numpy.array(self.eq_get())*numpy.polyval(eq_poly,chans)
                coeffs[0::2] = [coeff.real for coeff in poly_coeffs]
                coeffs[1::2] = [coeff.imag for coeff in poly_coeffs]
                
            elif len(eq_poly) == self.host.n_chans:
                # list - one for each channel
                coeffs[0::2] = [coeff.real for coeff in eq_poly]
                coeffs[1::2] = [coeff.imag for coeff in eq_poly]
            elif len(eq_poly)<self.host.n_chans:
                # polynomial
                import numpy
                poly_coeffs=numpy.polyval(eq_poly, range(self.host.n_chans))
                coeffs[0::2] = [coeff.real for coeff in poly_coeffs]
                coeffs[1::2] = [coeff.imag for coeff in poly_coeffs]
        except TypeError:
                #single value?
                coeffs = (self.host.n_chans * 2) * [0]
                coeffs[0::2] = [eq_poly.real for coeff in range(self.host.n_chans)]
                coeffs[1::2] = [eq_poly.imag for coeff in range(self.host.n_chans)]

        #Ensure coeffs values can be stored in 16 bits
        saturated_channels_count=0
        for i in range(len(coeffs)):
            if(coeffs[i] > 32767):
                coeffs[i]=32767
                saturated_channels_count+=1
            elif(coeffs[i] < -32767):
                coeffs[i] =-32767
                saturated_channels_count+=1

        creal = coeffs[0::2]
        cimag = coeffs[1::2]
        ss = struct.pack('>%ih' % (self.host.n_chans * 2), *coeffs)
        self.host.write(self.eq_bram_name, ss, 0)
        self.last_eq=[complex(creal[i],cimag[i]) for i in range(len(creal))]
        if(saturated_channels_count != 0):
            self.logger.warn('EQ values adjusted. %i channels saturated.'%saturated_channels_count)
        self.logger.info('EQ values: %s...'%self.last_eq[0:10])

        return self.last_eq

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return "%s: Fengine %i, on %s:%i, processing %s." % (
            self.name, self.input_number, self.host, self.offset,self.input)


class FpgaFHost(FpgaHost):
    """
    A Host, that hosts Fengines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, bitstream=None,
                 connect=True, config=None, **kwargs):
        super(FpgaFHost, self).__init__(host=host, katcp_port=katcp_port,
                                        bitstream=bitstream,
                                        transport=SkarabTransport,
                                        connect=connect)

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

        # This will always be a kwarg
        self.getLogger = kwargs['getLogger']

        logger_name = '{}_fhost-{}-{}'.format(descriptor, str(self.fhost_index), host)
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)
        result, self.logger = self.getLogger(logger_name=logger_name,
                                             log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        debugmsg = 'Successfully created logger for {}'.format(logger_name)
        self.logger.debug(debugmsg)

        # list of Fengines received by this F-engine host
        self.fengines = []

        if config is not None:
            self.num_fengines = int(config['f_per_fpga'])
            self.n_chans = int(config['n_chans'])
            self.min_load_time = float(config['min_load_time'])
        else:
            self.num_fengines = None
            self.n_chans = None
            self.min_load_time = None

        self.rx_data_sample_rate_hz = -1

        self.host_type = 'fhost'

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

    def clear_status(self):
        """
        Clear the status registers and counters on this host
        :return:
        """
        self.registers.control.write(status_clr='pulse', gbe_cnt_rst='pulse',
                                     cnt_rst='pulse')
        # self.registers.control.write(gbe_cnt_rst='pulse')
        self.logger.debug('{}: status cleared.'.format(self.host))

    def get_pipeline_latency(self):
        """
        Get the difference in timestamps from the output to the input of the pipeline.
        """
        return self.registers.time_difference.read()['data']['time_difference']

    def set_max_pipeline_latency(self,max_latency,autoresync=True):
        """
        Set the maximum difference (in ADC samples) allowed from the input to the
        output of the DSP pipeline before the hardware will automatically issue a reset.
        Optionally enable the automatic hardware check (and reset).
        This catches some HMC errors (where it doesn't return data for all read requests).
        """
        self.registers.time_check.write(max_difference=max_latency)
        if autoresync:
            self.registers.control.write(time_diff_check_en=True)
        return


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


    def set_fft_shift(self, shift_schedule=None):
        """
        Set the FFT shift schedule.
        :param shift_schedule: int representing bit mask. '1' represents a
        shift for that stage. First stage is MSb.
        Alternatively, specify the number of stages (as eg '5s')  you'd
        like to shift on, and these will be distributed evenly for you.
        Use config file default if None provided.
        Determine fft shift automatically if 'auto' is provided.
        :return: <nothing>
        """
        import numpy
        n_stages_total = int(numpy.log2(self.n_chans)+1)
        def distribute_shifts(n_stages_total,n_stages_shift):
            if n_stages_shift<=0:
                return 0
            elif n_stages_shift>=n_stages_total:
                return (2**(n_stages_total))-1
            else:
                new_shift_schedule=0
                shift_stages=n_stages_total-1-numpy.uint(numpy.linspace(0,n_stages_total,n_stages_shift,endpoint=False))
                for shift_stage in shift_stages:
                    self.logger.debug("FFT shifting stage %i"%(shift_stage))
                    new_shift_schedule+=(1<<int(shift_stage))
                return new_shift_schedule

        def test_shift_schedule(n_retries=5,wait_time=0.5):
            status_first=self.get_pfb_status()
            for test in range(n_retries):
                status=self.get_pfb_status()
                for pol in range(self.num_fengines):
                    if status['pol%i_or_err_cnt'%pol] != status_first['pol%i_or_err_cnt'%pol]:
                        self.logger.debug('FFT Shift auto-adjust: polarisation %i is overflowing!')
                        return False
                time.sleep(wait_time)
            return True

        def calc_n_stages(shift_schedule):
            rv=0
            for stage in range(n_stages_total):
                rv+=((shift_schedule>>stage)&1)
            return rv
        
        if (shift_schedule is None):
            shift_schedule = int(self._config['fft_shift'])
        elif (type(shift_schedule)==str): 
            if shift_schedule == 'auto':
                shift_ok=[]
                for shift_stages in range(n_stages_total+1):
                    fft_shift=distribute_shifts(n_stages_total,shift_stages)
                    self.registers.fft_shift.write(fft_shift=fft_shift)
                    shift_ok.append(test_shift_schedule())
                try:
                    shift_stages=min(n_stages_total,shift_ok.index(True)+3)
                    shift_schedule=distribute_shifts(n_stages_total,shift_stages)
                    self.logger.info("FFT shift auto-adj selected %i stages of shift from results: %s"%(shift_stages,str(shift_ok)))
                except ValueError:
                    self.logger.error("FFT shift auto-adj was unable to find a valid shift from results: %s. Shifting on every stage."%(str(shift_ok)))
                    shift_schedule=(2**(n_stages_total))-1
            elif (shift_schedule[-1]=='s'):
                n_stages=int(shift_schedule[0:-1])
                if n_stages <= n_stages_total:
                    shift_schedule=distribute_shifts(n_stages_total,n_stages)
                else:
                    self.logger.error("Can't shift on %i stages because there are only %i stages in this design! Shifting on every stage."%(n_stages,n_stages_total))
                    shift_schedule=(2**(n_stages_total))-1
        self.logger.info("Setting FFT shift to %i (%i stages)."%(shift_schedule,calc_n_stages(shift_schedule)))
        self.registers.fft_shift.write(fft_shift=shift_schedule)

    def get_fft_shift(self):
        """
        Get the current FFT shift schedule from the FPGA.
        :return: integer representing the FFT shift schedule for all the FFTs
        on this engine.
        """
        return self.registers.fft_shift.read()['data']['fft_shift']

    def get_quant_snapshots(self, channel_select=-1):
        """
        Get the quant snapshots for all the inputs on this host.
        :return:
        """
        return {
            feng.name: feng.get_quant_snapshot(channel_select=channel_select)
            for feng in self.fengines
        }

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

    def get_pfb_status(self):
        """
        Returns the pfb counters on f-eng
        :return: dict
        """
        import numpy
        rv=self.registers.pfb_status.read()['data']
        names=self.registers.pfb_pwr0.block_info['names']
        scale_factor=int(names[5:])
        rv['pol0_pfb_out_dBFS']=10*numpy.log10(self.registers.pfb_pwr0.read()['data'][names]/scale_factor)
        rv['pol1_pfb_out_dBFS']=10*numpy.log10(self.registers.pfb_pwr1.read()['data'][names]/scale_factor)
        return rv

    def get_quant_status(self):
        """
        Returns the EQ/quantiser counters on f-eng
        :return: dict
        """
        import numpy
        rv={}
        rv['p0_quant_out_dBFS']=10*numpy.log10(self.registers.quant_pwr0.read()['data']['reg'])
        rv['p1_quant_out_dBFS']=10*numpy.log10(self.registers.quant_pwr1.read()['data']['reg'])
        return rv

    def get_adc_status(self):
        """Return the ADC power levels in dBFS for all polarisations on this host.
        :return: dict
        """
        import numpy
        ret={}
        for feng in self.fengines:
            raw=self.registers['adc_dev%i'%feng.offset].read()['data']
            ret['p%i_min'%feng.offset]=raw['min']
            ret['p%i_max'%feng.offset]=raw['max']
            ret['p%i_pwr_dBFS'%feng.offset]=10*numpy.log10(self.registers['adc_pwr%i'%feng.offset].read()['data']['reg'])
            ret['p%i_dig_clip_cnt'%feng.offset]=self.registers['unpack_adc_clip%i'%feng.offset].read()['data']['sample_cnt']
        return ret

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

    def get_sync_status(self):
        """
        Read the synchronisation counters
        :return:
        """
        rv={}
        if 'sync_status' in self.registers.names():
            rv.update(self.registers.sync_status.read()['data'])
        if 'sync_status0' in self.registers.names():
            rv.update(self.registers.sync_status0.read()['data'])
        if 'sync_status1' in self.registers.names():
            rv.update(self.registers.sync_status1.read()['data'])
        if 'sync_status2' in self.registers.names():
            rv.update(self.registers.sync_status2.read()['data'])
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

    def subscribe_to_multicast(self):
        """
        Subscribe a skarab to its multicast input addresses.
        Assumes first 40G interface on SKARAB.
        :return:
        """
        gbe0_name = self.gbes.names()[0]
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
        self.logger.info('Subscribing %s to (%s+%i)' % (gbe.name, ip_str, ip_range - 1))
        gbe.multicast_receive(ip_str, ip_range-1)
