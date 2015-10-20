import time
import numpy
from tornado.ioloop import IOLoop

from casperfpga import utils as fpgautils
from casperfpga import tengbe

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

use_xeng_sim = False


class XEngineOperations(object):

    def __init__(self, corr_obj):
        """
        A collection of x-engine operations that act on/with a correlator instance.
        :param corr_obj:
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.xhosts
        self.logger = corr_obj.logger
        # do config things
        self.xengines_per_xhost = int(self.corr.configd['xengine']['x_per_fpga'])
        self.channels_per_xhost = self.corr.n_chans / len(self.hosts)
        self.channels_per_xengine = self.channels_per_xhost / self.xengines_per_xhost

    def _vacc_periodic_check(self, old_data, check_time):

        self.logger.debug('Checking VACC operation at %.3f' % time.time())
        last_data = old_data
    
        def get_data():
            """
            Get the relevant data from the X-engine FPGAs
            """
            def get_reorder_data(fpga):
                rv = {}
                for _ctr in range(0, fpga.x_per_fpga):
                    _reg = fpga.registers['reorderr_timeout%i' % _ctr]
                    rv['etim%i' % _ctr] = _reg.read()['data']['reg']
                return rv
            reo_data = THREADED_FPGA_OP(self.hosts, timeout=5,
                                        target_function=get_reorder_data)
            vacc_data = self.vacc_status()
            return {'reorder': reo_data, 'vacc': vacc_data}
    
        def _vacc_data_check(d0, d1):
            # check errors are not incrementing
            for host in self.hosts:
                for xeng in range(0, host.x_per_fpga):
                    status0 = d0[host.host][xeng]
                    status1 = d1[host.host][xeng]
                    if ((status1['errors'] > status0['errors']) or
                            (status0['errors'] != 0)):
                        self.logger.error('\tVACC %i on %s has '
                                          'errors' % (xeng, host.host))
                        return False
            # check that the accumulations are ticking over
            for host in self.hosts:
                for xeng in range(0, host.x_per_fpga):
                    status0 = d0[host.host][xeng]
                    status1 = d1[host.host][xeng]
                    if status1['count'] == status0['count']:
                        self.logger.error('\tVACC %i on %s is not '
                                          'incrementing' % (xeng, host.host))
                        return False
            return True
    
        def _reorder_data_check(d0, d1):
            for host in self.hosts:
                for ctr in range(0, host.x_per_fpga):
                    reg = 'etim%i' % ctr
                    if d0[host.host][reg] != d1[host.host][reg]:
                        self.logger.error('\t%s - vacc check reorder '
                                          'reg %s error' % (host.host, reg))
                        return False
            return True
    
        new_data = get_data()
        # self.logger.info('new_data: %s' % new_data)
    
        if last_data is not None:
            force_sync = False
            # check the vacc status data first
            if not _vacc_data_check(last_data['vacc'], new_data['vacc']):
                force_sync = True
            # check the reorder data
            if not force_sync:
                if not _reorder_data_check(last_data['reorder'],
                                           new_data['reorder']):
                    force_sync = True
            if force_sync:
                self.logger.error('\tforcing VACC sync')
                self.vacc_sync()
        IOLoop.current().call_later(check_time,
                                    self._vacc_periodic_check,
                                    new_data, check_time)
    
    def vacc_start_check_timer(self, vacc_check_time=30):
        """
        Set up a periodic check on the vacc operation.
        :param corr: the correlator instance
        :param vacc_check_time: the interval, in seconds, at which to check
        :return:
        """
        if not IOLoop.current()._running:
            raise RuntimeError('IOLoop not running, this will not work')
        self.logger.info('xeng_setup_vacc_check_timer: setting up the '
                         'vacc check timer at %i seconds' % vacc_check_time)
        if vacc_check_time < self.get_acc_time():
            raise RuntimeError('A check time smaller than the accumulation'
                               'time makes no sense.')
        IOLoop.current().add_callback(self._vacc_periodic_check,
                                      None, vacc_check_time)

    def initialise(self):
        """
        Set up x-engines on this device.
        :return:
        """
        # simulator
        if use_xeng_sim:
            THREADED_FPGA_OP(self.hosts, timeout=5,
                             target_function=(
                                 lambda fpga_: fpga_.registers.simulator.write(en=False, rst='pulse'),))
    
        # disable transmission, place cores in reset, and give control register a known state
        THREADED_FPGA_OP(self.hosts, timeout=5,
                         target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))
        THREADED_FPGA_OP(self.hosts, timeout=5,
                         target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=True),))
        self.clear_status_all()
    
        # set up default destination ip and port
        self.corr.set_stream_destination()
        self.corr.set_meta_destination()
    
        # set up the 10gbe cores
        xeng_port = int(self.corr.configd['xengine']['10gbe_port'])
        mac_start = tengbe.Mac(self.corr.configd['xengine']['10gbe_start_mac'])
    
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
            f.registers.board_id.write(reg=board_id)
            mac_ctr = 1
            for gbe, this_mac in zip(f.tengbes, macs):
                this_mac = tengbe.Mac.from_roach_hostname(f.host, mac_ctr)
                gbe.setup(mac=this_mac, ipaddress='0.0.0.0', port=xeng_port)
                self.logger.info(
                    'xhost(%s) gbe(%s) mac(%s) port(%i) board_id(%i)' %
                    (f.host, gbe.name, str(gbe.mac), xeng_port, board_id))
                # gbe.tap_start(restart=True)
                gbe.dhcp_start()
                mac_ctr += 1

        THREADED_FPGA_OP(self.hosts, timeout=40, target_function=(setup_gbes,))
    
        # clear gbe status
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(lambda fpga_: fpga_.registers.control.write(gbe_debug_rst='pulse'),))
    
        # release cores from reset
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=False),))
    
        # simulator
        if use_xeng_sim:
            THREADED_FPGA_OP(
                self.hosts, timeout=5,
                target_function=(lambda fpga_: fpga_.registers.simulator.write(en=True),))
    
        # set up accumulation length
        self.set_acc_len(vacc_resync=False)
    
        # clear general status
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(lambda fpga_: fpga_.registers.control.write(status_clr='pulse'),))
    
        # check for errors
        # TODO - read status regs?

    def clear_status_all(self):
        """
        Clear the various status registers and counters on all the fengines
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, timeout=10,
                           target_function='clear_status')

    def subscribe_to_multicast(self):
        """
        Subscribe the x-engines to the f-engine output multicast groups -
        each one subscribes to only one group, with data meant only for it.
        :return:
        """
        if self.corr.fengine_output.is_multicast():
            self.logger.info('F > X is multicast from base %s' %
                             self.corr.fengine_output)
            source_address = str(self.corr.fengine_output.ip_address)
            source_bits = source_address.split('.')
            source_base = int(source_bits[3])
            source_prefix = '%s.%s.%s.' % (source_bits[0],
                                           source_bits[1],
                                           source_bits[2])
            source_ctr = 0
            for host_ctr, host in enumerate(self.hosts):
                for gbe in host.tengbes:
                    rxaddress = '%s%d' % (source_prefix,
                                          source_base + source_ctr)
                    gbe.multicast_receive(rxaddress, 0)
                    source_ctr += 1
                    self.logger.info('\txhost %s %s subscribing to address %s' %
                                     (host.host, gbe.name, rxaddress))
        else:
            self.logger.info('F > X is unicast from base %s' %
                             self.corr.fengine_output)

    def check_rx(self, max_waittime=30):
        """
        Check that the x hosts are receiving data correctly
        :param max_waittime:
        :return:
        """
        self.logger.info('Checking X hosts are receiving data...')
        results = THREADED_FPGA_FUNC(
            self.hosts, timeout=max_waittime+1,
            target_function=('check_rx', (max_waittime,),))
        all_okay = True
        for _v in results.values():
            all_okay = all_okay and _v
        if not all_okay:
            self.logger.error('\tERROR in X-engine rx data.')
        self.logger.info('\tdone.')
        return all_okay

    def vacc_status(self):
        """
        Get a dictionary of the vacc status registers for all
        x-engines.
        :return: {}
        """
        return THREADED_FPGA_FUNC(self.hosts, timeout=10,
                                  target_function='vacc_get_status')
    
    def vacc_sync(self, vacc_load_time=None):
        """
        Sync the vector accumulators on all the x-engines.
        Assumes that the x-engines are all receiving data.
        :return:
        """
        min_ld_time = 2
        # how long should we wait for the vacc load
        if vacc_load_time is None:
            self.logger.info("Vacc sync time not specified. Syncing in %2.2f "
                             "seconds' time." % (2*min_ld_time))
            vacc_load_time = time.time()+2*min_ld_time
    
        t_now = time.time()
        if vacc_load_time < (t_now + min_ld_time):
            raise RuntimeError(
                'Cannot load at a time in the past. '
                'Need at least %2.2f seconds lead time. You asked for %s.%i, '
                'and it is now %s.%i.' % (
                    min_ld_time,
                    time.strftime('%H:%M:%S', time.gmtime(vacc_load_time)),
                    (vacc_load_time-int(vacc_load_time))*100,
                    time.strftime('%H:%M:%S', time.gmtime(t_now)),
                    (t_now-int(t_now))*100))
    
        self.logger.info('xeng vaccs syncing at %s (in %2.2fs)'
                         % (time.ctime(), vacc_load_time-time.time()))
    
        # check if the vaccs need resetting
        vaccstat = THREADED_FPGA_FUNC(
            self.hosts, timeout=10,
            target_function='vacc_check_arm_load_counts')
        reset_required = False
        for xhost, result in vaccstat.items():
            if result:
                self.logger.info('xeng_vacc_sync: %s has a vacc that '
                                 'needs resetting' % xhost)
                reset_required = True
    
        if reset_required:
            THREADED_FPGA_FUNC(self.hosts, timeout=10,
                               target_function='vacc_reset')
            vaccstat = THREADED_FPGA_FUNC(
                self.hosts, timeout=10,
                target_function='vacc_check_reset_status')
            for xhost, result in vaccstat.items():
                if not result:
                    errstr = 'xeng_vacc_sync: resetting vaccs on ' \
                             '%s failed.' % xhost
                    self.logger.error(errstr)
                    raise RuntimeError(errstr)
    
        # set the vacc load time on the xengines
        ldmcnt = int(self.corr.mcnt_from_time(vacc_load_time))
        quantisation_bits = int(
            numpy.log2(int(self.corr.configd['fengine']['n_chans'])) + 1 +
            numpy.log2(int(self.corr.configd['xengine']['xeng_accumulation_len'])))
        ldmcnt = ((ldmcnt >> quantisation_bits)+1) << quantisation_bits
    
        if self.corr.time_from_mcnt(ldmcnt) < time.time():
            self.logger.warn('Warning: the board timestamp has probably'
                             'wrapped!')
    
        self.logger.info('\tApplying load time: %i.' % ldmcnt)
        THREADED_FPGA_FUNC(self.hosts, timeout=10,
                           target_function=('vacc_set_loadtime', (ldmcnt,),))
    
        # read the current arm and load counts
        vacc_status = self.vacc_status()
        arm_count0 = vacc_status[self.hosts[0].host][0]['armcount']
        load_count0 = vacc_status[self.hosts[0].host][0]['loadcount']

        def print_vacc_statuses(vstatus):
            self.logger.info('VACC statii:')
            for _host in self.hosts:
                self.logger.info('\t%s:' % _host.host)
                for _ctr, _status in enumerate(vstatus[_host.host]):
                    self.logger.info('\t\t%i: %s' % (_ctr, _status))
    
        for host in self.hosts:
            for status in vacc_status[host.host]:
                _bad_ldcnt = status['loadcount'] != load_count0
                _bad_armcnt = status['armcount'] != arm_count0
                if _bad_ldcnt or _bad_armcnt:
                    self.logger.error('All hosts do not have matching arm and '
                                      'load counts.')
                    print_vacc_statuses(vacc_status)
                    raise RuntimeError('All hosts do not have matching arm and '
                                       'load counts.')

        self.logger.info('\tBefore arming: arm_count(%i) load_count(%i)' %
                         (arm_count0, load_count0))
    
        # then arm them
        THREADED_FPGA_FUNC(self.hosts, timeout=10, target_function='vacc_arm')
    
        # did the arm count increase?
        vacc_status = self.vacc_status()
        arm_count_new = vacc_status[self.hosts[0].host][0]['armcount']
        for host in self.hosts:
            for status in vacc_status[host.host]:
                if ((status['armcount'] != arm_count_new) or
                        (status['armcount'] != arm_count0 + 1)):
                    errstr = 'xeng_vacc_sync: all hosts do not have matching ' \
                             'arm counts or arm count did not increase.'
                    self.logger.error(errstr)
                    print_vacc_statuses(vacc_status)
                    raise RuntimeError(errstr)
        self.logger.info('\tDone arming')
    
        # check the the load time was stored correctly
        lsws = THREADED_FPGA_OP(
            self.hosts, timeout=10,
            target_function=(lambda x: x.registers.vacc_time_lsw.read()['data']),)
        msws = THREADED_FPGA_OP(
            self.hosts, timeout=10,
            target_function=(lambda x: x.registers.vacc_time_msw.read()['data']),)
        for host in self.hosts:
            if ((lsws[host.host]['lsw'] != lsws[self.hosts[0].host]['lsw']) or
                    (msws[host.host]['msw'] != msws[self.hosts[0].host]['msw'])):
                errstr = 'xeng_vacc_sync: all hosts do not have matching ' \
                         'VACC LSWs and MSWs'
                self.logger.error(errstr)
                print 'lsws:', lsws
                print 'msws:', msws
                vacc_status = self.vacc_status()
                print_vacc_statuses(vacc_status)
                raise RuntimeError(errstr)
        lsw = lsws[self.hosts[0].host]['lsw']
        msw = msws[self.hosts[0].host]['msw']
        xldtime = (msw << 32) | lsw
        self.logger.info('\tx engines have vacc ld time %i' % xldtime)
    
        # wait for the vaccs to arm
        wait_time = self.corr.time_from_mcnt(ldmcnt) - time.time() + 0.2
        self.logger.info('\tWaiting %2.2f seconds for arm to '
                         'trigger.' % wait_time)
        time.sleep(wait_time)
    
        # check the status to see that the load count increased
        vacc_status = self.vacc_status()
        load_count_new = vacc_status[self.hosts[0].host][0]['loadcount']
        for host in self.hosts:
            for status in vacc_status[host.host]:
                if ((status['loadcount'] != load_count_new) or
                        (status['loadcount'] != load_count0 + 1)):
                    self.logger.error('VACC did not trigger!')
                    print_vacc_statuses(vacc_status)
                    raise RuntimeError('VACC did not trigger!')
        self.logger.info('\tAll VACCs triggered correctly.')
    
        # allow vacc to flush and correctly populate parity bits:
        self.logger.info('\tWaiting %2.2fs for an accumulation to flush, '
                         'to correctly populate parity bits.' %
                         self.get_acc_time())
        time.sleep(self.get_acc_time()+0.2)
    
        self.logger.info('\tClearing status and reseting counters.')
        THREADED_FPGA_FUNC(self.hosts, timeout=10,
                           target_function='clear_status')
    
        # wait for a good accumulation to finish.
        self.logger.info('\tWaiting %2.2fs for an accumulation to flush '
                         'before checking counters.' % self.get_acc_time())
        time.sleep(self.get_acc_time()+0.2)
    
        # check the vacc status, errors and accumulations
        vac_okay = self.vacc_check_okay_initial()
        if not vac_okay:
            vacc_error_detail = THREADED_FPGA_FUNC(
                self.hosts, timeout=5,
                target_function='vacc_get_error_detail')
            self.logger.error('xeng_vacc_sync: exited on VACC error')
            self.logger.error('xeng_vacc_sync: vacc statii:')
            for host, item in vacc_status.items():
                self.logger.error('\t%s: %s' % (host, str(item)))
            self.logger.error('xeng_vacc_sync: vacc errors:')
            for host, item in vacc_error_detail.items():
                self.logger.error('\t%s: %s' % (host, str(item)))
            raise RuntimeError('xeng_vacc_sync: exited on VACC error')
        self.logger.info('\t...accumulations rolling in without error.')
        return self.corr.time_from_mcnt(ldmcnt)

    def vacc_check_okay_initial(self):
        """
        After an initial setup, is the vacc okay?
        Are the error counts zero and the counters
        ticking over?
        :param corr: The correlator instance.
        :return: True or False
        """
        self.logger.info('\tChecking for errors & accumulations...')
        vacc_status = self.vacc_status()
        for host in self.hosts:
            for status in vacc_status[host.host]:
                if status['errors'] > 0:
                    self.logger.error('\t\tVACC errors > 0. Que pasa?')
                    return False
                if status['count'] <= 0:
                    self.logger.error('\t\tVACC counts <= 0. Que pasa?')
                    return False
        self.logger.debug('\t\txeng_vacc_check_status: all okay')
        return True

    def set_acc_time(self, acc_time_s, vacc_resync=True):
        """
        Set the vacc accumulation length based on a required dump time, in seconds
        :param acc_time_s: new dump time, in seconds
        :return:
        """
        if use_xeng_sim:
            raise RuntimeError('That\'s not an option anymore.')
        else:
            new_acc_len = (
                (self.corr.sample_rate_hz * acc_time_s) /
                (self.corr.xeng_accumulation_len * self.corr.n_chans * 2.0))
            new_acc_len = round(new_acc_len)
            self.set_acc_len(new_acc_len, vacc_resync)

    def get_acc_time(self):
        """
        Get the dump time currently being used.
    
        Note: Will only be correct if accumulation time was set using this correlator
        object instance since cached values are used for the calculation.
        I.e., the number of accumulations are _not_ read from the FPGAs.
        :return:
        """
        return (self.corr.xeng_accumulation_len * self.corr.accumulation_len *
                self.corr.n_chans * 2.0) / self.corr.sample_rate_hz

    def set_acc_len(self, acc_len=None, vacc_resync=True):
        """
        Set the QDR vector accumulation length.
        :param acc_len:
        :return:
        """
        if acc_len is not None:
            self.corr.accumulation_len = acc_len
        THREADED_FPGA_OP(
            self.hosts, timeout=10,
            target_function=(
                lambda fpga_:
                fpga_.registers.acc_len.write_int(self.corr.accumulation_len),))
        self.logger.info('Set VACC accumulation length %d system-wide '
                         '(%.2f seconds)' %
                         (self.corr.accumulation_len, self.get_acc_time()))
        if self.corr.spead_meta_ig is not None:
            self.corr.spead_meta_ig['n_accs'] = self.corr.accumulation_len * \
                                                self.corr.xeng_accumulation_len
            self.corr.spead_meta_ig['int_time'] = self.get_acc_time()
            self.corr.spead_tx.send_heap(self.corr.spead_meta_ig.get_heap())
        if vacc_resync:
            self.vacc_sync()

    def get_baseline_order(self):
        """
        Return the order of baseline data output by a CASPER correlator X engine.
        :return:
        """
        # TODO - nants vs number of inputs?
        assert len(self.corr.fengine_sources)/2 == self.corr.n_antennas
        order1 = []
        order2 = []
        for ctr1 in range(self.corr.n_antennas):
            # print 'ctr1(%d)' % ctr1
            for ctr2 in range(int(self.corr.n_antennas/2), -1, -1):
                temp = (ctr1 - ctr2) % self.corr.n_antennas
                # print '\tctr2(%d) temp(%d)' % (ctr2, temp)
                if ctr1 >= temp:
                    order1.append((temp, ctr1))
                else:
                    order2.append((ctr1, temp))
        order2 = [order_ for order_ in order2 if order_ not in order1]
        baseline_order = order1 + order2
        source_names = []
        for source in self.corr.fengine_sources:
            source_names.append(source['source'].name)
        rv = []
        for baseline in baseline_order:
            rv.append((source_names[baseline[0] * 2],
                       source_names[baseline[1] * 2]))
            rv.append((source_names[baseline[0] * 2 + 1],
                       source_names[baseline[1] * 2 + 1]))
            rv.append((source_names[baseline[0] * 2],
                       source_names[baseline[1] * 2 + 1]))
            rv.append((source_names[baseline[0] * 2 + 1],
                       source_names[baseline[1] * 2]))
        return rv
    
    def tx_disable(self):
        """
        Start transmission of data products from the x-engines
        :param corr:
        :return:
        """
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(
                lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))

    def tx_enable(self):
        """
        Start transmission of data products from the x-engines
        :param corr:
        :return:
        """
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(
                lambda fpga_: fpga_.registers.control.write(gbe_txen=True),))
