import time
import numpy
from tornado.ioloop import IOLoop
from tornado.ioloop import PeriodicCallback
from tornado.locks import Event as IOLoopEvent

from casperfpga import utils as fpgautils

import data_stream
import fxcorrelator_speadops as speadops
from utils import parse_output_products

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

use_xeng_sim = False

MAX_VACC_SYNCH_ATTEMPTS = 5


class XengineStream(data_stream.SPEADStream):
    """
    An x-engine SPEAD stream
    """
    def __init__(self, name, destination, xops):
        """
        Make a SPEAD stream.
        :param name: the name of the stream
        :param destination: where is it going?
        :return:
        """
        self.xops = xops
        super(XengineStream, self).__init__(
            name, data_stream.XENGINE_CROSS_PRODUCTS, destination)

    def descriptors_setup(self):
        """
        Set up the data descriptors for an X-engine stream.
        :return:
        """
        speadops.item_0x1600(self.descr_ig)

        # # xeng flags
        # speadops.add_item(
        #     self.descr_ig, name='flags_xeng_raw', id=0x1601,
        #     description=
        #     'Flags associated with xeng_raw data output. bit 34 - corruption '
        #     'or data missing during integration, bit 33 - overrange in '
        #     'data path, bit 32 - noise diode on during integration, '
        #     'bits 0 - 31 reserved for internal debugging',
        #     shape=[], format=[('u', speadops.SPEAD_ADDRSIZE)])

        # xeng data
        # shape of the x-engine data is:
        # shape=[self.corr.n_chans, len(self.corr.baselines), 2]
        # for debug:
        # shape=[self.corr.n_chans * len(self.corr.baselines), 2]
        n_xengs = len(self.xops.corr.xhosts) * self.xops.corr.x_per_fpga
        speadops.add_item(
            self.descr_ig, name='xeng_raw', id=0x1800,
            description=
            'Raw data for %i xengines in the system. This item represents a '
            'full spectrum (all frequency channels) assembled from lowest '
            'frequency to highest frequency. Each frequency channel contains '
            'the data for all baselines (n_bls given by SPEAD ID 0x100b). '
            'Each value is a complex number - two (real and imaginary) '
            'unsigned integers.' % n_xengs,
            dtype=numpy.dtype('>i4'),
            # shape=[self.xops.corr.n_chans, len(self.xops.corr.baselines), 2])
            shape=[self.xops.corr.n_chans/n_xengs,
                   len(self.xops.corr.baselines), 2])

        speadops.add_item(
            self.descr_ig, name='frequency', id=0x4103,
            description=
            'Identifies the first channel in the band of frequency channels '
            'in the SPEAD heap',
            shape=[], format=[('u', speadops.SPEAD_ADDRSIZE)])

    def write_destination(self):
        """
        Write the destination to the hardware.
        :return:
        """
        txip = int(self.destination.ip_address)
        txport = self.destination.port
        try:
            THREADED_FPGA_OP(
                self.xops.hosts, timeout=10,
                target_function=(lambda fpga_:
                                 fpga_.registers.gbe_iptx.write(reg=txip),))
            THREADED_FPGA_OP(
                self.xops.hosts, timeout=10,
                target_function=(lambda fpga_:
                                 fpga_.registers.gbe_porttx.write(reg=txport),))
        except AttributeError:
            errmsg = 'Writing stream %s destination to hardware ' \
                     'failed!' % self.name
            self.xops.logger.error(errmsg)
            raise RuntimeError(errmsg)

    def tx_enable(self):
        """
        Enable TX for this data stream
        :return:
        """
        self.descriptors_issue()
        THREADED_FPGA_OP(
            self.xops.hosts, timeout=5,
            target_function=(
                lambda fpga_:
                fpga_.registers.control.write(gbe_txen=True),))
        self.tx_enabled = True
        self.xops.logger.info('X-engine output enabled')

    def tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        THREADED_FPGA_OP(
            self.xops.hosts, timeout=5,
            target_function=(
                lambda fpga_:
                fpga_.registers.control.write(gbe_txen=False),))
        self.tx_enabled = False
        self.xops.logger.info('X-engine output disabled')

    def __str__(self):
        return 'XengineStream %s -> %s' % (self.name, self.destination)


class VaccSynchAttemptsMaxedOut(RuntimeError):
    pass


class XEngineOperations(object):

    def __init__(self, corr_obj):
        """
        A collection of x-engine operations that act on/with a correlator
        instance.
        :param corr_obj: the FxCorrelator instance
        :return:
        """
        self.corr = corr_obj
        self.hosts = corr_obj.xhosts
        self.logger = corr_obj.logger
        self.data_stream = None

        self._board_ids = {}

        self.vacc_synch_running = IOLoopEvent()
        self.vacc_synch_running.clear()
        self.vacc_check_enabled = IOLoopEvent()
        self.vacc_check_enabled.clear()
        self.vacc_check_cb = None
        self.vacc_check_cb_data = None

    @staticmethod
    def _gberst(hosts, state):
        THREADED_FPGA_OP(
            hosts, timeout=5,
            target_function=(
                lambda fpga_:
                fpga_.registers.control.write(gbe_rst=state),))

    @property
    def board_ids(self):
        if len(self._board_ids) == 0:
            self._board_ids = {
                f.host: f.registers.board_id.read()['data']['reg']
                for f in self.hosts
            }
        return self._board_ids

    def initialise_post_gbe(self):
        """
        Perform post-gbe setup initialisation steps
        :return:
        """
        # write the board IDs to the xhosts
        board_id = 0
        for f in self.hosts:
            self._board_ids[f.host] = board_id
            f.registers.board_id.write(reg=board_id)
            board_id += 1

        # write the data stream destination to the registers
        self.data_stream.write_destination()

        # clear gbe status
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(
                lambda fpga_:
                fpga_.registers.control.write(gbe_debug_rst='pulse'),))

        # release cores from reset
        XEngineOperations._gberst(self.hosts, False)

        # simulator
        if use_xeng_sim:
            THREADED_FPGA_OP(
                self.hosts, timeout=5,
                target_function=(
                    lambda fpga_: fpga_.registers.simulator.write(en=True),))

        # set up accumulation length
        self.set_acc_len(vacc_resync=False)

        # clear general status
        THREADED_FPGA_OP(
            self.hosts, timeout=5,
            target_function=(
                lambda fpga_:
                fpga_.registers.control.write(status_clr='pulse'),))

        # check for errors
        # TODO - read status regs?

    def initialise_pre_gbe(self):
        """
        Set up x-engines on this device.
        :return:
        """
        # simulator
        if use_xeng_sim:
            THREADED_FPGA_OP(
                self.hosts, timeout=5,
                target_function=(
                    lambda fpga_: fpga_.registers.simulator.write(
                        en=False, rst='pulse'),))

        # set the gapsize register
        gapsize = int(self.corr.configd['xengine']['10gbe_pkt_gapsize'])
        self.logger.info('X-engines: setting packet gap size to %i' % gapsize)
        if 'gapsize' in self.hosts[0].registers.names():
            # these versions have the correct logic surrounding the register
            THREADED_FPGA_OP(
                self.hosts, timeout=5,
                target_function=(
                    lambda fpga_: fpga_.registers.gapsize.write_int(gapsize),))
        elif 'gap_size' in self.hosts[0].registers.names():
            # these versions do not, they need a software hack for the setting
            # to 'take'
            THREADED_FPGA_OP(
                self.hosts, timeout=5,
                target_function=(
                    lambda fpga_: fpga_.registers.gap_size.write_int(gapsize),))
            # HACK - this is a hack to overcome broken x-engine firmware in
            # versions around a2d0615bc9cd95eabf7c8ed922c1a15658c0688e.
            # The logic next to the gap_size register is broken, registering
            # the LAST value written, not the new one.
            THREADED_FPGA_OP(
                self.hosts, timeout=5,
                target_function=(
                    lambda fpga_: fpga_.registers.gap_size.write_int(
                        gapsize-1),))
            # /HACK
        else:
            errmsg = 'X-engine image has no register gap_size/gapsize?'
            self.logger.error(errmsg)
            raise RuntimeError(errmsg)

        # disable transmission, place cores in reset, and give control
        # register a known state
        self.data_stream.tx_disable()

        XEngineOperations._gberst(self.hosts, True)

        self.clear_status_all()

    def configure(self):
        """
        Configure the xengine operations - this is done whenever a correlator
        is instantiated.
        :return:
        """
        # set up the xengine data stream
        self._setup_data_stream()

        # vacc check
        self.vacc_check_enabled.clear()
        self.vacc_synch_running.clear()
        if self.vacc_check_cb is not None:
            self.vacc_check_cb.stop()
        self.vacc_check_cb = None

    def xengine_to_host_mapping(self):
        """
        Return a mapping of hostnames to engine numbers
        :return:
        """
        mapping = {}
        for host in self.hosts:
            board_id = self.board_ids[host.host]
            rv = ['xeng{0}'.format((board_id * self.corr.x_per_fpga) + ctr)
                  for ctr in range(self.corr.x_per_fpga)]
            mapping[host.host] = rv
        return mapping

    def _setup_data_stream(self):
        """
        Set up the data stream for the xengine output
        :return:
        """
        # the x-engine output data stream setup
        xeng_d = self.corr.configd['xengine']
        num_xeng = len(self.corr.xhosts) * self.corr.x_per_fpga
        output_name, output_address = parse_output_products(xeng_d)
        assert len(output_name) == 1, 'Currently only single xeng products ' \
                                      'supported.'
        output_name = output_name[0]
        output_address = output_address[0]
        if output_address.ip_range != 1:
            raise RuntimeError(
                'The x-engine\'s given address range (%s) must be one, a '
                'starting base.' % output_address)
        output_address.ip_range = num_xeng
        xeng_stream = XengineStream(output_name, output_address, self)
        self.data_stream = xeng_stream
        self.data_stream.set_source(self.corr.fops.data_stream.destination)
        self.corr.add_data_stream(xeng_stream)

    def _vacc_periodic_check(self):

        self.logger.debug('Checking vacc operation @ %s' % time.ctime())

        if not self.vacc_check_enabled.is_set():
            self.logger.info('Check logic disabled, exiting')
            return

        if self.vacc_synch_running.is_set():
            self.logger.info('vacc_sync is currently running, exiting')
            return

        def get_data():
            """
            Get the relevant data from the X-engine FPGAs
            """
            # older versions had other register names
            _OLD = 'reorderr_timeout0' in self.hosts[0].registers.names()

            def _get_reorder_data(fpga):
                rv = {}
                for _ctr in range(0, fpga.x_per_fpga):
                    if _OLD:
                        _reg = fpga.registers['reorderr_timeout%i' % _ctr]
                        rv['etim%i' % _ctr] = _reg.read()['data']['reg']
                    else:
                        _reg = fpga.registers['reorderr_timedisc%i' % _ctr]
                        rv['etim%i' % _ctr] = _reg.read()['data']['timeout']
                return rv
            reo_data = THREADED_FPGA_OP(self.hosts, timeout=5,
                                        target_function=_get_reorder_data)
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
                        self.logger.error('\tvacc %i on %s has '
                                          'errors' % (xeng, host.host))
                        return False
            # check that the accumulations are ticking over
            for host in self.hosts:
                for xeng in range(0, host.x_per_fpga):
                    status0 = d0[host.host][xeng]
                    status1 = d1[host.host][xeng]
                    if status1['count'] == status0['count']:
                        self.logger.error('\tvacc %i on %s is not '
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
    
        if self.vacc_check_cb_data is not None:
            force_sync = False
            # check the vacc status data first
            if not _vacc_data_check(self.vacc_check_cb_data['vacc'],
                                    new_data['vacc']):
                force_sync = True
            # check the reorder data
            if not force_sync:
                if not _reorder_data_check(self.vacc_check_cb_data['reorder'],
                                           new_data['reorder']):
                    force_sync = True
            if force_sync:
                self.logger.error('\tforcing vacc sync')
                self.vacc_sync()

        self.corr.logger.debug('scheduled check done @ %s' % time.ctime())
        self.vacc_check_cb_data = new_data

    def vacc_check_timer_stop(self):
        """
        Disable the vacc_check timer
        :return:
        """
        if self.vacc_check_cb is not None:
            self.vacc_check_cb.stop()
        self.vacc_check_cb = None
        self.vacc_check_enabled.clear()
        self.corr.logger.info('vacc check timer stopped')

    def vacc_check_timer_start(self, vacc_check_time=30):
        """
        Set up a periodic check on the vacc operation.
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
        if self.vacc_check_cb is not None:
            self.vacc_check_cb.stop()
        self.vacc_check_cb = PeriodicCallback(self._vacc_periodic_check,
                                              vacc_check_time * 1000)
        self.vacc_check_enabled.set()
        self.vacc_check_cb.start()
        self.corr.logger.info('vacc check timer started')


    def clear_status_all(self):
        """
        Clear the various status registers and counters on all the fengines
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, timeout=10,
                           target_function='clear_status')

    def subscribe_to_multicast(self):
        """
        Subscribe the x-engines to the F-engine output multicast groups -
        each one subscribes to only one group, with data meant only for it.
        :return:
        """
        source_address = self.corr.fops.data_stream.destination
        if source_address.is_multicast():
            self.logger.info('F > X is multicast from base %s' % source_address)
            source_address = str(source_address.ip_address)
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

                    # CLUDGE
                    source_ctr += 1
                    # source_ctr += 4

                    self.logger.info('\txhost %s %s subscribing to address %s' %
                                     (host.host, gbe.name, rxaddress))
        else:
            self.logger.info('F > X is unicast from base %s' % source_address)

    def check_rx(self, max_waittime=30):
        """
        Check that the x hosts are receiving data correctly
        :param max_waittime:
        :return:
        """
        self.logger.info('Checking X hosts are receiving data...')
        results = THREADED_FPGA_FUNC(
            self.hosts, timeout=max_waittime+1,
            target_function=('check_rx_reorder', (), {}))
        all_okay = True
        for _v in results.values():
            all_okay = all_okay and _v
        if not all_okay:
            self.logger.error('\tERROR in X-engine rx data. '
                              'Checking higher up.')
            results = THREADED_FPGA_FUNC(
                self.hosts, timeout=max_waittime + 1,
                target_function=('check_rx', (max_waittime,),))
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

    def _vacc_sync_check_reset(self):
        """
        Do the vaccs need resetting before a synch?
        :return:
        """
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
                    errmsg = 'xeng_vacc_sync: resetting vaccs on ' \
                             '%s failed.' % xhost
                    self.logger.error(errmsg)
                    raise RuntimeError(errmsg)

    def _vacc_sync_create_loadtime(self, min_loadtime):
        """
        Calculate the load time for the vacc synch based on a
        given minimum load time
        :param min_loadtime:
        :return: the vacc load time, in seconds since the UNIX epoch
        """
        # how long should we wait for the vacc load
        self.logger.info('Vacc sync time not specified. Syncing in '
                         '%2.2f seconds\' time.' % (min_loadtime*2))
        t_now = time.time()
        vacc_load_time = t_now + (min_loadtime*2)

        if vacc_load_time < (t_now + min_loadtime):
            raise RuntimeError(
                'Cannot load at a time in the past. '
                'Need at least %2.2f seconds lead time. You asked for '
                '%s.%i, and it is now %s.%i.' % (
                    min_loadtime,
                    time.strftime('%H:%M:%S', time.gmtime(vacc_load_time)),
                    (vacc_load_time-int(vacc_load_time))*100,
                    time.strftime('%H:%M:%S', time.gmtime(t_now)),
                    (t_now-int(t_now))*100))

        self.logger.info('\txeng vaccs will sync at %s (in %2.2fs)'
                         % (time.ctime(t_now), vacc_load_time-t_now))
        return vacc_load_time

    def _vacc_sync_calc_load_mcount(self, vacc_loadtime):
        """
        Calculate the loadtime in clock ticks
        :param vacc_loadtime:
        :return:
        """
        ldmcnt = int(self.corr.mcnt_from_time(vacc_loadtime))
        self.logger.debug('$$$$$$$$$$$ - ldmcnt = %i' % ldmcnt)
        _ldmcnt_orig = ldmcnt
        _cfgd = self.corr.configd
        n_chans = int(_cfgd['fengine']['n_chans'])
        xeng_acc_len = int(_cfgd['xengine']['xeng_accumulation_len'])

        quantisation_bits = int(
            numpy.log2(n_chans) + 1 +
            numpy.log2(xeng_acc_len))

        self.logger.debug('$$$$$$$$$$$ - quant bits = %i' % quantisation_bits)
        ldmcnt = ((ldmcnt >> quantisation_bits) + 1) << quantisation_bits
        self.logger.debug('$$$$$$$$$$$ - ldmcnt quantised = %i' % ldmcnt)
        self.logger.debug('$$$$$$$$$$$ - ldmcnt diff = %i' % (
            ldmcnt - _ldmcnt_orig))
        if _ldmcnt_orig > ldmcnt:
            raise RuntimeError('Quantising the ldmcnt has broken it: %i -> '
                               '%i, diff(%i)' % (_ldmcnt_orig, ldmcnt,
                                                 ldmcnt - _ldmcnt_orig))
        time_from_mcnt = self.corr.time_from_mcnt(ldmcnt)
        t_now = time.time()
        if time_from_mcnt <= t_now:
            self.logger.warn('\tWarning: the board timestamp has probably'
                             ' wrapped! mcnt_time(%.3f) time.time(%.3f)' %
                             (time_from_mcnt, t_now))
        return ldmcnt

    def _vacc_sync_print_vacc_statuses(self, vstatus):
        """
        Print the vacc statuses to the logger
        :param vstatus:
        :return:
        """
        self.logger.info('vacc statii:')
        for _host in self.hosts:
            self.logger.info('\t%s:' % _host.host)
            for _ctr, _status in enumerate(vstatus[_host.host]):
                self.logger.info('\t\t%i: %s' % (_ctr, _status))

    def _vacc_sync_check_counts_initial(self):
        """
        Check the arm and load counts initially
        :return:
        """
        # read the current arm and load counts
        vacc_status = self.vacc_status()
        arm_count0 = vacc_status[self.hosts[0].host][0]['armcount']
        load_count0 = vacc_status[self.hosts[0].host][0]['loadcount']
        # check the xhosts load and arm counts
        for host in self.hosts:
            for status in vacc_status[host.host]:
                _bad_ldcnt = status['loadcount'] != load_count0
                _bad_armcnt = status['armcount'] != arm_count0
                if _bad_ldcnt or _bad_armcnt:
                    errmsg = 'All hosts do not have matching arm and ' \
                           'load counts.'
                    self.logger.error(errmsg)
                    self._vacc_sync_print_vacc_statuses(vacc_status)
                    raise RuntimeError(errmsg)
        self.logger.info('\tBefore arming: arm_count(%i) load_count(%i)' %
                         (arm_count0, load_count0))
        return arm_count0, load_count0

    def _vacc_sync_check_arm_count(self, armcount_initial):
        """
        Check that the arm count increased
        :return:
        """
        vacc_status = self.vacc_status()
        arm_count_new = vacc_status[self.hosts[0].host][0]['armcount']
        for host in self.hosts:
            for status in vacc_status[host.host]:
                if ((status['armcount'] != arm_count_new) or
                        (status['armcount'] != armcount_initial + 1)):
                    errmsg = 'xeng_vacc_sync: all hosts do not have ' \
                           'matching arm counts or arm count did ' \
                           'not increase.'
                    self.logger.error(errmsg)
                    self._vacc_sync_print_vacc_statuses(vacc_status)
                    return False
        self.logger.info('\tDone arming')
        return True

    def _vacc_sync_check_loadtimes(self):
        """

        :return:
        """
        lsws = THREADED_FPGA_OP(
            self.hosts, timeout=10,
            target_function=(
                lambda x: x.registers.vacc_time_lsw.read()['data']),)
        msws = THREADED_FPGA_OP(
            self.hosts, timeout=10,
            target_function=(
                lambda x: x.registers.vacc_time_msw.read()['data']),)
        _host0 = self.hosts[0].host
        for host in self.hosts:
            if ((lsws[host.host]['lsw'] != lsws[_host0]['lsw']) or
                    (msws[host.host]['msw'] != msws[_host0]['msw'])):
                errmsg = 'xeng_vacc_sync: all hosts do not have matching ' \
                       'vacc LSWs and MSWs'
                self.logger.error(errmsg)
                self.logger.error('LSWs: %s' % lsws)
                self.logger.error('MSWs: %s' % msws)
                vacc_status = self.vacc_status()
                self._vacc_sync_print_vacc_statuses(vacc_status)
                return False
        lsw = lsws[self.hosts[0].host]['lsw']
        msw = msws[self.hosts[0].host]['msw']
        xldtime = (msw << 32) | lsw
        self.logger.info('\tx engines have vacc ld time %i' % xldtime)
        return True

    def _vacc_sync_wait_for_arm(self, load_mcount):
        """

        :param load_mcount:
        :return:
        """
        t_now = time.time()
        time_from_mcnt = self.corr.time_from_mcnt(load_mcount)
        wait_time = time_from_mcnt - t_now + 0.2
        if wait_time <= 0:
            self.logger.error('\tThis is wonky - why is the wait_time '
                              'less than zero? %.3f' % wait_time)
            self.logger.error('\tcorr synch epoch: %i' %
                              self.corr.synchronisation_epoch)
            self.logger.error('\ttime.time(): %.10f' % t_now)
            self.logger.error('\ttime_from_mcnt: %.10f' % time_from_mcnt)
            self.logger.error('\tldmcnt: %i' % load_mcount)
            # hack
            wait_time = t_now + 4

        self.logger.info('\tWaiting %2.2f seconds for arm to '
                         'trigger.' % wait_time)
        time.sleep(wait_time)

    def _vacc_sync_check_load_count(self, load_count0):
        """
        Did the vaccs load counts increment correctly?
        :param load_count0:
        :return:
        """
        vacc_status = self.vacc_status()
        load_count_new = vacc_status[self.hosts[0].host][0]['loadcount']
        for host in self.hosts:
            for status in vacc_status[host.host]:
                if ((status['loadcount'] != load_count_new) or
                        (status['loadcount'] != load_count0 + 1)):
                    self.logger.error('vacc did not trigger!')
                    self._vacc_sync_print_vacc_statuses(vacc_status)
                    return False
        self.logger.info('\tAll vaccs triggered correctly.')
        return True

    def _vacc_sync_final_check(self):
        """
        Check the vacc status, errors and accumulations
        :return:
        """
        self.logger.info('\tChecking for errors & accumulations...')
        vac_okay = self._vacc_check_okay_initial()
        if not vac_okay:
            vacc_status = self.vacc_status()
            vacc_error_detail = THREADED_FPGA_FUNC(
                self.hosts, timeout=5,
                target_function='vacc_get_error_detail')
            self.logger.error('\t\txeng_vacc_sync: exited on vacc error')
            self.logger.error('\t\txeng_vacc_sync: vacc statii:')
            for host, item in vacc_status.items():
                self.logger.error('\t\t\t%s: %s' % (host, str(item)))
            self.logger.error('\t\txeng_vacc_sync: vacc errors:')
            for host, item in vacc_error_detail.items():
                self.logger.error('\t\t\t%s: %s' % (host, str(item)))
            self.logger.error('\t\txeng_vacc_sync: exited on vacc error')
            return False
        self.logger.info('\t...accumulations rolling in without error.')
        return True

    def _vacc_check_okay_initial(self):
        """
        After an initial setup, is the vacc okay?
        Are the error counts zero and the counters
        ticking over?
        :return: True or False
        """
        vacc_status = self.vacc_status()
        note_errors = False
        for host in self.hosts:
            for xeng_ctr, status in enumerate(vacc_status[host.host]):
                _msgpref = '{h}:{x} - '.format(h=host, x=xeng_ctr)
                errs = status['errors']
                thresh = self.corr.qdr_vacc_error_threshold
                if (errs > 0) and (errs < thresh):
                    self.logger.warn(
                        '\t\t{pref}{thresh} > vacc errors > 0. Que '
                        'pasa?'.format(pref=_msgpref, thresh=thresh))
                    note_errors = True
                elif (errs > 0) and (errs >= thresh):
                    self.logger.error(
                        '\t\t{pref}vacc errors > {thresh}. Problems.'.format(
                            pref=_msgpref, thresh=thresh))
                    return False
                if status['count'] <= 0:
                    self.logger.error(
                        '\t\t{}vacc counts <= 0. Que pasa?'.format(_msgpref))
                    return False
        if note_errors:
            # investigate the errors further, what caused them?
            if self._vacc_non_parity_errors():
                self.logger.error('\t\t\tsome vacc errors, but they\'re not '
                                  'parity errors. Problems.')
                return False
            self.logger.info('\t\tvacc_check_okay_initial: mostly okay, some '
                             'QDR parity errors')
        else:
            self.logger.info('\t\tvacc_check_okay_initial: all okay')
        return True

    def _vacc_non_parity_errors(self):
        """
        Are VACC errors other than parity errors occuring?
        :return:
        """
        _loops = 2
        parity_errors = 0
        for ctr in range(_loops):
            detail = THREADED_FPGA_FUNC(
                self.hosts, timeout=5, target_function='vacc_get_error_detail')
            for xhost in detail:
                for vals in detail[xhost]:
                    for field in vals:
                        if vals[field] > 0:
                            if field != 'parity':
                                return True
                            else:
                                parity_errors += 1
            if ctr < _loops - 1:
                time.sleep(self.get_acc_time() * 1.1)
        if parity_errors == 0:
            self.logger.error('\t\tThat\'s odd, VACC errors reported but '
                              'nothing caused them?')
            return True
        return False

    def vacc_sync(self):
        """
        Sync the vector accumulators on all the x-engines.
        Assumes that the x-engines are all receiving data.
        :return: the vacc synch time, in seconds since the UNIX epoch
        """

        if self.vacc_synch_running.is_set():
            self.logger.error('vacc_sync called when it was already running?')
            return
        self.vacc_synch_running.set()
        min_load_time = 2

        attempts = 0
        try:
            while True:
                attempts += 1

                if attempts > MAX_VACC_SYNCH_ATTEMPTS:
                    raise VaccSynchAttemptsMaxedOut(
                        'Reached maximum vacc synch attempts, aborting')

                # check if the vaccs need resetting
                self._vacc_sync_check_reset()

                # estimate the sync time, if needed
                self._vacc_sync_calc_load_mcount(time.time())

                # work out the load time
                vacc_load_time = self._vacc_sync_create_loadtime(min_load_time)

                # set the vacc load time on the xengines
                load_mcount = self._vacc_sync_calc_load_mcount(vacc_load_time)

                # set the load mcount on the x-engines
                self.logger.info('\tApplying load time: %i.' % load_mcount)
                THREADED_FPGA_FUNC(
                    self.hosts, timeout=10,
                    target_function=('vacc_set_loadtime', (load_mcount,),))

                # check the current counts
                (arm_count0,
                 load_count0) = self._vacc_sync_check_counts_initial()

                # arm the xhosts
                THREADED_FPGA_FUNC(
                    self.hosts, timeout=10, target_function='vacc_arm')

                # did the arm count increase?
                if not self._vacc_sync_check_arm_count(arm_count0):
                    continue

                # check the the load time was stored correctly
                if not self._vacc_sync_check_loadtimes():
                    continue

                # wait for the vaccs to arm
                self._vacc_sync_wait_for_arm(load_mcount)

                # check the status to see that the load count increased
                if not self._vacc_sync_check_load_count(load_count0):
                    continue

                # allow vacc to flush and correctly populate parity bits:
                self.logger.info('\tWaiting %2.2fs for an accumulation to '
                                 'flush, to correctly populate parity bits.' %
                                 self.get_acc_time())
                time.sleep(self.get_acc_time() + 0.2)

                self.logger.info('\tClearing status and reseting counters.')
                THREADED_FPGA_FUNC(self.hosts, timeout=10,
                                   target_function='clear_status')

                # wait for a good accumulation to finish.
                self.logger.info('\tWaiting %2.2fs for an accumulation to '
                                 'flush before checking counters.' %
                                 self.get_acc_time())
                time.sleep(self.get_acc_time() + 0.2)

                # check the vacc status, errors and accumulations
                if not self._vacc_sync_final_check():
                    continue

                # done
                synch_time = self.corr.time_from_mcnt(load_mcount)
                self.vacc_synch_running.clear()
                return synch_time
        except KeyboardInterrupt:
            self.vacc_synch_running.clear()
        except VaccSynchAttemptsMaxedOut as e:
            self.vacc_synch_running.clear()
            self.logger.error(e.message)
            raise e

    def set_acc_time(self, acc_time_s, vacc_resync=True):
        """
        Set the vacc accumulation length based on a required dump time,
        in seconds
        :param acc_time_s: new dump time, in seconds
        :param vacc_resync: force a vacc resynchronisation
        :return:
        """
        if use_xeng_sim:
            raise RuntimeError('That\'s not an option anymore.')
        new_acc_len = (
            (self.corr.sample_rate_hz * acc_time_s) /
            (self.corr.xeng_accumulation_len * self.corr.n_chans * 2.0))
        new_acc_len = round(new_acc_len)
        self.corr.logger.info('set_acc_time: %.3fs -> new_acc_len(%i)' %
                              (acc_time_s, new_acc_len))
        self.set_acc_len(new_acc_len, vacc_resync)
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_xeng_acc_time()

    def get_acc_time(self):
        """
        Get the dump time currently being used.
    
        Note: Will only be correct if accumulation time was set using this
        correlator
        object instance since cached values are used for the calculation.
        I.e., the number of accumulations are _not_ read from the FPGAs.
        :return:
        """
        return (self.corr.xeng_accumulation_len * self.corr.accumulation_len *
                self.corr.n_chans * 2.0) / self.corr.sample_rate_hz

    def get_acc_len(self):
        """
        Read the acc len currently programmed into the FPGA.
        :return:
        """
        return self.hosts[0].registers.acc_len.read_uint()

    def set_acc_len(self, acc_len=None, vacc_resync=True):
        """
        Set the QDR vector accumulation length.
        :param acc_len:
        :param vacc_resync: force a vacc resynchronisation
        :return:
        """
        if (acc_len is not None) and (acc_len <= 0):
            errmsg = 'new acc_len of %i makes no sense' % acc_len
            self.logger.error(errmsg)
            raise RuntimeError(errmsg)
        reenable_timer = False
        if self.vacc_check_enabled.is_set():
            self.vacc_check_timer_stop()
            reenable_timer = True
        if acc_len is not None:
            self.corr.accumulation_len = acc_len
        THREADED_FPGA_OP(
            self.hosts, timeout=10,
            target_function=(
                lambda fpga_:
                fpga_.registers.acc_len.write_int(self.corr.accumulation_len),))
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_xeng_acc_time()
        self.logger.info('Set vacc accumulation length %d system-wide '
                         '(%.2f seconds)' %
                         (self.corr.accumulation_len, self.get_acc_time()))
        if vacc_resync:
            self.vacc_sync()
        if reenable_timer:
            self.vacc_check_timer_start()

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
