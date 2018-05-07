import numpy
import time

from casperfpga import utils as fpgautils
from casperfpga.CasperLogHandlers import CasperConsoleHandler

from data_stream import SPEADStream, FENGINE_CHANNELISED_DATA, \
    DIGITISER_ADC_SAMPLES
import utils
import fhost_fpga
import fxcorrelator_speadops as speadops
import delay as delayops

import logging

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


class FengineStream(SPEADStream):
    """
    An f-engine SPEAD stream
    """
    def __init__(self, name, destination, fops):
        """
        Make a SPEAD stream.
        :param name: the name of the stream
        :param destination: where is it going?
        :return:
        """
        self.fops = fops
        super(FengineStream, self).__init__(
            name, FENGINE_CHANNELISED_DATA, destination)

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
            THREADED_FPGA_OP(self.fops.hosts, timeout=5, target_function=(
                lambda fpga_: fpga_.registers.iptx_base.write_int(txip),))
        except AttributeError:
            errmsg = 'Writing stream %s destination to hardware ' \
                     'failed!' % self.name
            self.fops.logger.error(errmsg)
            raise RuntimeError(errmsg)

    def tx_enable(self, n_retries=5):
        """
        Enable TX for this data stream
        :return:
        """
        self.descriptors_issue()
        self.fops.logger.warn(
            '{}: Ignoring command to start F-engine stream.'.format(self.name))

    def _tx_enable(self, n_retries=5):
        """
        Enable TX for this data stream
        """
        done = False
        while n_retries > 0:
            try:
                THREADED_FPGA_OP(
                    self.fops.hosts, 5,
                    (lambda fpga_: fpga_.tx_enable(),))
                n_retries = -1
            except RuntimeError:
                if n_retries == 0:
                    raise
                else:
                    n_retries -= 1
                    self.fops.logger.warning('Failed to start F-engine output; %i retries remaining.'%n_retries)
                    time.sleep(2)
        if n_retries == -1:
            self.tx_enabled = True
            self.fops.logger.info('F-engine output enabled')

        

    def tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        self.fops.logger.warn(
            '{}: stopping F-engine streams will break the correlator. '
            'Ignoring.'.format(self.name))

    def _tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        THREADED_FPGA_OP(
            self.fops.hosts, 5,
            (lambda fpga_: fpga_.tx_disable(),))
        self.fops.logger.info('F-engine output disabled')


    def __str__(self):
        return 'FengineStream %s -> %s' % (self.name, self.destination)


class FEngineOperations(object):

    def __init__(self, corr_obj):
        """
        A collection of F-engine operations that act on/with a
        correlator instance.
        :param corr_obj:
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.fhosts
        # self.logger = corr_obj.logger

        self.fengines = []
        self.data_stream = None
        
        # Now creating separate instances of loggers as needed
        logger_name = '{}_FEngOps'.format(corr_obj.descriptor)
        self.logger = logging.getLogger(logger_name)
        # - Give logger some default config
        console_handler_name = '{}_stream'.format(corr_obj.descriptor)
        console_handler = CasperConsoleHandler(name=console_handler_name)
        self.logger.addHandler(console_handler)
        self.logger.setLevel(logging.DEBUG)
        infomsg = 'Successfully created logger for {}'.format(console_handler_name)
        self.logger.info(infomsg)
        
    def initialise(self):
        """
        Set up F-engines on this device. This is done after programming the
        devices in the instrument.
        :return:
        """
        #This isn't necessary directly after programming; F-engines start-up disabled. 
        #However, is needed if re-initialising an already-running correlator.
        self.data_stream._tx_disable()
        num_x_hosts = len(self.corr.xhosts)
        x_per_fpga = int(self.corr.configd['xengine']['x_per_fpga'])
        num_x = num_x_hosts * x_per_fpga
        if 'x_setup' in self.hosts[0].registers.names():
            self.logger.info('Found num_x independent F-engines')
            # set up the x-engine information in the F-engine hosts
            f_per_x = self.corr.n_chans / num_x
            ip_per_x = 1.0  # TODO put this in config file
            THREADED_FPGA_OP(
                self.hosts, timeout=10,
                target_function=(
                    lambda fpga_:
                    fpga_.registers.x_setup.write(
                        f_per_x=f_per_x, ip_per_x=ip_per_x, num_x=num_x,),))
            time.sleep(1)
        else:
            self.logger.info('Found FIXED num_x F-engines')

        # set up the corner turner
        reg_error = False
        host_ctr = 0
        for f in self.hosts:
            # f.registers.ct_control0.write(tvg_en=True, tag_insert=False)
            f.registers.ct_control0.write(obuf_read_gap=self.corr.ct_readgap)
            chans_per_x = self.corr.n_chans * 1.0 / num_x
            chans_per_board = self.corr.n_chans * 1.0 / num_x_hosts
            try:
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
                xeng_start = (host_ctr * (num_x_hosts + 1) + host_ctr / 4) % num_x
                ct_num_accs = 256
                f.registers.ct_control4.write(
                    ct_board_offset=(xeng_start * ct_num_accs))
                # the 8 and the 32 below are hardware limits.
                # 8 packets in a row to one x-engine, and 32 256-bit
                # words in an outgoing packet
                f.registers.ct_control5.write(
                    ct_freq_gen_offset=(xeng_start * (8 * 32)))
            except AttributeError:
                reg_error = True
            host_ctr += 1
        if reg_error:
            cts = '['
            for reg in self.hosts[0].registers:
                if reg.name.startswith('ct_control'):
                    cts += '%s, ' % reg.name
                ctr = cts[:-2] + ']'
            self.logger.warning(
                'No corner turner control registers found, or they are '
                'incorrect/old. Expect ct_control[0,1,2,3], found: %s.' % cts)

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
        self.eq_write_all()
        self.set_fft_shift_all()

        #configure the ethernet cores.
        THREADED_FPGA_FUNC(
                self.hosts, timeout=5,
                target_function=('setup_host_gbes',
                                 (), {}))

        #subscribe to multicast groups
        self.subscribe_to_multicast()

    def configure(self):
        """
        Configure the fengine operations - this is done whenever a correlator
        is instantiated.
        :return:
        """
        assert len(self.corr.fhosts) > 0
        _fengd = self.corr.configd['fengine']

        dig_streams = []
        for stream in self.corr.data_streams:
            if stream.category == DIGITISER_ADC_SAMPLES:
                dig_streams.append((stream.name, stream.input_number))
        dig_streams = sorted(dig_streams,
                             key=lambda stream: stream[1])

        # match eq polys to input names
        eq_polys = {}
        for dig_stream in dig_streams:
            stream_name = dig_stream[0]
            eq_polys[stream_name] = utils.process_new_eq(
                _fengd['default_eq_poly'])
        assert len(eq_polys) == len(dig_streams), (
            'Digitiser input names (%d) must be paired with EQ polynomials '
            '(%d).' % (len(dig_streams), len(eq_polys)))

        # assemble the inputs given into a list
        _feng_temp = []
        for stream_index, stream_value in enumerate(dig_streams):
            new_feng = fhost_fpga.Fengine(
                input_stream=self.corr.get_data_stream(stream_value[0]),
                host=None,
                offset=stream_value[1] % self.corr.f_per_fpga,
                feng_id=stream_index, descriptor=self.corr.descriptor)
            new_feng.eq_poly = eq_polys[new_feng.name]
            new_feng.eq_bram_name = 'eq%i' % new_feng.offset
            dest_ip_range = new_feng.input.destination.ip_range
            assert dest_ip_range == self.corr.n_input_streams_per_fengine, (
                'F-engines should be receiving from %d streams.' %
                self.corr.n_input_streams_per_fengine)
            _feng_temp.append(new_feng)

        # check that the inputs all have the same IP ranges
        _ip_range0 = _feng_temp[0].input.destination.ip_range
        for _feng in _feng_temp:
            _ip_range = _feng.input.destination.ip_range
            assert _ip_range == _ip_range0, (
                'All F-engines should be receiving from %d streams.' %
                self.corr.n_input_streams_per_fengine)

        # assign inputs to fhosts
        self.logger.info('Assigning Fengines to f-hosts')
        _feng_ctr = 0
        self.fengines = []
        for fhost in self.hosts:
            fhost.fengines=[]
            for fengnum in range(0, self.corr.f_per_fpga):
                _feng = _feng_temp[_feng_ctr]
                _feng.host = fhost
                self.fengines.append(_feng)
                fhost.add_fengine(_feng)
                self.logger.info('\t%i: %s' % (_feng_ctr, _feng))
                _feng_ctr += 1
        if _feng_ctr != len(self.hosts) * self.corr.f_per_fpga:
            raise RuntimeError(
                'We have different numbers of inputs (%d) and F-engines (%d). '
                'Problem.', _feng_ctr, len(self.hosts) * self.corr.f_per_fpga)
        self.logger.info('done.')

        output_name, output_address = utils.parse_output_products(_fengd)
        assert len(output_name) == 1, 'Currently only single feng products ' \
                                      'supported.'
        output_name = output_name[0]
        output_address = output_address[0]
        if output_address.ip_range != 1:
            raise RuntimeError(
                'The f-engine\'s given output address range (%s) must be one, a'
                ' starting base address.' % output_address)
        num_xeng = len(self.corr.xhosts) * self.corr.x_per_fpga
        output_address.ip_range = num_xeng
        self.data_stream = FengineStream(output_name, output_address, self)
        self.data_stream.set_source(
            [feng.input.destination for feng in self.fengines]
        )
        self.corr.add_data_stream(self.data_stream)

        # set the sample rate on the Fhosts
        for host in self.hosts:
            host.rx_data_sample_rate_hz = self.corr.sample_rate_hz

    def sys_reset(self, sleeptime=0):
        """
        Pulse the sys_rst line on all F-engine hosts
        :param sleeptime:
        :return:
        """
        self.logger.info('Forcing an F-engine resync')
        THREADED_FPGA_OP(self.hosts, timeout=5, target_function=(
            lambda fpga_: fpga_.registers.control.write(sys_rst='pulse'),))
        if sleeptime > 0:
            time.sleep(sleeptime)

    def get_rx_timestamps(self,src=0):
        """
        Are the timestamps being received by the F-engines okay?
        :return: (a boolean, the F-engine times as 48-bit counts,
        their unix representations)
        """
        self.logger.info('Checking timestamps on F hosts...')
        start_time=time.time()
        results = THREADED_FPGA_FUNC(
            self.hosts, timeout=5,
            target_function=('get_local_time',[src],{}))
        read_time = time.time()
        elapsed_time=read_time-start_time
        feng_mcnts = {}
        feng_times = {}
        rv=True
        for host in self.hosts:
            feng_mcnt = results[host.host]
            feng_mcnts[host.host] = feng_mcnt
            feng_times[host.host] = self.corr.time_from_mcnt(feng_mcnt)

        for host in self.hosts:
            feng_mcnt = results[host.host]
            feng_time = self.corr.time_from_mcnt(feng_mcnt)
            # are the count bits okay?
            if feng_mcnt & 0xfff != 0:
                errmsg = '%s,%s: bottom 12 bits of timestamp from F-engine are ' \
                       'not zero?! feng_mcnt(%012X)' % (host.host,
                              host.fengines[0].input.name,feng_mcnt)
                self.logger.error(errmsg)
                rv=False
            # is the time in the future?
            if feng_time > (read_time+(self.corr.time_jitter_allowed)):
                errmsg = '%s, %s: F-engine time cannot be in the future? ' \
                       'now(%.3f) feng_time(%.3f)' % (host.host,
                          host.fengines[0].input.name,read_time,feng_time)
                self.logger.error(errmsg)
                rv=False
            # is the time close enough to local time?
            if abs(read_time - feng_time) > self.corr.time_offset_allowed:
                errmsg = '%s, %s: time calculated from board cannot be so ' \
                         'far from local time: now(%.3f) feng_time(%.3f) ' \
                         'diff(%.3f)' % (host.host, host.fengines[0].input.name,
                            read_time, feng_time, read_time - feng_time)
                self.logger.error(errmsg)
                rv=False
        # are they all within 500ms of one another?
        diff = max(feng_times.values()) - min(feng_times.values())
        if diff > (self.corr.time_jitter_allowed+elapsed_time):
            errmsg = 'F-engine timestamps are too far apart: %.3fs. Took %.3fs. to read all boards.' %(diff,elapsed_time)
            self.logger.error(errmsg)
            rv=False
        self.logger.info('\tdone.')
        return rv, feng_mcnts, feng_times

    def delay_set_all(self, loadtime, delay_list):
        """
        Set the delays for all inputs in the system
        :param loadtime: the UNIX time at which to effect the changes
        :param delay_list: a list of ICD strings, one for each input
        :return: an in-order list of fengine delay results
        """
        if loadtime <= 0:
            actual_vals = self.delays_get()
            rv = []
            for feng in self.fengines:
                rv.append(actual_vals[feng.name])
            return rv
        loadmcnt = self._delays_check_loadtime(loadtime)
        sample_rate_hz = self.corr.get_scale_factor()
        delays = delayops.process_list(delay_list, sample_rate_hz)
        if len(delays) != len(self.fengines):
            raise ValueError('Have %i F-engines, received %i delay coefficient '
                             'sets.' % (len(self.fengines), len(delays)))
        # collect delay coefficient sets and fhosts
        delays_by_host = {host.host: [] for host in self.hosts}
        for feng in self.fengines:
            delays_by_host[feng.host.host].append(delays[feng.input_number])
        actual_vals = THREADED_FPGA_FUNC(
            self.corr.fhosts, timeout=0.5,
            target_function=('delay_set_all', [loadmcnt, delays_by_host], {}))
        rv = {}
        for val in actual_vals.values():
            rv.update(
                {fengkey: fengvalue for fengkey, fengvalue in val.items()})
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_feng_delays()
        actual_vals = rv
        rv = []
        for feng in self.fengines:
            rv.append(actual_vals[feng.name])
        return rv

    def delays_set(self, input_name, loadtime=None,
                   delay=None, delay_rate=None,
                   phase=None, phase_rate=None):
        """
        Set the delay for a given input.
        :param input_name: the name of the input to which we should
            apply the delays
        :param loadtime: the UNIX time to effect the changes
        :param delay:
        :param delay_rate:
        :param phase:
        :param phase_rate:
        :return:
        """
        fengine = self.get_fengine(input_name)
        if loadtime is None:
            loadtime = time.time() + 25
            self.logger.debug('input %s delay setting: no loadtime given, '
                              'setting to 25s in the future.' % input_name)
        if loadtime > 0:
            loadmcnt = self._delays_check_loadtime(loadtime)
            fengine.delay_set(loadmcnt, delay, delay_rate, phase, phase_rate)
            if self.corr.sensor_manager:
                self.corr.sensor_manager.sensors_feng_delays()
        return fengine.delay_get()

    def delays_get(self, input_name=None):
        """
        Get the delays for a given source name or index.
        :param input_name: a source name or index. If None, get all the
            fengine delay data.
        :return:
        """
        if input_name is None:
            actual_vals = THREADED_FPGA_FUNC(
                self.corr.fhosts, timeout=0.5,
                target_function=('delays_get', [], {}))
            rv = {}
            for val in actual_vals.values():
                rv.update(
                    {fengkey: fengvalue for fengkey, fengvalue in val.items()})
            return rv
        feng = self.get_fengine(input_name)
        return feng.delay_get()

    def _delays_check_loadtime(self, loadtime):
        """
        Check a given delay load time.
        :param loadtime: the UNIX time
        :return: the system sample count
        """
        # check that load time is not too soon or in the past
        time_now = time.time()
        if loadtime < (time_now + self.corr.min_load_time):
            errmsg = 'Time given is in the past or does not allow for ' \
                     'enough time to set values'
            self.logger.error(errmsg)
            raise RuntimeError(errmsg)
        loadtime_mcnt = self.corr.mcnt_from_time(loadtime)
        return loadtime_mcnt


    def tx_enable(self,force_enable=False):
        """
        Enable TX on all tengbe cores on all F hosts
        :return:
        """
        if force_enable:
            self.data_stream._tx_enable()
        else:
            self.data_stream.tx_enable()

    def tx_disable(self,force_disable=False):
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
        THREADED_FPGA_OP(
            self.hosts, 5,
            (lambda fpga_: fpga_.registers.control.write(auto_rst_enable=True),))
        self.logger.info('F-engine hardware auto rst/resync mechanism enabled.')

    def auto_rst_disable(self):
        """
        Disable hardware automatic resync upon error detection.
        """
        THREADED_FPGA_OP(
            self.hosts, 5,
            (lambda fpga_: fpga_.registers.control.write(auto_rst_enable=False),))
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
        errmsg = ('Could not find input %s anywhere. Available inputs: %s' % (input_name, self.corr.get_input_labels()))
        self.logger.error(errmsg)
        raise ValueError(errmsg)

    def eq_get(self, input_name=None):
        """
        Return the EQ arrays in a dictionary, arranged by input name.
        :param input_name: if this is given, return only this input's eq
        :return:
        """
        if input_name is not None:
            return {input_name: self.get_fengine(input_name).eq_poly}
        return {
            feng.name: feng.eq_poly for feng in self.fengines
        }

    def eq_set(self, write=True, input_name=None, new_eq=None):
        """
        Set the EQ for a specific input
        :param write: should the value be written to BRAM on the device?
        :param input_name: the input name
        :param new_eq: an eq list or value or poly
        :return:
        """
        if new_eq is None:
            raise ValueError('New EQ of nothing makes no sense.')
        # if no input is given, apply the new eq to all inputs
        if input_name is None:
            self.logger.info('Setting EQ on all inputs to new given EQ.')
            for fhost in self.hosts:
                for feng in fhost.fengines:
                    self.eq_set(write=False, input_name=feng.name,
                                new_eq=new_eq)
            if write:
                self.eq_write_all()
        else:
            feng = self.get_fengine(input_name)
            old_eq = feng.eq_poly[:]
            try:
                neweq = utils.process_new_eq(new_eq)
                feng.eq_poly = neweq
                self.logger.info(
                    'Updated EQ value for input %s: %s...' % (
                        input_name, neweq[0:min(10, len(neweq))]))
                if write:
                    feng.host.write_eq(input_name=input_name)
            except Exception as e:
                feng.eq_poly = old_eq[:]
                self.logger.error('New EQ error - REVERTED to '
                                  'old value! - %s' % e.message)
                raise ValueError('New EQ error - REVERTED to '
                                 'old value! - %s' % e.message)
        if write:
            if self.corr.sensor_manager:
                self.corr.sensor_manager.sensors_feng_eq()

    def eq_write_all(self, new_eq_dict=None):
        """
        Set the EQ gain for given inputs and write the changes to memory.
        :param new_eq_dict: a dictionary of new eq values to store
        :return:
        """
        if new_eq_dict is not None:
            self.logger.info('Updating some EQ values before writing.')
            for feng, new_eq in new_eq_dict.items():
                self.eq_set(write=False, input_name=feng, new_eq=new_eq)
        self.logger.info('Writing EQ on all fhosts based on stored '
                         'per-input EQ values...')
        THREADED_FPGA_FUNC(self.hosts, 10, 'write_eq_all')
        self.logger.info('done.')

    def set_fft_shift_all(self, shift_value=None):
        """
        Set the FFT shift on all boards.
        :param shift_value:
        :return:
        """
        if shift_value is None:
            shift_value = self.corr.fft_shift
        if shift_value < 0:
            raise RuntimeError('Shift value cannot be less than zero')
        self.logger.info('Setting FFT shift to %i on all F-engine '
                         'boards...' % shift_value)
        THREADED_FPGA_FUNC(self.hosts, 10, ('set_fft_shift', (shift_value,),))
        self.corr.fft_shift = shift_value
        self.logger.info('done.')
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_feng_fft_shift()
        return shift_value

    def get_fft_shift_all(self):
        """
        Get the FFT shift value on all boards.
        :return:
        """
        # get the fft shift values
        rv = THREADED_FPGA_FUNC(self.hosts, 10, 'get_fft_shift')
        if rv[rv.keys()[0]] != self.corr.fft_shift:
            self.logger.warning('FFT shift read from fhosts disagrees with '
                                'stored value. Correcting.')
            self.corr.fft_shift = rv[rv.keys()[0]]
        return rv

    def fengine_to_host_mapping(self):
        """
        Return a mapping of hostnames to engine numbers
        :return:
        """
        mapping = {}
        for host in self.hosts:
            rv = ['feng{:03}'.format(feng.input_number)
                  for feng in host.fengines]
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
        for fhost in self.hosts:
            fhost.subscribe_to_multicast(self.corr.f_per_fpga)
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
        _band = self.corr.sample_rate_hz / 2.0
        if (freq > _band) or (freq <= 0):
            raise RuntimeError('frequency %.3f is not in our band' % freq)
        _hz_per_chan = _band / self.corr.n_chans
        _chan_index = numpy.floor(freq / _hz_per_chan)
        return _chan_index

    def get_quant_snap(self, input_name):
        """
        Get the quantiser snapshot for this input_name
        :param input_name:
        :return:
        """
        for host in self.hosts:
            try:
                return host.get_quant_snapshot(input_name)
            except ValueError:
                pass
        raise ValueError(
            'Could not find input %s anywhere. Available inputs: %s' % (
                input_name, self.corr.get_input_labels()))

    def get_adc_snapshot(self, input_name=None, unix_time=-1):
        """
        Read the small voltage buffer for a input from a host.
        :param input_name: the input name, if None, will return all inputs
        :param unix_time: the time at which to trigger the snapshots
        :return: {feng_name0: AdcData(),
                  feng_name1: AdcData(),
                 }
        """
        #if no trigger time was specified, trigger in 2s' time.
        if unix_time < 0:
            #unix_time = time.time() + 2
            #self.logger.info('Trigger time not specified; triggering in 2s.')
            ldmcnt= None
            timeout= 10
        else:
            ldmcnt = self.corr.mcnt_from_time(unix_time)
            ldmcnt = (ldmcnt >> 12) << 12
            timeout = unix_time-time.time()
            if timeout < 0:
                raise RuntimeError("Cannot trigger at a time in the past!")


        if input_name is None:
            # get data for all F-engines triggered at the same time
            res = THREADED_FPGA_FUNC(
                self.hosts, timeout=timeout+10,
                target_function=('get_adc_snapshots', [],
                                 {'loadcnt': ldmcnt,
                                  'timeout': timeout}))
            rv = {}
            for feng in self.fengines:
                rv[feng.name] = res[feng.host.host]['p%i' % feng.offset]
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
