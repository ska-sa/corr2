import time
import utils
from logging import INFO

from tornado.ioloop import IOLoop
from tornado.ioloop import PeriodicCallback
from tornado.locks import Event as IOLoopEvent

from casperfpga import utils as fpgautils

import data_stream
import fxcorrelator_speadops as speadops

# from corr2LogHandlers import getLogger

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

use_xeng_sim = False

class XengineStream(data_stream.SPEADStream):
    """
    An x-engine SPEAD stream
    """
    def __init__(self, name, destination, xops, max_pkt_size, timeout=5, *args, **kwargs):
        """
        Make a SPEAD stream.
        :param name: the name of the stream
        :param destination: where is it going?
        :return:
        """
        self.xops = xops
        self.timeout = timeout
        super(XengineStream, self).__init__(name,
            data_stream.XENGINE_CROSS_PRODUCTS, destination, max_pkt_size=max_pkt_size,
            instrument_descriptor=self.xops.corr.descriptor,
            *args, **kwargs)

    def descriptors_setup(self):
        """
        Set up the data descriptors for an X-engine stream.
        :return:
        """
        speadops.item_0x1600(self.descr_ig)
        import numpy
        n_xengs = len(self.xops.corr.xhosts) * self.xops.corr.x_per_fpga
        speadops.add_item(
            self.descr_ig, name='xeng_raw', id=0x1800,
            description=
            'Raw data for %i xengines in the system. This item represents a '
            'full spectrum (all frequency channels) assembled from lowest '
            'frequency to highest frequency. Each frequency channel contains '
            'the data for all baselines (n_bls given by SPEAD ID 0x100b). '
            'Each value is a complex number - two (real and imaginary) '
            'signed integers.' % n_xengs,
            dtype=numpy.dtype('>i4'),
            shape=[self.xops.corr.n_chans/n_xengs,
                   len(self.xops.get_baseline_ordering()), 2])
                   #len(self.xops.corr.baselines), 2])

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
                self.xops.hosts, timeout=self.timeout,
                target_function=(lambda fpga_:
                                 fpga_.registers.gbe_iptx.write(reg=txip),))
            THREADED_FPGA_OP(
                self.xops.hosts, timeout=self.timeout,
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
            self.xops.hosts, timeout=self.timeout,
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
            self.xops.hosts, timeout=self.timeout,
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

    def __init__(self, corr_obj, timeout=5, *args, **kwargs):
        """
        A collection of x-engine operations that act on/with a correlator
        instance.
        :param corr_obj: the FxCorrelator instance
        :return:
        """
        self.corr = corr_obj
        self.timeout = timeout
        self.hosts = corr_obj.xhosts
        self.data_stream = None
        self.vacc_acc_len = int(self.corr.configd['xengine']['accumulation_len'])
        self.xeng_acc_len = int(self.corr.configd['xengine']['xeng_accumulation_len'])

        self._board_ids = {}

        # Now creating separate instances of loggers as needed
        logger_name = '{}_XEngOps'.format(corr_obj.descriptor)
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)

        # All 'Instrument-level' objects will log at level INFO
        result, self.logger = corr_obj.getLogger(logger_name=logger_name,
                                                 log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        self.logger.debug('Successfully created logger for {}'.format(logger_name))

    @staticmethod
    def _gberst(hosts, state):
        THREADED_FPGA_OP(
            hosts, timeout=self.timeout,
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

    def initialise(self, *args, **kwargs):
        """
        Set up x-engines on this device.
        :return:
        """
        # disable transmission, place cores in reset, and give control
        # register a known state
        self.data_stream.tx_disable()
        #XEngineOperations._gberst(self.hosts, True)

        # write the board IDs to the xhosts
        board_id = 0
        for f in self.hosts:
            self._board_ids[f.host] = board_id
            f.registers.board_id.write(reg=board_id)
            board_id += 1

        #configure the ethernet cores.
        THREADED_FPGA_FUNC(
                self.hosts, timeout=self.timeout,
                target_function=('setup_host_gbes',
                                 (), {}))

        #subscribe to multicast groups
        self.subscribe_to_multicast()

        #set the tx_offset registers:
        #This adjusts the read offset in the HMC reorder blocks.
        # The idea is to offset each board's processing, so that
        # B-engines are offset relative to other boards.
        # We aim to offset each board by n_x_per_fpga windows (ie four frequency channels for MeerKAT)
        # NNB: ensure that the compiled packet buffer is deep enough to accommodate these offsets.
        # for 64A, the shift of the last board will be over 516K!
        board_id = 0
        self.logger.info("Setting TX offsets.")
        for f in self.hosts:
            offset=f.x_per_fpga*board_id*self.corr.n_antennas*self.xeng_acc_len/(256/32)
            f.registers.hmc_pkt_reord_rd_offset.write(rd_offset=offset)
            board_id += 1

        # write the data stream destination to the registers
        self.data_stream.write_destination()
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_stream_destinations()

        # set up accumulation length
        self.set_acc_len(vacc_resync=False)

    def configure(self, *args, **kwargs):
        """
        Configure the xengine operations - this is done whenever a correlator
        is instantiated.
        :return:
        """
        # set up the xengine data stream
        self._setup_data_stream(*args, **kwargs)

    def xengine_to_host_mapping(self):
        """
        Return a mapping of hostnames to engine numbers
        :return:
        """
        mapping = {}
        for host in self.hosts:
            board_id = self.board_ids[host.host]
            rv = ['xeng{:03}'.format((board_id * self.corr.x_per_fpga) + ctr)
                  for ctr in range(self.corr.x_per_fpga)]
            mapping[host.host] = rv
        return mapping

    def _setup_data_stream(self, *args, **kwargs):
        """
        Set up the data stream for the xengine output
        :return:
        """
        # the x-engine output data stream setup
        xeng_d = self.corr.configd['xengine']
        num_xeng = len(self.corr.xhosts) * self.corr.x_per_fpga
        output_name, output_address = utils.parse_output_products(xeng_d)
        assert len(output_name) == 1, 'Currently only single xeng products ' \
                                      'supported.'
        output_name = output_name[0]
        output_address = output_address[0]
        if output_address.ip_range != 1:
            raise RuntimeError(
                'The x-engine\'s given address range (%s) must be one, a '
                'starting base.' % output_address)
        output_address.ip_range = num_xeng
        max_pkt_size = self.corr.x_stream_payload_len
        xeng_stream = XengineStream(output_name, output_address, self,
                                    max_pkt_size=max_pkt_size,
                                    *args, **kwargs)
        self.data_stream = xeng_stream
        self.data_stream.set_source(self.corr.fops.data_stream.destination)
        self.corr.add_data_stream(xeng_stream)

    def clear_status_all(self):
        """
        Clear the various status registers and counters on all the xengines
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, timeout=self.timeout,
                           target_function='clear_status')

    def get_baseline_ordering(self):
        """
        Return the output baseline ordering as a list of tuples of input names.
        """
        new_labels=self.corr.get_input_labels()
        return utils.baselines_from_source_list(new_labels)

    def subscribe_to_multicast(self):
        """
        Subscribe the x-engines to the F-engine output multicast groups -
        each one subscribes to only one group, with data meant only for it.
        :return:
        """
        source_address = self.corr.fops.data_stream.destination
        if not source_address.is_multicast():
            self.logger.info('F > X is unicast from base %s' % source_address)
            return
        self.logger.info('F > X is multicast from base %s' % source_address)
        source_range = source_address.ip_range
        source_address = str(source_address.ip_address)
        source_bits = source_address.split('.')
        source_base = int(source_bits[3])
        source_prefix = '%s.%s.%s.' % (
            source_bits[0], source_bits[1], source_bits[2])
        source_ctr = 0
        num_x_hosts = len(self.hosts)
        num_gbes_per_x = len(self.hosts[0].gbes)
        num_ips_total = float(source_range)
        addresses_per_gbe = num_ips_total / (num_x_hosts * num_gbes_per_x)
        if ((addresses_per_gbe%1) != 0):
            raise RuntimeError("Impossible situation: Trying to subscribe to {} addresses per gbe port?".format(addresses_per_gbe))
        for host_ctr, host in enumerate(self.hosts):
            for gbe in host.gbes:
                rxaddress = '%s%d' % (source_prefix,
                                      source_base + source_ctr)
                gbe.multicast_receive(rxaddress, addresses_per_gbe-1)
                source_ctr += addresses_per_gbe
                self.logger.info('\tXhost %2i, %s: %s(%s+%i)' % (host.index,
                    host.host, gbe.name, rxaddress, addresses_per_gbe - 1))

    def get_rx_reorder_status(self):
        """
        Get a dictionary of the reorder status registers for all
        x-engines.
        :return: {}
        """
        return THREADED_FPGA_FUNC(self.hosts, timeout=self.timeout,
                                  target_function='get_rx_reorder_status')
    
    def vaccs_synchronised(self):
        """
        Checks all vaccs are synchronised with each other
        :return: True or False
        """ 
        rv=THREADED_FPGA_FUNC(self.hosts, timeout=self.timeout,
                                  target_function='get_vacc_timestamps')
        acc_len=int(self.vacc_acc_len)
        sync=True
        timestamp=rv[rv.keys()[0]][0]['timestamp']
        #check that they're all in sync; 
        #allow for reading registers at acc boundary:
        for hostname in rv:
            for vacc in rv[hostname]:
                if ((vacc['timestamp'] != timestamp) and 
                    (vacc['timestamp'] != (timestamp+acc_len)) and
                    (vacc['timestamp'] != (timestamp-acc_len))):
                    sync=False
        return sync

    def get_vacc_status(self):
        """
        Get a dictionary of the vacc status registers for all
        x-engines.
        :return: {}
        """
        rv=THREADED_FPGA_FUNC(self.hosts, timeout=self.timeout,
                                  target_function='get_vacc_status')
        acc_len=int(self.vacc_acc_len)
        sync=True
        timestamp=rv[rv.keys()[0]][0]['timestamp']
        #check that they're all in sync; 
        #allow for reading registers at acc boundary:
        for hostname in rv:
            for vacc in rv[hostname]:
                if ((vacc['timestamp'] != timestamp) and 
                    (vacc['timestamp'] != (timestamp+acc_len)) and
                    (vacc['timestamp'] != (timestamp-acc_len))):
                    sync=False
        rv['synchronised']=sync
        return rv

    def vacc_reset_all(self):
        """
        Reset all Xengine VACCs
        """
        self.logger.info('Resetting all VACCs.')
        THREADED_FPGA_FUNC(self.hosts, timeout=self.timeout,
                               target_function='vacc_reset')

    def _vacc_sync_create_loadtime(self, load_time=None):
        """
        Returns a valid load time for the vacc synch.
        Checks minimum load time.
        Generates a suitable loadtime if none is provided.
        :param load_time:
        :return: the vacc load time, in seconds since the UNIX epoch
        """
        min_loadtime = self.acc_time_from_len(self.vacc_acc_len) + 2.0
        # min_loadtime = 2
        t_now = time.time()
        if load_time is None:
            # how long should we wait for the vacc load
            self.logger.info('Vacc sync time not specified.')
            vacc_load_time = t_now + (min_loadtime*2)
        else:
            vacc_load_time = load_time
        askstr = 'You asked for %s.%i, and it is now %s.%i.' % (
            time.strftime('%H:%M:%S', time.gmtime(vacc_load_time)),
            (vacc_load_time-int(vacc_load_time))*100,
            time.strftime('%H:%M:%S', time.gmtime(t_now)),
            (t_now-int(t_now))*100)
        if vacc_load_time < (t_now + min_loadtime):
            raise RuntimeError(
                'Cannot load at a time in the past. Need at least %2.2f '
                'seconds lead time. %s' % (min_loadtime, askstr))
        elif vacc_load_time > (t_now + 10):
            self.logger.warn('Requested loadtime is more than '
                             '10 seconds away. %s' % askstr)
        self.logger.info('Vaccs will sync at %s (in %2.2fs)'
                         % (time.ctime(t_now), vacc_load_time-t_now))
        return vacc_load_time

    def _vacc_sync_calc_load_mcount(self, vacc_loadtime, phase_sync=True):
        """
        Calculate the loadtime in clock ticks,
         from a vacc_loadtime in seconds since the unix epoch.
        Accounts for quantisation due to Feng PFB.
        :param vacc_loadtime:
        :return:
        """
        import numpy
        ldmcnt = int(self.corr.mcnt_from_time(vacc_loadtime))
        self.logger.debug('$$$$$$$$$$$ - ldmcnt = %i' % ldmcnt)
        _ldmcnt_orig = ldmcnt
        quantisation_bits = int(
            numpy.log2(self.corr.n_chans) + 1 +
            numpy.log2(self.xeng_acc_len))

        if phase_sync:
            last_loadmcnt=self.get_vacc_loadtime()
            if last_loadmcnt>0:
                acc_len=int(self.vacc_acc_len)
                n_accs=int(((ldmcnt-last_loadmcnt)>>(quantisation_bits))/acc_len)+1
                self.logger.info("Attempting to phase-up VACC at acc_cnt {} since {}.".format(n_accs,last_loadmcnt))
                ldmcnt=last_loadmcnt+(((n_accs)*acc_len-1)<<quantisation_bits)

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

    def vacc_print_statuses(self, vstatus=None):
        """
        Print the vacc statuses to the logger
        :param vstatus:
        :return:
        """
        if vstatus==None:
            vstatus=self.get_vacc_status()
        self.logger.info('vacc statii:')
        for n,_host in enumerate(self.hosts):
            self.logger.info('\t%i, %s:' %(n,_host.host))
            for _ctr, _status in enumerate(vstatus[_host.host]):
                self.logger.info('\t\t%i: %s' % (_ctr, _status))

    def _vacc_sync_check_armload_increment(self, vacc_status_initial,check='arm_cnt'):
        """
        Check that the arm count increased
        :return:
        """
        vacc_status_new = self.get_vacc_status()
        rv=True
        for host in self.hosts: #iterate over hosts
            for i,status_new in enumerate(vacc_status_new[host.host]): #iterate over vaccs on host
                if (status_new[check] != vacc_status_initial[host.host][i][check] + 1):
                    errmsg = "xeng_vacc_sync: %s vacc %i's %s did not incrment."%(host.host,i,check)
                    if check == 'arm_cnt':
                        self.logger.warn(errmsg)
                    else:
                        self.logger.error(errmsg)
                    rv=False
        if rv: self.logger.info('VACC %s counters incremented successfully.'%check)
        return rv

    def _vacc_sync_wait_for_mcnt(self, load_mcount):
        """

        :param load_mcount:
        :return:
        """
        t_now = time.time()
        time_from_mcnt = self.corr.time_from_mcnt(load_mcount)
        wait_time = time_from_mcnt - t_now + self.acc_time_from_len(self.vacc_acc_len) + 1.2
        if wait_time <= 0:
            self.logger.error('\tTime passed %i seconds ago.'%wait_time)
            self.logger.error('\tcorr synch epoch: %i' %
                              self.corr.synchronisation_epoch)
            self.logger.error('\ttime.time(): %.10f' % t_now)
            self.logger.error('\ttime_from_mcnt: %.10f' % time_from_mcnt)
            self.logger.error('\tldmcnt: %i' % load_mcount)
            return

        self.logger.info('Waiting %2.2f seconds for arm to '
                         'trigger.' % wait_time)
        time.sleep(wait_time)

    def vacc_sync(self, sync_time=None):
        """
        Sync the vector accumulators on all the x-engines.
        Assumes that the x-engines are all receiving data.
        :return: the vacc synch time, in seconds since the UNIX epoch
        """

        #if self.vacc_synch_running.is_set():
        #    self.logger.error('vacc_sync called when it was already running?')
        #    return
        #self.vacc_synch_running.set()

        # work out the load time
        vacc_load_time = self._vacc_sync_create_loadtime(load_time=sync_time)

        # set the vacc load time on the xengines
        # should automatically estimate sync time, if needed.
        load_mcount = self._vacc_sync_calc_load_mcount(vacc_load_time)

        # set the load mcount on the x-engines
        self.logger.info('Applying load time: %i.' % load_mcount)
        THREADED_FPGA_FUNC(
            self.hosts, timeout=self.timeout,
            target_function=('vacc_set_loadtime', (load_mcount,),))

        # check the current counts
        #initial_status=self.get_vacc_status()

        # arm the xhosts
        THREADED_FPGA_FUNC(
            self.hosts, timeout=self.timeout, target_function='vacc_arm')

        ## did the arm count increase?
        #JM 2019-07-08 Don't bother checking this anymore.
        #self._vacc_sync_check_armload_increment(initial_status,check='arm_cnt')

        # wait for the vaccs to trigger
        # JM 2019-10-03 don't bother waiting to check if it succeeded. 
        # New HW automatically resyncs.
        #self._vacc_sync_wait_for_mcnt(load_mcount)
        # check the status to see that the load count increased
        #if not self._vacc_sync_check_armload_increment(initial_status,check='ld_cnt'):
        #    self.corr.fops.get_rx_timestamps()
        #    return -1

        synch_time = self.corr.time_from_mcnt(load_mcount)
        #self.vacc_synch_running.clear()
        return synch_time

    def acc_len_from_time(self, acc_time_s):
        """
        Given an acc time in seconds, get the number of cycles
        :param acc_time_s: the time for which to accumulate, in seconds
        :return:
        """
        new_acc_len = (self.corr.sample_rate_hz * acc_time_s) / (
                self.xeng_acc_len * self.corr.n_chans * 2.0 * self.corr.fops.decimation_factor)
        return round(new_acc_len)

    def acc_time_from_len(self, acc_len_cycles):
        """
        Given an acc time in seconds, get the number of cycles
        :param acc_len_cycles: number of clock cycles for which to accumulate
        :return:
        """
        return (acc_len_cycles * self.xeng_acc_len *
                self.corr.n_chans * 2.0 / self.corr.sample_rate_hz * self.corr.fops.decimation_factor)

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
        new_acc_len = self.acc_len_from_time(acc_time_s)
        self.corr.logger.info('set_acc_time: %.3fs -> new_acc_len(%i)' %
                              (acc_time_s, new_acc_len))
        self.set_acc_len(new_acc_len, vacc_resync)

    def get_acc_time(self):
        """
        Get the dump time currently being used.
        :return:
        """
        return self.acc_time_from_len(self.get_acc_len())

    def get_acc_len(self):
        """
        Read the acc len currently programmed into the FPGA.
        :return:
        """
        self.vacc_acc_len = int(self.hosts[0].vacc_get_acc_len())
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_xeng_acc_time()
        return self.vacc_acc_len

    def set_acc_len(self, acc_len=None, vacc_resync=True):
        """
        Set the vector accumulation length.
        :param acc_len: the accumulation length, in clock cycles
        :param vacc_resync: force a vacc resynchronisation
        :return:
        """
        if (acc_len is not None) and (acc_len <= 0):
            errmsg = 'new acc_len of %i makes no sense' % acc_len
            self.logger.error(errmsg)
            raise RuntimeError(errmsg)
        reenable_timer = False
        if acc_len is not None:
            self.vacc_acc_len = int(acc_len)

        # Here we space-out the packets that the correlator emits, to
        # smooth-out the bursty nature of the VACC output.
        #Calculates the gap size & set the gapsize register
        clock_cycles_per_accumulation = self.vacc_acc_len * 2 * self.corr.n_chans * self.xeng_acc_len/8*self.corr.fops.decimation_factor;#feng clock cycles. Divide by 8 to accomodate for the 8 samples in parallel
        vector_length_bytes = self.corr.n_antennas * (self.corr.n_antennas + 1)/2 * self.corr.n_chans * 8/ (len(self.hosts)*self.corr.x_per_fpga) * 4
        packets_per_accumulation = vector_length_bytes/self.corr.x_stream_payload_len
        gapsize = int(clock_cycles_per_accumulation/packets_per_accumulation*0.99) #scale by 0.99 to allow 1% deadtime between accs.

        if(gapsize > 2**19-1):
            gapsize = 2**19

        THREADED_FPGA_OP(
            self.hosts, timeout=self.timeout,
            target_function=(
                lambda fpga_:
                fpga_.registers.gapsize.write(gap_size=gapsize),))

        THREADED_FPGA_OP(
            self.hosts, timeout=self.timeout,
            target_function=(
                lambda fpga_:
                fpga_.vacc_set_acc_len(self.vacc_acc_len),))
        if self.corr.sensor_manager:
            self.corr.sensor_manager.sensors_xeng_acc_time()
        self.logger.info('Set vacc accumulation length %d system-wide '
                         '(%.2f seconds)' %
                         (self.vacc_acc_len,self.acc_time_from_len(self.vacc_acc_len)))
        if vacc_resync:
            self.vacc_sync()

    def auto_rst_enable(self):
        """
        Enable hardware automatic resync upon error detection.
        """
        THREADED_FPGA_OP(self.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.registers.control.write(auto_rst_enable=True), ))
        self.logger.info('X-engine hardware auto rst/resync mechanism enabled.')

    def auto_rst_disable(self):
        """
        Disable hardware automatic resync upon error detection.
        """
        THREADED_FPGA_OP(self.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.registers.control.write(auto_rst_enable=False), ))
        self.logger.info('X-engine hardware auto rst/resync mechanism disabled.')


    def gbe_counter_rst(self):
        """
        Reset gbe counters, this is needed for the gbe sensors to work.
        """
        THREADED_FPGA_OP(self.hosts, timeout=self.timeout,
            target_function=(lambda fpga_: fpga_.gbes.gbe0.get_hw_gbe_stats(rst_counters=True), ))
        self.logger.info('X-engine gbe counters reset for gbe0.')


        

    def get_vacc_loadtime(self):
        """
        Return the last time the VACCs were all loaded (synchronised),
        else, return -1
        """
        results = THREADED_FPGA_FUNC(
            self.hosts, timeout=self.timeout,
            target_function=('get_vacc_loadtime'))

        first_loadtime=results.values()[0]
        for hostname,loadtime in results.iteritems():
            if first_loadtime!=loadtime:
                errmsg = 'VACCs are not synchronised!'
                self.logger.error(errmsg)
                first_loadtime=-1
                break
        return first_loadtime

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
