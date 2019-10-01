import Queue
import threading
import time
import re

import utils
import fhost_fpga
import fxcorrelator_speadops as speadops
import delay as delayops

from casperfpga import utils as fpgautils
from casperfpga import CasperLogHandlers

from data_stream import SPEADStream
from data_stream import FENGINE_CHANNELISED_DATA
from data_stream import StreamAddress

from logging import INFO


THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function
CHECK_TARGET_FUNC = fpgautils._check_target_func


class FengineStream(SPEADStream):
    """
    An f-engine SPEAD stream
    """

    def __init__(self, name, destination, fops, max_pkt_size, timeout=5, *args, **kwargs):
        """
        Make a SPEAD stream.
        :param name: the name of the stream
        :param destination: where is it going?
        :return:
        """
        self.fops = fops
        self.timeout = timeout
        super(FengineStream, self).__init__(
            name, FENGINE_CHANNELISED_DATA, destination, max_pkt_size=max_pkt_size,
            instrument_descriptor=self.fops.corr.descriptor, **kwargs)

    def descriptors_setup(self):
        """
        Set up the data descriptors for an F-engine stream.
        :return:
        """
        speadops.item_0x1600(self.descr_ig)

    def write_destination(self):
        """
        Write the destination to the hardware.
        :return:
        """
        txip = int(self.destination.ip_address)
        try:
            THREADED_FPGA_OP(self.fops.hosts, timeout=self.timeout,
                target_function=(lambda fpga_: fpga_.registers.iptx_base.write_int(txip),))
        except AttributeError:
            errmsg = 'Writing stream {} destination to hardware failed!'.format(self.name)
            self.fops.logger.error(errmsg)
            raise RuntimeError(errmsg)

    def tx_enable(self, n_retries=5):
        """
        Enable TX for this data stream
        :return:
        """
        self.descriptors_issue()
        if self.tx_enabled:
            self.fops.logger.warn(
                '{}: F-engine stream already running. Ignoring tx_enable command.'.format(self.name))
        else:
            self._tx_enable(n_retries)

    def _tx_enable(self, n_retries=5):
        """
        Enable TX for this data stream
        """
        done = False
        while n_retries > 0:
            try:
                THREADED_FPGA_OP(self.fops.hosts, timeout=self.timeout,
                    target_function=(lambda fpga_: fpga_.tx_enable(),))
                n_retries = -1
            except RuntimeError:
                n_retries -= 1
                self.fops.logger.warning(
                    'Failed to start F-engine output; {} retries remaining.'.format(n_retries))
                time.sleep(2)
        # if zero, then we tried n_retries times and failed. If less than zero,
        # we succeeded.
        if n_retries < 0:
            self.tx_enabled = True
            self.fops.logger.info('F-engine output enabled')
        else:
            self.fops.logger.error('Failed to start F-engine output.')

    def tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        self.fops.logger.warn(
            '{}: stopping F-engine streams will break the correlator. Ignoring.'.format(self.name))

    def _tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        THREADED_FPGA_OP(self.fops.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.tx_disable(), ))
        self.fops.logger.info('F-engine output disabled')
        self.tx_enabled = False

    def __str__(self):
        return 'FengineStream {} -> {}'.format(self.name, self.destination)


class FEngineOperations(object):

    def __init__(self, corr_obj, timeout=5, **kwargs):
        """
        A collection of F-engine operations that act on/with a
        correlator instance.
        :param corr_obj:
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.fhosts
        self.timeout = timeout
        self.fengines = []
        self.data_stream = None

        # Now creating separate instances of loggers as needed
        logger_name = '{}_FEngOps'.format(corr_obj.descriptor)
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)

        # All 'Instrument-level' objects will log at level INFO
        # - corr_obj already has it, might as well use it
        result, self.logger = corr_obj.getLogger(logger_name=logger_name,
                                                 log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        self.logger.debug('Successfully created logger for {}'.format(logger_name))

    def initialise(self, *args, **kwargs):
        """
        Set up F-engines on this device. This is done after programming the
        devices in the instrument.
        :return:
        """
        # This isn't necessary directly after programming; F-engines start-up disabled.
        # However, is needed if re-initialising an already-running correlator.
        self.data_stream._tx_disable()
        num_x_hosts = len(self.corr.xhosts)
        x_per_fpga = int(self.corr.configd['xengine']['x_per_fpga'])
        num_x = num_x_hosts * x_per_fpga
        chans_per_x = self.corr.n_chans * 1.0 / num_x
        chans_per_board = self.corr.n_chans * 1.0 / num_x_hosts
        ct_num_accs = self.corr.xops.xeng_acc_len
        if 'x_setup' in self.hosts[0].registers.names():
            self.logger.info('Found num_x independent F-engines')
            # set up the x-engine information in the F-engine hosts
            f_per_x = self.corr.n_chans / num_x
            ip_per_x = 1.0  # TODO put this in config file
            THREADED_FPGA_OP(self.hosts, timeout=10,
                target_function=(lambda fpga_: fpga_.registers.x_setup.write(f_per_x=f_per_x,
                    ip_per_x=ip_per_x, num_x=num_x,),))
            time.sleep(1)
        else:
            self.logger.info('Found FIXED num_x F-engines')

        # set up the corner turner
        reg_error = False
        host_ctr = 0
        for f in self.hosts:
            xeng_start = (host_ctr * (num_x_hosts + 1) + host_ctr / 4) % num_x
            # f.registers.ct_control0.write(tvg_en=True, tag_insert=False)
            try:
                f.registers.ct_control0.write(obuf_read_gap=self.corr.ct_readgap)
                f.registers.ct_control1.write(
                    num_x=num_x,
                    num_x_recip=1.0 / num_x,
                    x_per_board=x_per_fpga,
                    x_per_board_recip=1.0 / x_per_fpga,)
                f.registers.ct_control2.write(
                    chans_per_x=chans_per_x,
                    chans_per_board=chans_per_board,)
                f.registers.ct_control3.write(
                    num_x_boards=num_x_hosts,
                    num_x_boards_recip=1.0 / num_x_hosts,
                    chans_per_x_recip=1.0 / chans_per_x, )
                f.registers.ct_control4.write(ct_board_offset=(xeng_start * ct_num_accs))
                # the 8 and the 32 below are hardware limits.
                # 8 packets in a row to one x-engine, and 32 256-bit
                # words in an outgoing packet
                f.registers.ct_control5.write(ct_freq_gen_offset=(xeng_start * (16 * 32)))
                #https://docs.google.com/spreadsheets/d/1wBXsfUCxf5hzC0G8Vz7emh3qIeYMBLdObgv9pOe_Zgc/edit#gid=1568192830
            except ValueError:
                #couldn't find the appropriate fields in the registers. Trying another mapping.
                f.registers.ct_control0.write(
                    obuf_read_gap=self.corr.ct_readgap,
                    chans_per_x_recip=1.0 / chans_per_x,)
                f.registers.ct_control1.write(
                    num_x=num_x,
                    num_x_recip=1.0 / num_x,
                    x_per_board=x_per_fpga,
                    x_per_board_recip=1.0 / x_per_fpga,)
                f.registers.ct_control2.write(
                    chans_per_x=chans_per_x,
                    chans_per_board=chans_per_board,)
                f.registers.ct_control3.write(
                    num_x_boards=num_x_hosts,
                    num_x_boards_recip=1.0 / num_x_hosts,)
                f.registers.ct_control4.write(ct_board_offset=(xeng_start * ct_num_accs))
                # the 8 and the 32 below are hardware limits.
                # 8 packets in a row to one x-engine, and 32 256-bit
                # words in an outgoing packet
                f.registers.ct_control5.write(ct_freq_gen_offset=(xeng_start * (16 * 32)))
            except AttributeError:
                reg_error = True
            host_ctr += 1
        if reg_error:
            cts = '['
            for reg in self.hosts[0].registers:
                if reg.name.startswith('ct_control'):
                    cts += '{}, '.format(reg.name)
                ctr = cts[:-2] + ']'
            self.logger.warning(
                'No corner turner control registers found, or they are '
                'incorrect/old. Expect ct_control[0,1,2,3], found: {}.'.format(cts))

        # write the board IDs to the fhosts
        output_port = self.data_stream.destination.port
        board_id = 0
        for f in self.hosts:
            f.registers.tx_metadata.write(board_id=board_id, porttx=output_port)
            board_id += 1

        # where does the F-engine data go?
        self.data_stream.write_destination()
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_stream_destinations()

        # set eq and shift
        self.set_fft_shift_all()
        self.eq_set()

        # configure the ethernet cores.
        THREADED_FPGA_FUNC(self.hosts, timeout=self.timeout,
            target_function=('setup_host_gbes', (), {}))

        # subscribe to multicast groups
        self.subscribe_to_multicast()

    def configure(self, *args, **kwargs):
        """
        Configure the fengine operations - this is done whenever a correlator
        is instantiated.
        :return:
        """
        assert len(self.corr.fhosts) > 0
        _fengd = self.corr.configd['fengine']

        self.pfb_bits = int(_fengd['pfb_bits'])
        self.quant_bits = int(_fengd['quant_bits'])
        self.decimation_factor = int(self.corr.configd['fengine']['decimation_factor'])

        dig_streams = []

        source_mcast = _fengd.get('source_mcast_ips', None)
        assert isinstance(source_mcast, str)
        source_mcast = re.split(r'[,\s]+', source_mcast)
        assert isinstance(source_mcast, list)
        source_names = utils.get_sources(config=self.corr.configd)
        for ctr, src in enumerate(source_mcast):
            source_mcast[ctr] = src.strip()
        assert len(source_mcast) == len(source_names), (
            'Source names ({}) must be paired with multicast source '
            'addresses ({})'.format(len(source_names), len(source_mcast)))
        for ctr, source in enumerate(source_names):
            addr = StreamAddress.from_address_string(source_mcast[ctr])
            dig_src = fhost_fpga.InputStreamDetails(source, addr, ctr)
            dig_streams.append(dig_src);

        # assemble the inputs given into a list
        _feng_temp = []
        for stream_index, stream_object in enumerate(dig_streams):
            new_feng = fhost_fpga.Fengine(
                input_stream=stream_object,
                host=None,
                offset=stream_object.input_number % self.corr.f_per_fpga,
                feng_id=stream_index, descriptor=self.corr.descriptor, *args, **kwargs)
            new_feng.eq_bram_name = 'eq{}'.format(new_feng.offset)
            dest_ip_range = new_feng.input.destination.ip_range
            assert dest_ip_range == self.corr.n_input_streams_per_fengine, (
                'F-engines should be receiving from {} streams.'.format(
                    self.corr.n_input_streams_per_fengine))
            _feng_temp.append(new_feng)

        # check that the inputs all have the same IP ranges
        _ip_range0 = _feng_temp[0].input.destination.ip_range
        for _feng in _feng_temp:
            _ip_range = _feng.input.destination.ip_range
            assert _ip_range == _ip_range0, (
                'All F-engines should be receiving from {} streams.'.format(
                    self.corr.n_input_streams_per_fengine))

        # assign inputs to fhosts
        self.logger.info('Assigning Fengines to f-hosts')
        _feng_ctr = 0
        self.fengines = []
        for fhost in self.hosts:
            fhost.fengines = []
            for fengnum in range(0, self.corr.f_per_fpga):
                _feng = _feng_temp[_feng_ctr]
                _feng.host = fhost
                self.fengines.append(_feng)
                fhost.add_fengine(_feng)
                self.logger.info('\t{}: {}'.format(_feng_ctr, _feng))
                _feng_ctr += 1

        if _feng_ctr != len(self.hosts) * self.corr.f_per_fpga:
            raise RuntimeError(
                'We have different numbers of inputs ({}) and F-engines ({}). Problem.'.format(
                    _feng_ctr, len(self.hosts) * self.corr.f_per_fpga))
        self.logger.info('done.')

        output_name, output_address = utils.parse_output_products(_fengd)
        assert len(output_name) == 1, 'Currently only single feng products supported.'
        output_name = output_name[0]
        output_address = output_address[0]
        if output_address.ip_range != 1:
            raise RuntimeError(
                'The f-engine\'s given output address range ({}) must be one, '
                'a starting base address.'.format(output_address))
        num_xeng = len(self.corr.xhosts) * self.corr.x_per_fpga
        output_address.ip_range = num_xeng
        max_pkt_size = self.corr.f_stream_payload_len
        self.data_stream = FengineStream(output_name, output_address, self, max_pkt_size, *args, **kwargs)
        self.data_stream.set_source([feng.input.destination for feng in self.fengines])
        self.corr.add_data_stream(self.data_stream)

    def sys_reset(self, sleeptime=0):
        """
        Pulse the sys_rst line on all F-engine hosts
        :param sleeptime:
        :return:
        """
        self.logger.info('Forcing an F-engine resync')
        THREADED_FPGA_OP(self.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.registers.control.write(sys_rst='pulse'),))
        if sleeptime > 0:
            time.sleep(sleeptime)

    def set_center_freq(self,freq):
        """Set the DDC's center frequency in Hz. """
        self.logger.info("Attempting to set the center frequency to {:.5f} MHz".format(freq/1e6))
        #if (band > 0):
        #    raise NotImplementedError('This is not implemented for anything other than the default band.')
        if (self.decimation_factor==1):
            self.logger.info("No point setting the center frequency in wideband modes.")
            return self.corr.sample_rate_hz/4.
        offset = self.corr.sample_rate_hz/4./self.decimation_factor
        min_freq=offset
        max_freq=(self.corr.sample_rate_hz/2.) - offset
        if (freq < min_freq):
            freq=min_freq
        if (freq>max_freq):
            freq=max_freq
        self._set_osc_freq(freq)
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_center_freq()
        return self.get_center_freq()

    def get_center_freq(self):
        """Fetch the tuned center-frequency of the DDC."""
        #if (band > 0):
        #    raise NotImplementedError('This is not implemented for anything other than the default band.')
        if (self.decimation_factor==1):
            return self.corr.sample_rate_hz/4.
        #offset = self.corr.sample_rate_hz/4./self.decimation_factor
        osc_freq=self._get_osc_freq()
        self.logger.info("Center frequency is {:.5f} MHz".format((osc_freq)/1e6))
        return osc_freq

    def _set_osc_freq(self,freq):
        """Set the DDC oscillator frequency to "freq" Hz."""
        #if (band > 0):
        #    raise NotImplementedError('This is not implemented for anything other than the default band.')
        self.logger.debug('Setting DDC oscillator freq to {:.3f} MHz'.format(freq/1.e6))
        reg_value = freq*(2**22)/self.corr.sample_rate_hz
        THREADED_FPGA_OP(self.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.registers.freq_cwg_osc.write(frequency=reg_value),))
        return self._get_osc_freq()

    def _get_osc_freq(self):
        """Return the hardware configured oscillator frequency, in Hz."""
        #if (band > 0):
        #    raise NotImplementedError('This is not implemented for anything other than the default band.')
        rv =THREADED_FPGA_OP(self.hosts,timeout=1,target_function=(lambda fpga_: fpga_.registers.freq_cwg_osc.read()['data']['frequency'],)) 
        if min(rv.values()) != max(rv.values()): 
            self.logger.warning("Fhosts have different tuning frequencies!")
            raise RuntimeError("Fhosts have different tuning frequencies!")
        rv=rv.values()[0]*self.corr.sample_rate_hz/(2**22)
        self.logger.debug('DDC oscillator freq is {:.3f} MHz'.format(rv/1.e6))
        return rv

    def get_rx_timestamps(self, src=0):
        """
        Are the timestamps being received by the F-engines okay?
        :return: (a boolean, the F-engine times as 48-bit counts,
        their unix representations)
        """
        self.logger.debug('Checking timestamps on F hosts...')
        start_time = time.time()
        results = THREADED_FPGA_FUNC(self.hosts, timeout=self.timeout,
            target_function=('get_local_time', [src], {}))
        read_time = time.time()
        elapsed_time = read_time - start_time
        feng_mcnts = {}
        feng_times = {}
        rv = True
        for host in self.hosts:
            feng_mcnt = results[host.host]
            feng_mcnts[host.host] = feng_mcnt
            feng_times[host.host] = self.corr.time_from_mcnt(feng_mcnt)

        for host in self.hosts:
            feng_mcnt = results[host.host]
            feng_time = self.corr.time_from_mcnt(feng_mcnt)
            # are the count bits okay?
            if feng_mcnt & 0xfff != 0:
                errmsg = (
                    '{},{}: bottom 12 bits of timestamp from F-engine are '
                    'not zero?! feng_mcnt({:012X})'.format(host.host, host.fengines[0].input.name,
                        feng_mcnt))
                self.logger.error(errmsg)
                rv = False
            # is the time in the future?
            if feng_time > (read_time + (self.corr.time_jitter_allowed)):
                errmsg = (
                    '{}, {}: F-engine time cannot be in the future? '
                    'now({:.3f}) feng_time({:.3f})'.format(host.host, host.fengines[0].input.name,
                        read_time, feng_time))
                self.logger.error(errmsg)
                rv = False
            # is the time close enough to local time?
            if abs(read_time - feng_time) > self.corr.time_offset_allowed:
                errmsg = (
                    '{}, {}: time calculated from board cannot be so '
                    'far from local time: now({:.3f}) feng_time({:.3f}) diff({:.3f})'.format(
                        host.host, host.fengines[0].input.name, read_time, feng_time,
                        read_time - feng_time))
                self.logger.error(errmsg)
                rv = False
        # are they all within 500ms of one another?
        diff = max(feng_times.values()) - min(feng_times.values())
        if diff > (self.corr.time_jitter_allowed + elapsed_time):
            errmsg = (
                'F-engine timestamps are too far apart: {:.3f}. Took {:.3f}. to read all boards.'.format(
                    diff, elapsed_time))
            self.logger.error(errmsg)
            rv = False
        self.logger.debug('\tdone.')
        return rv, feng_mcnts, feng_times

    def threaded_feng_operation(self, timeout, target_function):
        """
        Thread any operation against many FPGA objects
        :param fpga_list: list of KatcpClientFpga objects
        :param timeout: how long to wait before timing out
        :param target_function: a tuple with three parts:
                                1. reference, the function object that must be
                                   run - MUST take FPGA object as first argument
                                2. tuple, the arguments to the function
                                3. dict, the keyword arguments to the function
                                e.g. (func_name, (1,2,), {'another_arg': 3})
        :return: a dictionary of the results, keyed on feng index
        """
        target_function = CHECK_TARGET_FUNC(target_function)

        def jobfunc(resultq, feng):
            rv = target_function[0](feng, *target_function[1], **target_function[2])
            resultq.put_nowait((feng.input_number, rv))

        num_fengs = len(self.fengines)
        result_queue = Queue.Queue(maxsize=num_fengs)
        thread_list = []
        for feng_ in self.fengines:
            thread = threading.Thread(target=jobfunc, args=(result_queue, feng_))
            thread.setDaemon(True)
            thread.start()
            thread_list.append(thread)
        for thread_ in thread_list:
            thread_.join(timeout)
            if thread_.isAlive():
                break
        returnval = {}
        hosts_missing = [feng.input_number for feng in self.fengines]
        while True:
            try:
                result = result_queue.get_nowait()
                returnval[result[0]] = result[1]
                hosts_missing.pop(hosts_missing.index(result[0]))
            except Queue.Empty:
                break
        if hosts_missing:
            errmsg = (
                'Ran \'{}\' on fengines. Did not complete: {}.'.format(target_function[0].__name__,
                    hosts_missing))
            self.logger.error(errmsg)
            raise RuntimeError(errmsg)
        return returnval

    def delay_set(self, input_name, loadtime=None, delay=0, delay_delta=0, phase=0, phase_delta=0):
        """
        Set the delay and phase coefficients for a single input.
        :param loadtime: the UNIX time at which to effect the changes. Default: immediately.
        :param delay: delay in seconds
        :param delay_delta: delay change in seconds per second
        :param phase: phase offset in radians
        :param phase_delta: phase rate of change in radians/second.
        :return: True/False
        """
        sample_rate_hz = self.corr.sample_rate_hz
        loadmcnt = self._delays_check_loadtime(loadtime)
        if not (loadmcnt > 0):
            self.logger.error("Dropping delay request.")
        else:
            delay = delayops.prepare_delay_vals(((delay, delay_delta), (phase, phase_delta)),
                sample_rate_hz)
            delay.load_mcnt = loadmcnt
            feng = self.get_fengine(input_name)
            feng.delay_set(delay)
            if self.corr.sensor_manager:
                self.corr.sensor_manager.sensors_feng_delays(feng)

    def delay_set_all(self, loadtime, delay_list):
        """
        Set the delays for all inputs in the system
        :param loadtime: the UNIX time at which to effect the changes
        :param delay_list: a list of ICD strings, one for each input.
                            A list of strings (delay,rate:phase,rate) or
                             delay tuples ((delay,rate),(phase,rate))
        :return: True if all success, False otherwise.
        """
        loadmcnt = self._delays_check_loadtime(loadtime)
        self.logger.debug("Received delay model update for {} (mcnt {}) at {}: {}.".format(loadtime,
                loadmcnt, time.time(),delay_list.__str__()))
        if not (loadmcnt > 0):
            self.logger.error("Dropping delay request.")
        else:
            sample_rate_hz = self.corr.get_scale_factor()
            delays = delayops.process_list(delay_list, sample_rate_hz)
            if len(delays) != len(self.fengines):
                raise ValueError('Have {} F-engines, received {} delay coefficient sets.'.format(
                    len(self.fengines), len(delays)))
            for delay in delays:
                delay.load_mcnt = loadmcnt
            rv = self.threaded_feng_operation(timeout=self.timeout,
                target_function=(lambda feng_: feng_.delay_set(delays[feng_.input_number]),))
            if len(rv) != len(self.fengines):
                rv = False
                self.logger.error("Only got {} delay responses.".format(len(rv)))
            if self.corr.sensor_manager:
                for feng in self.fengines:
                    self.corr.sensor_manager.sensors_feng_delays(feng)

#    def delays_get(self, input_name=None):
#        """
#        Get the delays for a given source name.
#        :param input_name: a source name. If None, get all the
#            fengine delay data.
#        :return:
#        """
#        if input_name is None:
#            rv=self.threaded_feng_operation(timeout=5, target_function=(lambda feng_: feng_.delay_get(),))
#        else:
#            feng=self.get_fengine(input_name)
#            rv={input_name: feng.delay_get()}
#        return feng.delay_get()

    def _delays_check_loadtime(self, loadtime):
        """
        Check a given delay load time.
        :param loadtime: the UNIX time
        :return: the system sample count
        """
        time_now = time.time()
        if loadtime is None:
            loadtime = time_now + self.corr.min_load_time + 0.1

        # check that load time is not too soon or in the past
        if loadtime < (time_now + self.corr.min_load_time):
            errmsg = (
                'Delay model update leadtime ({} s) error. tnow: {}, tload: {}.'.format(
                    self.corr.min_load_time, time_now, loadtime))
            self.logger.error(errmsg)
            return None

        #TODO this logic doesn't work correctly all the time, because this function can be called when setting random Fengines, and so shouldn't hardcode the reference to feng0. disabling for now.
        #last_loadtime = self.corr.time_from_mcnt(
        #    self.fengines[0].last_delay.load_mcnt)
        #if time.time() < last_loadtime:
        #    self.logger.warning(
        #        "Received a delay update before the last one had a chance to load! "
        #        "Queuing is not supported. The last load command (for time {}) will not be applied, "
        #        "and will be overwritten by this command at time {}.".format(last_loadtime,
        #            time.time()))
        loadtime_mcnt = self.corr.mcnt_from_time(loadtime)
        return loadtime_mcnt

    def tx_enable(self, force_enable=False):
        """
        Enable TX on all tengbe cores on all F hosts
        :return:
        """
        if force_enable:
            self.data_stream._tx_enable()
        else:
            self.data_stream.tx_enable()

    def tx_disable(self, force_disable=False):
        """
        Disable TX on all tengbe cores on all F hosts
        :return:
        """
        if force_disable:
            self.data_stream._tx_disable()
        else:
            self.data_stream.tx_disable()

    def auto_rst_enable(self):
        """
        Enable hardware automatic resync upon error detection.
        """
        #feng_pipeline_latency = ct+hmc  +  pfb_fir  +  fft  +  cd+hmc  +  misc
        max_difference=(self.corr.n_chans*2*self.corr.xops.xeng_acc_len*2*self.decimation_factor + 50000) + (self.decimation_factor*self.corr.n_chans*16*2) + (self.decimation_factor*self.corr.n_chans*7) +  (512 + 50000) + (50000)
        THREADED_FPGA_OP(self.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.registers.time_check.write(max_difference=max_difference), ))
        THREADED_FPGA_OP(self.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.registers.control.write(auto_rst_enable=True,time_diff_check_en=True), ))
        self.logger.info('F-engine hardware auto rst/resync mechanism enabled.')

    def auto_rst_disable(self):
        """
        Disable hardware automatic resync upon error detection.
        """
        THREADED_FPGA_OP(self.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.registers.control.write(auto_rst_enable=False), ))
        self.logger.info('F-engine hardware auto rst/resync mechanism disabled.')

    def get_fengine(self, input_name):
        """
        Find an f-engine by name or index.
        :param input_name:
        :return:
        """
        for fhost in self.hosts:
            try:
                return fhost.get_fengine(input_name)
            except fhost_fpga.InputNotFoundError:
                pass
        errmsg = ('Could not find input {} anywhere. Available inputs: {}'.format(input_name,
            self.corr.get_input_labels()))
        self.logger.error(errmsg)
        raise ValueError(errmsg)

    def eq_get(self, input_name=None):
        """
        Return the EQ arrays in a dictionary, arranged by input name.
        :param input_name: if this is given, return only this input's eq
        :return: a dictionary, indexed by input_name
        """
        if input_name is None:
            fengs = self.fengines
            rv = self.threaded_feng_operation(timeout=self.timeout,
                target_function=(lambda feng_: feng_.eq_get(),))
        else:
            fengs = [self.get_fengine(input_name)]
            rv = {input_name: fengs[0].eq_get()}
        # update the sensors, if they're being used:
        for feng in fengs:
            if self.corr.sensor_manager:
                self.corr.sensor_manager.sensors_feng_eq(feng)
        return rv

    def eq_set(self, new_eq=None, input_name=None):
        """
        Set the EQ for a specific input, or all inputs.
        :param new_eq: an eq list or value or poly
        :param input_name: the input name. None for all fengines.
        :return:
        """
        #neweq = utils.process_new_eq(new_eq)
        # if no input is given, apply the new eq to all inputs
        if input_name is None:
            self.logger.info('Setting EQ on all inputs to new given EQ.')
            fengs = self.fengines
            rv = self.threaded_feng_operation(timeout=self.timeout*(self.corr.n_chans/1024),
                target_function=(lambda feng_: feng_.eq_set(new_eq),))
        else:
            fengs = [self.get_fengine(input_name)]
            fengs[0].eq_set(eq_poly=new_eq)
        for feng in fengs:
            if self.corr.sensor_manager:
                self.corr.sensor_manager.sensors_feng_eq(feng)

    def set_fft_shift_all(self, shift_value=None):
        """
        Set the FFT shift on all boards.
        :param shift_value:
        :return:
        """
        self.logger.info('Attempting to set the FFT shift to {} on all F-engine boards...'.format(shift_value))
        if shift_value=='auto':
            import numpy
            timeout = numpy.log2(self.corr.n_chans)*3
        else:
            timeout = self.timeout
        THREADED_FPGA_FUNC(self.hosts, timeout, ('set_fft_shift', (shift_value,),))
        self.logger.info('done.')
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_feng_fft_shift()

    def get_fft_shift_all(self):
        """
        Get the FFT shift value on all boards.
        :return:
        """
        # get the fft shift values
        rv = THREADED_FPGA_FUNC(self.hosts, 10, 'get_fft_shift')
        return rv

    def fengine_to_host_mapping(self):
        """
        Return a mapping of hostnames to engine numbers
        :return:
        """
        mapping = {}
        for host in self.hosts:
            rv = ['feng{:03}'.format(feng.input_number) for feng in host.fengines]
            mapping[host.host] = rv
        return mapping

    def clear_status_all(self):
        """
        Clear the various status registers and counters on all the fengines
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, 10, 'clear_status')

    def subscribe_to_multicast(self):
        """
        Subscribe all F-engine network cores to their multicast data
        :return:
        """
        self.logger.info('Subscribing F-engine inputs:')
        # don't do this in parallel. Ease the load on the switch?
        for fhost in self.hosts:
            fhost.subscribe_to_multicast()
        # res = THREADED_FPGA_FUNC(self.hosts, timeout=10,
        #                          target_function=('subscribe_to_multicast',
        #                                           [self.corr.f_per_fpga], {}))

    def sky_freq_to_chan(self, freq):
        raise NotImplementedError

    def freq_to_chan(self, freq):
        """
        In which fft channel is a frequency found?
        :param freq: frequency, in Hz, float
        :return: the fft channel, integer
        """
        center = self.get_center_freq()
        _bw = self.corr.sample_rate_hz / 2.0 / self.decimation_factor
        _band_min = center_freq - _bw/2
        _band_max = center_freq + bw/2
        if (freq > _band_max) or (freq <= _band_min):
            raise RuntimeError('frequency {:.3f}MHz is not in our band ({:.3f} to {:.3f} MHz).'.format(freq/1e6,_band_min/1e6,_band_max/1e6))
        import numpy
        _hz_per_chan = _band / self.corr.n_chans
        _chan_index = numpy.floor((freq-_band_min) / _hz_per_chan)
        return _chan_index

    def get_quant_snap(self, input_name, channel_select=-1):
        """
        Get the quantiser snapshot for this input_name
        :param input_name:
        :param channel_select:
        :return:
        """
        feng = self.get_fengine(input_name)
        return feng.get_quant_snapshot(channel_select=channel_select)

    def get_adc_snapshot(self, input_name=None, unix_time=-1):
        """
        Read the small voltage buffer for a input from a host.
        :param input_name: the input name, if None, will return all inputs
        :param unix_time: the time at which to trigger the snapshots
        :return: {feng_name0: AdcData(),
                  feng_name1: AdcData(),
                 }
        """
        # if no trigger time was specified, trigger in 2s' time.
        if unix_time < 0:
            #unix_time = time.time() + 2
            #self.logger.info('Trigger time not specified; triggering in 2s.')
            ldmcnt = None
            timeout = 10
        else:
            ldmcnt = self.corr.mcnt_from_time(unix_time)
            ldmcnt = (ldmcnt >> 12) << 12
            timeout = unix_time - time.time()
            if timeout < 0:
                raise RuntimeError("Cannot trigger at a time in the past!")
            timeout += 1

        if input_name is None:
            # get data for all F-engines triggered at the same time
            res = THREADED_FPGA_FUNC(self.hosts, timeout=timeout + 10,
                target_function=('get_adc_snapshots', [], {'loadcnt': ldmcnt, 'timeout': timeout}))
            rv = {}
            for feng in self.fengines:
                rv[feng.name] = res[feng.host.host]['p{}'.format(feng.offset)]
            return rv
        else:
            # return the data only for one given input
            rv = None
            host = self.get_fengine(input_name).host
            rv = host.get_adc_snapshots(input_name, timeout=timeout)
            return {input_name: rv}

    def get_version_info(self):
        """
        Get the version information for the hosts
        :return: a dict of {file: version_info, }
        """
        try:
            return self.hosts[0].get_version_info()
        except AttributeError:
            return {}
# end
