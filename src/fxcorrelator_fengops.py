import numpy
import time

from casperfpga import utils as fpgautils

from data_stream import SPEADStream, FENGINE_CHANNELISED_DATA, \
    DIGITISER_ADC_SAMPLES
import utils
import fhost_fpga
import fxcorrelator_speadops as speadops
import delay as delayops

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


class FengineStream(SPEADStream):
    """
    An x-engine SPEAD stream
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

    def tx_enable(self):
        """
        Enable TX for this data stream
        :return:
        """
        self.descriptors_issue()
        THREADED_FPGA_OP(
            self.fops.hosts, 5,
            (lambda fpga_: fpga_.registers.control.write(gbe_txen=True),))
        self.tx_enabled = True
        self.fops.logger.info('F-engine output enabled')

    def tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        self.fops.logger.info('{}: F-engine streams cannot be stopped.'.format(
            self.name))

    def _tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        THREADED_FPGA_OP(
            self.fops.hosts, 5,
            (lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))
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
        self.logger = corr_obj.logger
        self.fengines = []
        self.data_stream = None

    def initialise_post_gbe(self):
        """
        Perform post-gbe setup initialisation steps
        :return:
        """
        # write the board IDs to the fhosts
        output_port = self.data_stream.destination.port
        board_id = 0
        for f in self.hosts:
            f.registers.tx_metadata.write(board_id=board_id,
                                          porttx=output_port)
            board_id += 1

        # release from reset
        THREADED_FPGA_OP(self.hosts, timeout=10, target_function=(
            lambda fpga_: fpga_.registers.control.write(gbe_rst=False),))

    def initialise_pre_gbe(self):
        """
        Set up F-engines on this device. This is done after programming the
        devices in the instrument.
        :return:
        """

        if 'x_setup' in self.hosts[0].registers.names():
            self.logger.info('Found num_x independent F-engines')
            # set up the x-engine information in the F-engine hosts
            num_x_hosts = len(self.corr.xhosts)
            x_per_fpga = int(self.corr.configd['xengine']['x_per_fpga'])
            num_x = num_x_hosts * x_per_fpga
            f_per_x = self.corr.n_chans / num_x
            ip_per_x = 1.0
            THREADED_FPGA_OP(
                self.hosts, timeout=10,
                target_function=(
                    lambda fpga_:
                    fpga_.registers.x_setup.write(f_per_x=f_per_x,
                                                  ip_per_x=ip_per_x,
                                                  num_x=num_x,),))
            time.sleep(1)
        else:
            self.logger.info('Found FIXED num_x F-engines')

        # set eq and shift
        self.eq_write_all()
        self.set_fft_shift_all()

        # set up the fpga comms
        self.tx_disable()
        THREADED_FPGA_OP(
            self.hosts, timeout=10,
            target_function=(
                lambda fpga_: fpga_.registers.control.write(gbe_rst=True),))
        self.clear_status_all()

        # where does the F-engine data go?
        self.data_stream.write_destination()

        # set the sample rate on the Fhosts
        for host in self.hosts:
            host.rx_data_sample_rate_hz = self.corr.sample_rate_hz

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
                _fengd['eq_poly_%s' % stream_name])
        assert len(eq_polys) == len(dig_streams), (
            'Digitiser input names (%d) must be paired with EQ polynomials '
            '(%d).' % (len(dig_streams), len(eq_polys)))

        # assemble the inputs given into a list
        _feng_temp = []
        for stream in dig_streams:
            new_feng = fhost_fpga.Fengine(
                input_stream=self.corr.get_data_stream(stream[0]),
                host=None,
                offset=stream[1] % self.corr.f_per_fpga,
                sensor_manager=None)
            new_feng.eq_poly = eq_polys[new_feng.name]
            new_feng.eq_bram_name = 'eq%i' % new_feng.offset
            dest_ip_range = new_feng.input.destination.ip_range
            assert dest_ip_range == self.corr.ports_per_fengine, (
                'F-engines should be receiving from %d streams.' %
                self.corr.ports_per_fengine)
            _feng_temp.append(new_feng)

        # check that the inputs all have the same IP ranges
        _ip_range0 = _feng_temp[0].input.destination.ip_range
        for _feng in _feng_temp:
            _ip_range = _feng.input.destination.ip_range
            assert _ip_range == _ip_range0, (
                'All F-engines should be receiving from %d streams.' %
                self.corr.ports_per_fengine)

        # assign inputs to fhosts
        self.logger.info('Assigning Fengines to f-hosts')
        _feng_ctr = 0
        self.fengines = []
        for fhost in self.hosts:
            self.logger.info('\t%s:' % fhost.host)
            for fengnum in range(0, self.corr.f_per_fpga):
                _feng = _feng_temp[_feng_ctr]
                _feng.host = fhost
                self.fengines.append(_feng)
                fhost.add_fengine(_feng)
                self.logger.info('\t\t%s' % _feng)
                _feng_ctr += 1
        if _feng_ctr != len(self.hosts) * self.corr.f_per_fpga:
            raise RuntimeError('We have different numbers of inputs (%d) and '
                               'F-engines (%d). Problem.', _feng_ctr,
                               len(self.hosts) * self.corr.f_per_fpga)
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

    def check_rx(self, max_waittime=30):
        """
        Check that the F-engines are receiving data correctly
        :param max_waittime:
        :return:
        """
        self.logger.info('Checking F hosts are receiving data...')
        results = THREADED_FPGA_FUNC(
            self.hosts, timeout=max_waittime+1,
            target_function=('check_rx', (max_waittime,),))
        all_okay = True
        for _v in results.values():
            all_okay = all_okay and _v
        if not all_okay:
            self.logger.error('\tERROR in F-engine rx data.')
        self.logger.info('\tdone.')
        return all_okay

    def check_rx_timestamps(self):
        """
        Are the timestamps being received by the F-engines okay?
        :return: (a boolean, the F-engine times as 48-bit counts,
        their unix representations)
        """
        self.logger.info('Checking timestamps on F hosts...')
        results = THREADED_FPGA_FUNC(
            self.hosts, timeout=5,
            target_function='get_local_time')
        read_time = time.time()
        synch_epoch = self.corr.synchronisation_epoch
        if synch_epoch == -1:
            self.logger.warning('System synch epoch unset, skipping F-engine '
                                'future time test.')
        feng_times = {}
        feng_times_unix = {}
        for host in self.hosts:
            feng_mcnt = results[host.host]
            # are the count bits okay?
            if feng_mcnt & 0xfff != 0:
                errmsg = '%s: bottom 12 bits of timestamp from F-engine are ' \
                       'not zero?! feng_mcnt(%i)' % (host.host, feng_mcnt)
                self.logger.error(errmsg)
                return False, feng_times, feng_times_unix
            # compare the F-engine times to the local UNIX time
            if synch_epoch != -1:
                # is the time in the future?
                feng_time_s = feng_mcnt / self.corr.sample_rate_hz
                feng_time = synch_epoch + feng_time_s
                if feng_time > read_time:
                    errmsg = '%s: F-engine time cannot be in the future? ' \
                           'now(%.3f) feng_time(%.3f)' % (host.host, read_time,
                                                          feng_time)
                    self.logger.error(errmsg)
                    return False, feng_times, feng_times_unix
                # is the time close enough to local time?
                if abs(read_time - feng_time) > self.corr.time_offset_allowed_s:
                    errmsg = '%s: time calculated from board cannot be so ' \
                             'far from local time: now(%.3f) feng_time(%.3f) ' \
                             'diff(%.3f)' % (host.host, read_time, feng_time,
                                             read_time - feng_time)
                    self.logger.error(errmsg)
                    return False, feng_times, feng_times_unix
                feng_times_unix[host.host] = feng_time
            else:
                feng_times_unix[host.host] = -1
            feng_times[host.host] = feng_mcnt

        # are they all within 500ms of one another?
        diff = max(feng_times.values()) - min(feng_times.values())
        diff_ms = diff / self.corr.sample_rate_hz * 1000.0
        if diff_ms > self.corr.time_jitter_allowed_ms:
            errmsg = 'F-engine timestamps are too far apart: %.3fms' % diff_ms
            self.logger.error(errmsg)
            return False, feng_times, feng_times_unix
        self.logger.info('\tdone.')
        return True, feng_times, feng_times_unix

    # def delays_process(self, loadtime, delays):
    #     """
    #
    #     :param loadtime:
    #     :param delays:
    #     :return:
    #     """
    #     if loadtime <= time.time():
    #         raise ValueError('Loadtime %.3f is in the past?' % loadtime)
    #     # This was causing an error
    #     dlist = delays#.split(' ')
    #     ant_delay = []
    #     for delay in dlist:
    #         bits = delay.strip().split(':')
    #         if len(bits) != 2:
    #             raise ValueError('%s is not a valid delay setting' % delay)
    #         delay = bits[0]
    #         delay = delay.split(',')
    #         delay = (float(delay[0]), float(delay[1]))
    #         fringe = bits[1]
    #         fringe = fringe.split(',')
    #         fringe = (float(fringe[0]), float(fringe[1]))
    #         ant_delay.append((delay, fringe))
    #
    #     labels = []
    #     for feng in self.corr.fengines:
    #         labels.append(feng['input'].name)
    #     if len(ant_delay) != len(labels):
    #         raise ValueError(
    #             'Too few values provided: expected(%i) got(%i)' %
    #             (len(labels), len(ant_delay)))
    #
    #     rv = ''
    #     for ctr in range(0, len(labels)):
    #         res = self.set_delay(labels[ctr],
    #                              ant_delay[ctr][0][0], ant_delay[ctr][0][1],
    #                              ant_delay[ctr][1][0], ant_delay[ctr][1][1],
    #                              loadtime, False)
    #         res_str = '%.3f,%.3f:%.3f,%.3f' % \
    #                   (res['act_delay'], res['act_delay_delta'],
    #                    res['act_phase_offset'], res['act_phase_offset_delta'])
    #         rv = '%s %s' % (rv, res_str)
    #     return rv

    def delays_process_parallel(self, loadtime, delay_list):
        """
        Given a load time and a set of delay values, apply them to the
        F-engines in this system.
        :param loadtime:
        :param delay_list:
        :return:
        """
        if loadtime > 0:
            time_now = time.time()
            # check that load time is not too soon or in the past
            if loadtime < (time_now + self.corr.min_load_time):
                errmsg = 'Time given is in the past or does not allow for ' \
                         'enough time to set values'
                self.logger.error(errmsg)
                raise RuntimeError(errmsg)
            loadtime_mcnt = self.corr.mcnt_from_time(loadtime)
            load_wait_delay = (loadtime - time_now + self.corr.min_load_time)
            numfeng = len(self.fengines)
            if len(delay_list) != numfeng:
                errmsg = 'Too few delay setup parameters given. Need as ' \
                       'many as there are inputs (%i), given %i delay ' \
                       'settings' % (numfeng, len(delay_list))
                self.logger.error(errmsg)
                raise ValueError(errmsg)
            input_delays = delayops.process_list(delay_list)
            # set them in the objects and then write them to hardware
            actual_vals = self.set_delays_all(loadtime_mcnt, input_delays)
        else:
            actual_vals = self.get_delays_all()
        rv = []
        for val in actual_vals:
            res_str = '{},{}:{},{}'.format(
                val['act_delay'], val['act_delay_delta'],
                val['act_phase_offset'], val['act_phase_offset_delta'])
            rv.append(res_str)
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_feng_delays()
        return rv

    def set_delays_all(self, loadtime_mcnt, coefficients):
        """
        Set delays on all fhosts
        :param loadtime_mcnt: the load time, converted to system tick time
        :param coefficients: a list of coefficient tuples, one per input
        :return:
        """
        # spawn threads to write values out, giving a maximum time of 0.75
        # seconds to do them all
        target_func = ('set_and_write_delays_all',
                       [loadtime_mcnt, coefficients, self.corr.sample_rate_hz],
                       {})
        actual_vals = THREADED_FPGA_FUNC(
            self.corr.fhosts, timeout=0.5, target_function=target_func)
        return [actual_vals[feng.host.host][feng.offset]
                for feng in self.fengines]

    def get_delays_all(self):
        """
        Get delays from all fhosts
        :return:
        """
        return [
            {
                'act_delay': feng.delay_actual.delay,
                'act_delay_delta': feng.delay_actual.delay_delta,
                'act_phase_offset': feng.delay_actual.phase_offset,
                'act_phase_offset_delta': feng.delay_actual.phase_offset_delta
            } for feng in self.fengines
        ]

    def check_tx(self):
        """
        Check that the F-engines are sending data correctly
        :return:
        """
        self.logger.info('Checking F hosts are transmitting data...')
        results = THREADED_FPGA_FUNC(self.hosts, timeout=10,
                                     target_function=('check_tx_raw',
                                                      (0.2, 5), {}))
        all_okay = True
        for _v in results.values():
            all_okay = all_okay and _v
        if not all_okay:
            self.logger.error('\tERROR in F-engine tx data.')
        self.logger.info('\tdone.')
        return all_okay

    def resync_and_check(self):
        """
        Resynchronise all the f-engines and then check if they still have RX
        or TX errors.
        :return:
        """
        attempts = 5
        self.logger.info('Attempting to resync the f-engines:')
        while attempts > 0:
            logstr = '\tattempt 1: '
            self.sys_reset()
            if self.check_rx():
                if self.check_tx():
                    self.logger.info(logstr + 'succeeded')
                    return True
            self.logger.info(logstr + 'failed')
            attempts -= 1
        return False

    def tx_enable(self):
        """
        Enable TX on all tengbe cores on all F hosts
        :return:
        """
        self.data_stream.tx_enable()

    def tx_disable(self):
        """
        Disable TX on all tengbe cores on all F hosts
        :return:
        """
        self.data_stream.tx_disable()

    def get_fengine(self, input_name):
        """

        :param input_name:
        :return:
        """
        for feng in self.fengines:
            if input_name == feng.name:
                return feng
        raise ValueError('Could not find F-engine with input %s' % input_name)

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
            for feng, new_eq in new_eq_dict.iteritems():
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
            rv = ['feng{0}'.format(feng.input_number)
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
        Subscribe all F-engine data inputs to their multicast data
        :return:
        """
        self.logger.info('Subscribing F-engine inputs...')
        for fhost in self.hosts:
            self.logger.info('\t%s:' % fhost.host)

            # andrew's ar1.5 changes
            if 'rx_dest_ip_mask0' in fhost.registers._items:
                destination = fhost.fengines[0].input.destination    
                base = int(destination.ip_address)
                fhost.registers.rx_dest_ip0.write_int(base)

                mask = (255 << 24) + (255 << 16) + (255 << 8) + (256 - destination.ip_range)
                fhost.registers.rx_dest_ip_mask0.write_int(mask)
            
            if 'rx_dest_ip_mask1' in fhost.registers._items:
                destination = fhost.fengines[1].input.destination    
                base = int(destination.ip_address)
                fhost.registers.rx_dest_ip1.write_int(base)

                mask = (255 << 24) + (255 << 16) + (255 << 8) + (256 - destination.ip_range)
                fhost.registers.rx_dest_ip_mask1.write_int(mask)

            gbe_ctr = 0
            for feng in fhost.fengines:
                input_addr = feng.input.destination
                if not input_addr.is_multicast():
                    self.logger.info('\t\tsource address %s is not '
                                     'multicast?' % input_addr.ip_address)
                else:
                    rxaddr = str(input_addr.ip_address)
                    rxaddr_bits = rxaddr.split('.')
                    rxaddr_base = int(rxaddr_bits[3])
                    rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0],
                                                   rxaddr_bits[1],
                                                   rxaddr_bits[2])
                    if ((len(fhost.tengbes) / self.corr.f_per_fpga) !=
                            input_addr.ip_range):
                        raise RuntimeError(
                            '10Gbe ports (%d) do not match sources IPs (%d)' %
                            (len(fhost.tengbes), input_addr.ip_range))
                    for ctr in range(0, input_addr.ip_range):
                        gbename = fhost.tengbes.names()[gbe_ctr]
                        gbe = fhost.tengbes[gbename]
                        rxaddress = '%s%d' % (rxaddr_prefix, rxaddr_base + ctr)
                        self.logger.info('\t\t%s subscribing to '
                                         'address %s' % (gbe.name, rxaddress))
                        gbe.multicast_receive(rxaddress, 0)
                        gbe_ctr += 1
        self.logger.info('done.')

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

    def _get_adc_snapshot_compat(self, input_name):
        """

        :return:
        """
        if input_name is None:
            res = THREADED_FPGA_FUNC(
                self.hosts, timeout=10,
                target_function=('get_adc_snapshots', [], {}))
            rv = {}
            for feng in self.fengines:
                rv[feng.name] = res[feng.host.host]['p%i' % feng.offset]
            return rv
        else:
            # return the data only for one given input
            try:
                feng = self.get_fengine(input_name)
                d = feng.host.get_adc_snapshots()
                return {input_name: d['p%i' % feng.offset]}
            except ValueError:
                pass
            raise ValueError(
                'Could not find input %s anywhere. Available inputs: %s' % (
                    input_name, self.corr.get_input_labels()))

    def get_adc_snapshot(self, input_name=None, unix_time=-1):
        """
        Read the small voltage buffer for a input from a host.
        :param input_name: the input name, if None, will return all inputs
        :param unix_time: the time at which to read
        :return: {feng_name0: AdcData(),
                  feng_name1: AdcData(),
                 }
        """
        # check for compatibility for really old f-engines
        ctrl_reg = self.hosts[0].registers.control
        old_fengines = 'adc_snap_trig_select' not in ctrl_reg.field_names()
        if old_fengines:
            if unix_time == -1:
                self.logger.warning('REALLY OLD F-ENGINES ENCOUNTERED, USING '
                                    'IMMEDIATE ADC SNAPSHOTS')
                return self._get_adc_snapshot_compat(input_name)
            else:
                raise RuntimeError('Timed ADC snapshots are not supported by '
                                   'the F-engine hardware. Please try again '
                                   'without specifying the snapshot trigger '
                                   'time.')
        if input_name is None:
            # get data for all F-engines triggered at the same time
            localtime = self.hosts[0].get_local_time()
            _sample_rate = self.hosts[0].rx_data_sample_rate_hz
            if unix_time == -1:
                timediff = 2
            else:
                timediff = unix_time - time.time()
            timediff_samples = (timediff * 1.0) * _sample_rate
            loadtime = int(localtime + timediff_samples)
            loadtime += 2**12
            loadtime = (loadtime >> 12) << 12
            res = THREADED_FPGA_FUNC(
                self.hosts, timeout=10,
                target_function=('get_adc_snapshots_timed', [],
                                 {'loadtime_system': loadtime,
                                  'localtime': localtime}))
            rv = {}
            for feng in self.fengines:
                rv[feng.name] = res[feng.host.host]['p%i' % feng.offset]
            return rv
        else:
            # return the data only for one given input
            rv = None
            for host in self.hosts:
                try:
                    rv = host.get_adc_snapshot_for_input(
                        input_name, unix_time)
                    break
                except ValueError:
                    pass
            if rv is None:
                raise ValueError(
                    'Could not find input %s anywhere. Available inputs: %s' % (
                        input_name, self.corr.get_input_labels()))
            return {input_name: rv}

    def check_qdr_devices(self):
        """
        Are the QDR devices behaving?
        :return:
        """
        res = THREADED_FPGA_FUNC(
            self.hosts, 5,
            ('check_qdr_devices', [self.corr.qdr_ct_error_threshold], {}))
        for host, result in res.items():
            if not result:
                return False
        return True
