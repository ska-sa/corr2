import numpy
import time

from casperfpga import utils as fpgautils

from data_source import DataSource
import utils

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


class FEngineOperations(object):

    def __init__(self, corr_obj):
        """
        A collection of f-engine operations that act on/with a
        correlator instance.
        :param corr_obj:
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.fhosts
        self.logger = corr_obj.logger
        # do config things

    def initialise_post_gbe(self):
        """
        Perform post-gbe setup initialisation steps
        :return:
        """
        # write the board IDs to the fhosts
        board_id = 0
        for f in self.hosts:
            f.registers.tx_metadata.write(board_id=board_id,
                                          porttx=self.corr.fengine_output.port)
            board_id += 1

        # release from reset
        THREADED_FPGA_OP(self.hosts, timeout=10, target_function=(
            lambda fpga_: fpga_.registers.control.write(gbe_rst=False),))

    def initialise_pre_gbe(self):
        """
        Set up f-engines on this device. This is done after programming the
        devices in the instrument.
        :return:
        """

        if 'x_setup' in self.hosts[0].registers.names():
            self.logger.info('Found num_x independent f-engines')
            # set up the x-engine information in the f-engine hosts
            num_x_hosts = len(self.corr.xhosts)
            num_x = num_x_hosts * int(self.corr.configd['xengine']['x_per_fpga'])
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
            self.logger.info('Found FIXED num_x f-engines')

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

        # where does the f-engine data go?
        self.corr.fengine_output = DataSource.from_mcast_string(
            self.corr.configd['fengine']['destination_mcast_ips'])
        self.corr.fengine_output.name = 'fengine_destination'
        fdest_ip = int(self.corr.fengine_output.ip_address)
        THREADED_FPGA_OP(self.hosts, timeout=5, target_function=(
            lambda fpga_: fpga_.registers.iptx_base.write_int(fdest_ip),))

        # set the sample rate on the Fhosts
        for host in self.hosts:
            host.rx_data_sample_rate_hz = self.corr.sample_rate_hz

    def configure(self):
        """
        Configure the fengine operations - this is done whenever a correlator
        is instantiated.
        :return:
        """
        return

    def sys_reset(self, sleeptime=0):
        """
        Pulse the sys_rst line on all F-engine hosts
        :param sleeptime:
        :return:
        """
        self.logger.info('Forcing an f-engine resync')
        THREADED_FPGA_OP(self.hosts, timeout=5, target_function=(
            lambda fpga_: fpga_.registers.control.write(sys_rst='pulse'),))
        if sleeptime > 0:
            time.sleep(sleeptime)

    def check_rx(self, max_waittime=30):
        """
        Check that the f-engines are receiving data correctly
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
        Are the timestamps being received by the f-engines okay?
        :return: (a boolean, the f-engine times as 48-bit counts,
        their unix representations)
        """
        self.logger.info('Checking timestamps on F hosts...')
        results = THREADED_FPGA_FUNC(
            self.hosts, timeout=5,
            target_function='get_local_time')
        read_time = time.time()
        synch_epoch = self.corr.get_synch_time()
        if synch_epoch == -1:
            self.logger.warning('System synch epoch unset, skipping f-engine '
                                'future time test.')
        feng_times = {}
        feng_times_unix = {}
        for host in self.hosts:
            feng_mcnt = results[host.host]
            # are the count bits okay?
            if feng_mcnt & 0xfff != 0:
                _err = '%s: bottom 12 bits of timestamp from f-engine are ' \
                       'not zero?! feng_mcnt(%i)' % (host.host, feng_mcnt)
                self.logger.error(_err)
                return False, feng_times, feng_times_unix
            # compare the f-engine times to the local UNIX time
            if synch_epoch != -1:
                # is the time in the future?
                feng_time_s = feng_mcnt / float(self.corr.sample_rate_hz)
                feng_time = synch_epoch + feng_time_s
                if feng_time > read_time:
                    _err = '%s: f-engine time cannot be in the future? ' \
                           'now(%.3f) feng_time(%.3f)' % (host.host, read_time,
                                                          feng_time)
                    self.logger.error(_err)
                    return False, feng_times, feng_times_unix
                # is the time close enough to local time?
                if abs(read_time - feng_time) > self.corr.time_offset_allowed_s:
                    _err = '%s: time calculated from board cannot be so far ' \
                           'from local time: now(%.3f) feng_time(%.3f) ' \
                           'diff(%.3f)' % (host.host, read_time, feng_time,
                                           read_time - feng_time)
                    self.logger.error(_err)
                    return False, feng_times, feng_times_unix
                feng_times_unix[host.host] = feng_time
            else:
                feng_times_unix[host.host] = -1
            feng_times[host.host] = feng_mcnt

        # are they all within 500ms of one another?
        diff = max(feng_times.values()) - min(feng_times.values())
        diff_ms = diff / float(self.corr.sample_rate_hz) * 1000.0
        if diff_ms > self.corr.time_jitter_allowed_ms:
            _err = 'F-engine timestamps are too far apart: %.3fms' % diff_ms
            self.logger.error(_err)
            return False, feng_times, feng_times_unix
        self.logger.info('\tdone.')
        return True, feng_times, feng_times_unix

    def _prepare_delay_vals(self, delay=0, delta_delay=0, phase_offset=0,
                            delta_phase_offset=0, ld_time=None, ld_check=True):
        # convert delay in time into delay in clock cycles
        delay_s = float(delay) * self.corr.sample_rate_hz

        # convert to fractions of a sample
        phase_offset_s = float(phase_offset)/float(numpy.pi)

        # convert from radians per second to fractions of sample per sample
        delta_phase_offset_s = (float(delta_phase_offset) / float(numpy.pi) /
                                self.corr.sample_rate_hz)

        if ld_time is not None:
            # check that load time is not too soon or in the past
            if ld_time < (time.time() + self.corr.min_load_time):
                self.logger.error('Time given is in the past or does not allow '
                                  'for enough time to set values')
        
        ld_time_mcnt = None
        if ld_time is not None:
            ld_time_mcnt = self.corr.mcnt_from_time(ld_time)

        # calculate time to wait for load
        load_wait_delay = None
        if ld_check:
            if ld_time is not None:
                load_wait_delay = (ld_time - time.time() +
                                   self.corr.min_load_time)

        return {'delay': delay_s, 'delta_delay': delta_delay,
                'phase_offset': phase_offset_s,
                'delta_phase_offset': delta_phase_offset_s,
                'load_time': ld_time_mcnt,
                'load_wait': load_wait_delay}

    def _prepare_actual_delay_vals(self, actual_vals):
        return {
            'act_delay': actual_vals['act_delay'] / self.corr.sample_rate_hz,
            'act_delta_delay': actual_vals['act_delta_delay'],
            'act_phase_offset': actual_vals['act_phase_offset']*numpy.pi,
            'act_delta_phase_offset': actual_vals['act_delta_phase_offset'] *
                                      numpy.pi * self.corr.sample_rate_hz
        }

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
    #     for src in self.corr.fengine_sources:
    #         labels.append(src['source'].name)
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
    #                   (res['act_delay'], res['act_delta_delay'],
    #                    res['act_phase_offset'], res['act_delta_phase_offset'])
    #         rv = '%s %s' % (rv, res_str)
    #     return rv

    def delays_process_parallel(self, loadtime, delays):
        """

        :param loadtime:
        :param delays:
        :return:
        """
        if loadtime <= time.time():
            _err = 'Loadtime %.3f is in the past?' % loadtime
            self.logger.error(_err)
            raise ValueError(_err)

        dlist = delays
        _n_fsource = len(self.corr.fengine_sources)
        if len(dlist) != _n_fsource:
            _err = 'Too few delay setup parameters given. Need as' \
                   ' many as there are f-sources = %i' % _n_fsource
            self.logger.error(_err)
            raise ValueError(_err)

        ant_delay = []
        for delay in dlist:
            bits = delay.strip().split(':')
            if len(bits) != 2:
                _err = '%s is not a valid delay setting' % delay
                self.logger.error(_err)
                raise ValueError(_err)
            delay = bits[0]
            delay = delay.split(',')
            delay = (float(delay[0]), float(delay[1]))
            fringe = bits[1]
            fringe = fringe.split(',')
            fringe = (float(fringe[0]), float(fringe[1]))
            ant_delay.append((delay, fringe))

        actual_vals = self.set_delays_all(loadtime, ant_delay)
        rv = []
        for val in actual_vals:
            res_str = '{},{}:{},{}'.format(
                val['act_delay'], val['act_delta_delay'],
                val['act_phase_offset'], val['act_delta_phase_offset'])
            rv.append(res_str)
        return rv
    
    def set_delays_all(self, loadtime, coeffs):
        """
        Set delays on all fhosts
        :param loadtime:
        :param coeffs:
        :return:
        """
        for count, src in enumerate(self.corr.fengine_sources):
            vals = self._prepare_delay_vals(coeffs[count][0][0], 
                                            coeffs[count][0][1],
                                            coeffs[count][1][0],
                                            coeffs[count][1][1],
                                            loadtime, False)
            host = src['host']
            offset = src['numonhost']
            host.set_delay(offset, vals['delay'], vals['delta_delay'],
                           vals['phase_offset'], vals['delta_phase_offset'],
                           vals['load_time'], None, False)

        # spawn threads to write values out, giving a maximum time of 0.75
        # seconds to do them all
        actual_vals = THREADED_FPGA_FUNC(self.corr.fhosts, timeout=0.75,
                                         target_function='write_delays_all')
        if len(actual_vals) != len(self.corr.fhosts):
            _err = 'Number of delay values returned (%i) does not match ' \
                   'number of sources (%i)' % \
                   (len(actual_vals), len(self.corr.fhosts))
            self.logger.error(_err)
            raise ValueError(_err)

        act_vals = []
        for count, src in enumerate(self.corr.fengine_sources):
            host = src['host'].host
            offset = src['numonhost']
            vals = self._prepare_actual_delay_vals(actual_vals[host][offset])
            act_vals.append(vals)
            self.logger.info(
                '[%s] Phase offset actually set to %6.3f rad with rate %e '
                'rad/s.' %
                (src['source'].name,
                 actual_vals[host][offset]['act_phase_offset'],
                 actual_vals[host][offset]['act_delta_phase_offset']))
            self.logger.info(
                '[%s] Delay actually set to %e samples with rate %e.' %
                (src['source'].name,
                 actual_vals[host][offset]['act_delay'],
                 actual_vals[host][offset]['act_delta_delay']))
        return act_vals

    # def set_delay(self, source_name, delay=0, delta_delay=0, phase_offset=0,
    #               delta_phase_offset=0, ld_time=None, ld_check=True):
    #     """
    #     Set delay correction values for specified source.
    #     This is a blocking call.
    #     By default, it will wait until load time and verify that things
    #     worked as expected.
    #     This check can be disabled by setting ld_check param to False.
    #     Load time is optional; if not specified, load immediately.
    #     :return
    #     """
    #     self.logger.info('Setting delay correction values for '
    #                      'source %s' % source_name)
    #
    #     vals = self._prepare_delay_vals(delay, delta_delay, phase_offset, delta_phase_offset,
    #                                 ld_time, ld_check)
    #     f_delay = vals['delay']
    #     f_delta_delay = vals['delta_delay']
    #     f_phase_offset = vals['phase_offset']
    #     f_delta_phase_offset = vals['delta_phase_offset']
    #     f_load_time = vals['load_time']
    #     f_load_wait = vals['load_wait']
    #
    #     # determine fhost to write to
    #     write_hosts = []
    #     for src in self.corr.fengine_sources:
    #         if source_name in src['source'].name:
    #             offset = src['numonhost']
    #             write_hosts.append(src['host'])
    #     if len(write_hosts) == 0:
    #         raise ValueError('Unknown source name %s' % source_name)
    #     elif len(write_hosts) > 1:
    #         raise RuntimeError('Found more than one fhost handling source {!r}: {}'
    #             .format(source_name, [h.host for h in write_hosts]))
    #
    #     fhost = write_hosts[0]
    #     try:
    #         actual_vals = fhost.write_delay(
    #             offset,
    #             f_delay, f_delta_delay,
    #             f_phase_offset, f_delta_phase_offset,
    #             f_load_time, f_load_wait, ld_check)
    #     except Exception as e:
    #         self.logger.error('New delay error - %s' % e.message)
    #         raise
    #
    #     actual_values = self._prepare_actual_delay_vals(actual_vals)
    #
    #     self.logger.info(
    #         'Phase offset actually set to %6.3f radians.' %
    #         (actual_values['act_phase_offset']))
    #     self.logger.info(
    #         'Phase offset change actually set to %e radians per second.' %
    #         (actual_values['act_delta_phase_offset']))
    #     self.logger.info(
    #         'Delay actually set to %e samples.' %
    #         (actual_values['act_delay']))
    #     self.logger.info(
    #         'Delay rate actually set to %e seconds per second.' %
    #         (actual_values['act_delta_delay']))
    #
    #     return actual_values

    def check_tx(self):
        """
        Check that the f-engines are sending data correctly
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

    def tx_enable(self):
        """
        Enable TX on all tengbe cores on all F hosts
        :return:
        """
        THREADED_FPGA_OP(
            self.hosts, 5,
            (lambda fpga_: fpga_.registers.control.write(gbe_txen=True),))

    def tx_disable(self):
        """
        Disable TX on all tengbe cores on all F hosts
        :return:
        """
        THREADED_FPGA_OP(
            self.hosts, 5,
            (lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))

    def eq_get(self, source_name=None):
        """
        Return the EQ arrays in a dictionary, arranged by source name.
        :return:
        """
        eq_table = {}
        for fhost in self.hosts:
            eq_table.update(fhost.eqs)
            if source_name is not None and source_name in eq_table:
                return {source_name: eq_table[source_name]}
        return eq_table

    def eq_set(self, write=True, source_name=None, new_eq=None):
        """
        Set the EQ for a specific source
        :param write: should the value be written to BRAM on the device?
        :param source_name: the source name
        :param new_eq: an eq list or value or poly
        :return:
        """
        if new_eq is None:
            raise ValueError('New EQ of nothing makes no sense.')
        # if no source is given, apply the new eq to all sources
        if source_name is None:
            self.logger.info('Setting EQ on all sources to new given EQ.')
            for fhost in self.hosts:
                for src_nm in fhost.eqs:
                    self.eq_set(write=False, source_name=src_nm, new_eq=new_eq)
            if write:
                self.eq_write_all()
        else:
            for fhost in self.hosts:
                if source_name in fhost.eqs:
                    old_eq = fhost.eqs[source_name]['eq'][:]
                    try:
                        neweq = utils.process_new_eq(new_eq)
                        fhost.eqs[source_name]['eq'] = neweq
                        self.logger.info(
                            'Updated EQ value for source %s: %s...' % (
                                source_name, neweq[0:min(10, len(neweq))]))
                        if write:
                            fhost.write_eq(eq_name=source_name)
                    except Exception as e:
                        fhost.eqs[source_name]['eq'] = old_eq[:]
                        self.logger.error('New EQ error - REVERTED to '
                                          'old value! - %s' % e.message)
                        raise ValueError('New EQ error - REVERTED to '
                                         'old value! - %s' % e.message)
                    return
            raise ValueError('Unknown source name %s' % source_name)

    def eq_write_all(self, new_eq_dict=None):
        """
        Set the EQ gain for given sources and write the changes to memory.
        :param new_eq_dict: a dictionary of new eq values to store
        :return:
        """
        if new_eq_dict is not None:
            self.logger.info('Updating some EQ values before writing.')
            for src, new_eq in new_eq_dict:
                self.eq_set(write=False, source_name=src, new_eq=new_eq)
        self.logger.info('Writing EQ on all fhosts based on stored '
                         'per-source EQ values...')
        THREADED_FPGA_FUNC(self.hosts, 10, 'write_eq_all')
        self.corr.speadops.update_metadata([0x1400])
        self.logger.info('done.')

    def set_fft_shift_all(self, shift_value=None):
        """
        Set the FFT shift on all boards.
        :param shift_value:
        :return:
        """
        if shift_value is None:
            shift_value = int(self.corr.configd['fengine']['fft_shift'])
        if shift_value < 0:
            raise RuntimeError('Shift value cannot be less than zero')
        self.logger.info('Setting FFT shift to %i on all f-engine '
                         'boards...' % shift_value)
        THREADED_FPGA_FUNC(self.hosts, 10, ('set_fft_shift', (shift_value,),))
        self.logger.info('done.')
        self.corr.speadops.update_metadata([0x101e])
        return shift_value

    def get_fft_shift_all(self):
        """
        Get the FFT shift value on all boards.
        :return:
        """
        # get the fft shift values
        return THREADED_FPGA_FUNC(self.hosts, 10, 'get_fft_shift')

    def clear_status_all(self):
        """
        Clear the various status registers and counters on all the fengines
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, 10, 'clear_status')

    def subscribe_to_multicast(self):
        """
        Subscribe all f-engine data sources to their multicast data
        :return:
        """
        self.logger.info('Subscribing f-engine datasources...')
        for fhost in self.hosts:
            self.logger.info('\t%s:' % fhost.host)
            gbe_ctr = 0
            for source in fhost.data_sources:
                if not source.is_multicast():
                    self.logger.info('\t\tsource address %s is not '
                                     'multicast?' % source.ip_address)
                else:
                    rxaddr = str(source.ip_address)
                    rxaddr_bits = rxaddr.split('.')
                    rxaddr_base = int(rxaddr_bits[3])
                    rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0],
                                                   rxaddr_bits[1],
                                                   rxaddr_bits[2])
                    if (len(fhost.tengbes) / self.corr.f_per_fpga) != source.ip_range:
                        raise RuntimeError(
                            '10Gbe ports (%d) do not match sources IPs (%d)' %
                            (len(fhost.tengbes), source.ip_range))
                    for ctr in range(0, source.ip_range):
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

    def get_quant_snap(self, source_name):
        """
        Get the quantiser snapshot for this source_name
        :param source_name:
        :return:
        """
        for host in self.hosts:
            try:
                return host.get_quant_snapshot(source_name)
            except ValueError:
                pass
        raise ValueError('Could not find source %s anywhere.' % source_name)

    def get_adc_snapshot(self, source_name, unix_time=-1):
        """
        Read the small voltage buffer for a source from a host.
        :param source_name: the source name
        :param unix_time: the time at which to read
        :return:
        """
        if unix_time == -1:
                unix_time = time.time() + 1
        for host in self.hosts:
            try:
                return host.get_adc_snapshot_for_source(source_name, unix_time)
            except ValueError:
                pass
        raise ValueError('Could not find source %s anywhere.' % source_name)
