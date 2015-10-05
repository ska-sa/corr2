import numpy
import spead64_48 as spead
from casperfpga import utils as fpgautils
from casperfpga import tengbe

from data_source import DataSource
import utils
import time

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


class FEngineOperations(object):

    def __init__(self, corr_obj):
        """
        A collection of f-engine operations that act on/with a correlator instance.
        :param corr_obj:
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.fhosts
        self.logger = corr_obj.logger
        # do config things

    def initialise(self):
        """
        Set up f-engines on this device.
        :return:
        """
        # set eq and shift
        self.eq_write_all()
        self.set_fft_shift_all()

        # set up the fpga comms
        THREADED_FPGA_OP(self.hosts, timeout=10,
                         target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))
        THREADED_FPGA_OP(self.hosts, timeout=10,
                         target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=True),))
        self.clear_status_all()

        # where does the f-engine data go?
        self.corr.fengine_output = DataSource.from_mcast_string(
            self.corr.configd['fengine']['destination_mcast_ips'])
        self.corr.fengine_output.name = 'fengine_destination'
        fdest_ip = int(self.corr.fengine_output.ip_address)
        THREADED_FPGA_OP(self.hosts, timeout=5, target_function=(
            lambda fpga_: fpga_.registers.iptx_base.write_int(fdest_ip),) )

        # set up the 10gbe cores
        feng_port = int(self.corr.configd['fengine']['10gbe_port'])
        mac_start = tengbe.Mac(self.corr.configd['fengine']['10gbe_start_mac'])

        # set up shared board info
        boards_info = {}
        board_id = 0
        mac = int(mac_start)
        for f in self.hosts:
            macs = []
            for gbe in f.tengbes:
                macs.append(mac)
                mac += 1
            boards_info[f.host] = board_id, macs
            board_id += 1

        def setup_gbes(f):
            board_id, macs = boards_info[f.host]
            f.registers.tx_metadata.write(board_id=board_id,
                                          porttx=self.corr.fengine_output.port)
            mac_ctr = 1
            for gbe, this_mac in zip(f.tengbes, macs):
                this_mac = tengbe.Mac.from_roach_hostname(f.host, mac_ctr)
                gbe.setup(mac=this_mac, ipaddress='0.0.0.0', port=feng_port)
                self.logger.info(
                    'fhost(%s) gbe(%s) mac(%s) port(%i) board_id(%i) tx(%s:%i)' %
                    (f.host, gbe.name, str(gbe.mac), feng_port, board_id,
                     self.corr.fengine_output.ip_address, self.corr.fengine_output.port))
                # gbe.tap_start(restart=True)
                gbe.dhcp_start()
                mac_ctr += 1

        timeout = len(self.hosts[0].tengbes) * 30 * 1.1
        THREADED_FPGA_OP(self.hosts, timeout=timeout, target_function=(setup_gbes,))

        # release from reset
        THREADED_FPGA_OP(self.hosts, timeout=5, target_function=(
            lambda fpga_: fpga_.registers.control.write(gbe_rst=False),))

    def sys_reset(self, sleeptime=0):
        """
        Pulse the sys_rst line on all F-engine hosts
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
        results = THREADED_FPGA_FUNC(self.hosts, timeout=max_waittime+1,
                                     target_function=('check_rx', (max_waittime,),))
        all_okay = True
        for _v in results.values():
            all_okay = all_okay and _v
        if not all_okay:
            self.logger.error('\tERROR in F-engine rx data.')
        self.logger.info('\tdone.')
        return all_okay

    def set_delay(self, source_name, delay=0, delta_delay=0, phase_offset=0,
                       delta_phase_offset=0, ld_time=None, ld_check=True):
        """
        Set delay correction values for specified source. This is a blocking call.
        By default,
        it will wait until load time and verify that things worked as expected.
        This check can be disabled by setting ld_check param to False.
        Load time is optional; if not specified, load immediately.
        :return
        """
        self.logger.info('Setting delay correction values for source '
                         '%s' % source_name)

        # convert delay in time into delay in samples
        delay_s = float(delay) * self.corr.sample_rate_hz  # delay in clock cycles

        feng_clk = self.corr.sample_rate_hz / self.corr.adc_demux_factor
        # convert from cycles per second to cycles per feng fpga clock
        delta_phase_offset_s = float(delta_phase_offset) / feng_clk

        ld_time_mcnt = None
        if ld_time is not None:
            if ld_time < (time.time() + self.corr.min_load_time):
                self.logger.error(
                    'Time given is in the past or does not allow for enough time '
                    'to set values')
                raise RuntimeError('Time given is in the past or does not allow '
                                   'for enough time to set values')
            ld_time_mcnt = self.corr.mcnt_from_time(ld_time)

        # calculate time to wait for load
        load_wait_delay = None
        if ld_check:
            if ld_time is not None:
                load_wait_delay = (ld_time - time.time()) + self.corr.min_load_time

        # determine fhost to write to
        for fhost in self.hosts:
            if source_name in fhost.delays.keys():
                try:
                    actual_values = (
                        fhost.write_delay(source_name, delay_s, delta_delay,
                                          phase_offset, delta_phase_offset_s,
                                          ld_time_mcnt, load_wait_delay))

                    self.logger.info('Phase offset actually set to %6.3f degrees.' %
                                          actual_values['act_phase_offset'])
                    self.logger.info('Phase offset change actually set to %e Hz.' %
                                          (actual_values['act_delta_phase_offset']*feng_clk))
                    self.logger.info('Delay actually set to %e samples.' %
                                          actual_values['act_delay'])
                    self.logger.info('Delay rate actually set to %e seconds per second.' %
                                          actual_values['act_delta_delay'])
                except Exception as e:
                    self.logger.error('New delay error - %s' % e.message)
                    raise ValueError('New delay error - %s' % e.message)
            self.logger.info('done.')
            return
        raise ValueError('Unknown source name %s' % source_name)

    def check_tx(self):
        """
        Check that the f-engines are sending data correctly
        :return:
        """
        self.logger.info('Checking F hosts are transmitting data...')
        results = THREADED_FPGA_FUNC(self.hosts, timeout=5,
                                     target_function='check_tx_raw')
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
        THREADED_FPGA_OP(self.hosts, timeout=5,
                         target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=True),))

    def tx_disable(self):
        """
        Disable TX on all tengbe cores on all F hosts
        :return:
        """
        THREADED_FPGA_OP(self.hosts, timeout=5,
                         target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))

    def eq_get(self, source_name=None):
        """
        Return the EQ arrays in a dictionary, arranged by source name.
        :return:
        """
        eq_table = {}
        for fhost in self.hosts:
            eq_table.update(fhost.eqs)
            if source_name is not None and source_name in eq_table.keys():
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
                for src_nm in fhost.eqs.keys():
                    self.eq_set(write=False, source_name=src_nm, new_eq=new_eq)
            if write:
                self.eq_write_all()
        else:
            for fhost in self.hosts:
                if source_name in fhost.eqs.keys():
                    old_eq = fhost.eqs[source_name]['eq'][:]
                    try:
                        neweq = utils.process_new_eq(new_eq)
                        fhost.eqs[source_name]['eq'] = neweq
                        self.logger.info('Updated EQ value for source %s: %s...' %
                                         (source_name, neweq[0:min(10, len(neweq))]))
                        if write:
                            fhost.write_eq(eq_name=source_name)
                    except Exception as e:
                        fhost.eqs[source_name]['eq'] = old_eq[:]
                        self.logger.error('New EQ error - REVERTED to old value! - %s' % e.message)
                        raise ValueError('New EQ error - REVERTED to old value! - %s' % e.message)
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
        self.logger.info('Writing EQ on all fhosts based on stored per-source EQ values...')
        THREADED_FPGA_FUNC(self.hosts, timeout=10, target_function='write_eq_all')
        if self.corr.spead_meta_ig is not None:
            self.eq_update_metadata()
            self.corr.spead_tx.send_heap(self.corr.spead_meta_ig.get_heap())
        self.logger.info('done.')

    def eq_update_metadata(self):
        """
        Update the EQ metadata for this correlator.
        :return:
        """
        all_eqs = self.eq_get()
        for source_ctr, source in enumerate(self.corr.fengine_sources):
            eqlen = len(all_eqs[source.name]['eq'])
            self.corr.spead_meta_ig.add_item(name='eq_coef_%s' % source.name,
                                             id=0x1400 + source_ctr,
                                             description='The unitless per-channel digital scaling '
                                                         'factors implemented prior to requantisation, '
                                                         'post-FFT, for input %s. Complex number '
                                                         'real,imag 32 bit integers.' % source.name,
                                             shape=[eqlen, 2],
                                             fmt=spead.mkfmt(('u', 32)),
                                             init_val=[[numpy.real(eq_coeff), numpy.imag(eq_coeff)]
                                                       for eq_coeff in all_eqs[source.name]['eq']])

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
        self.logger.info('Setting FFT shift to %i on all f-engine boards...' % shift_value)
        THREADED_FPGA_FUNC(self.hosts, timeout=10,
                           target_function=('set_fft_shift', (shift_value,),))
        self.logger.info('done.')
        if self.corr.spead_meta_ig is not None:
            self.corr.spead_meta_ig['fft_shift'] = int(self.corr.configd['fengine']['fft_shift'])
            self.corr.spead_tx.send_heap(self.corr.spead_meta_ig.get_heap())
        return shift_value

    def get_fft_shift_all(self):
        """
        Get the FFT shift value on all boards.
        :return:
        """
        # get the fft shift values
        return THREADED_FPGA_FUNC(self.hosts, timeout=10, target_function='get_fft_shift')

    def clear_status_all(self):
        """
        Clear the various status registers and counters on all the fengines
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, timeout=10, target_function='clear_status')

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
                    self.logger.info('\t\tsource address %s is not multicast?' % source.ip_address)
                else:
                    rxaddr = str(source.ip_address)
                    rxaddr_bits = rxaddr.split('.')
                    rxaddr_base = int(rxaddr_bits[3])
                    rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0], rxaddr_bits[1], rxaddr_bits[2])
                    if (len(fhost.tengbes) / self.corr.f_per_fpga) != source.ip_range:
                        raise RuntimeError(
                            '10Gbe ports (%d) do not match sources IPs (%d)' %
                            (len(fhost.tengbes), source.ip_range))
                    for ctr in range(0, source.ip_range):
                        gbename = fhost.tengbes.names()[gbe_ctr]
                        gbe = fhost.tengbes[gbename]
                        rxaddress = '%s%d' % (rxaddr_prefix, rxaddr_base + ctr)
                        self.logger.info('\t\t%s subscribing to address %s' % (gbe.name, rxaddress))
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
