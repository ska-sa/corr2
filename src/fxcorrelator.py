"""
Created on Feb 28, 2013

@author: paulp
"""

# things all fxcorrelators Instruments do

import logging
import time

from casperfpga import utils as fpgautils

import utils
import xhost_fpga
import fhost_fpga
import bhost_fpga
from instrument import Instrument
from fxcorrelator_fengops import FEngineOperations
from fxcorrelator_xengops import XEngineOperations
from fxcorrelator_bengops import BEngineOperations
from fxcorrelator_filterops import FilterOperations
from data_stream import StreamAddress
from digitiser import DigitiserStream

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

LOGGER = logging.getLogger(__name__)

MAX_QDR_ATTEMPTS = 5


class FxCorrelator(Instrument):
    """
    A generic FxCorrelator composed of fengines that channelise antenna inputs
    and xengines that each produce cross products from a continuous portion
    of the channels and accumulate the result.
    SPEAD data streams are produced.
    """
    def __init__(self, descriptor, identifier=-1, config_source=None,
                 logger=LOGGER):
        """
        An abstract base class for instruments.
        :param descriptor: A text description of the instrument. Required.
        :param identifier: An optional integer identifier.
        :param config_source: The instrument configuration source. Can be a
        text file, hostname, whatever.
        :param logger: Use the module logger by default, unless something else
        is given.
        :return: <nothing>

        """
        self.logger = logger

        # we know about f and x hosts and engines, not just engines and hosts
        self.fhosts = []
        self.xhosts = []
        self.filthosts = None
        self.found_beamformer = False

        self.fops = None
        self.xops = None
        self.bops = None
        self.filtops = None
        self.speadops = None

        # attributes
        self.katcp_port = None
        self.f_per_fpga = None
        self.x_per_fpga = None
        self.accumulation_len = None
        self.xeng_accumulation_len = None
        self.baselines = None

        # parent constructor
        Instrument.__init__(self, descriptor, identifier, config_source, logger)

    def initialise(self, program=True, qdr_cal=True, require_epoch=False):
        """
        Set up the correlator using the information in the config file.
        :param program: program the FPGA boards if True
        :param qdr_cal: perform QDR cal if True
        :param require_epoch: the synch epoch MUST be set before init if True
        :return:
        """
        # check that the instrument's synch epoch has been set
        if require_epoch:
            if self.synchronisation_epoch == -1:
                raise RuntimeError('System synch epoch has not been set prior'
                                   ' to initialisation!')

        # set up the F, X, B and filter handlers
        self.fops = FEngineOperations(self)
        self.xops = XEngineOperations(self)
        self.bops = BEngineOperations(self)
        self.filtops = FilterOperations(self)

        # set up the filter boards if we need to
        if 'filter' in self.configd:
            try:
                self.filtops.initialise(program=program)
            except Exception as e:
                raise e

        # connect to the other hosts that make up this correlator
        THREADED_FPGA_FUNC(self.fhosts + self.xhosts, timeout=5,
                           target_function='connect')

        igmp_version = self.configd['FxCorrelator'].get('igmp_version')
        if igmp_version is not None:
            self.logger.info('Setting FPGA hosts IGMP version '
                             'to %s' % igmp_version)
            THREADED_FPGA_FUNC(
                self.fhosts + self.xhosts, timeout=5,
                target_function=('set_igmp_version', (igmp_version, ), {}))

        # if we need to program the FPGAs, do so
        if program:
            self.logger.info('Programming FPGA hosts')
            fpgautils.program_fpgas([(host, host.boffile) for host in
                                     (self.fhosts + self.xhosts)],
                                    progfile=None, timeout=15)
        else:
            self.logger.info('Loading design information')
            THREADED_FPGA_FUNC(self.fhosts + self.xhosts, timeout=10,
                               target_function='get_system_information')

        # remove test hardware from designs
        utils.disable_test_gbes(self)
        utils.remove_test_objects(self)

        # run configuration on the parts of the instrument
        self.configure()

        # run post-programming initialisation
        self.post_program_initialise(program, qdr_cal)

        # reset all counters on fhosts and xhosts
        self.fops.clear_status_all()
        self.xops.clear_status_all()

        # set an initialised flag
        self._initialised = True

    def _gbe_setup(self):
        """
        Set up the 10gbe ports on the hosts
        :return:
        """
        feng_port = int(self.configd['fengine']['10gbe_port'])
        xeng_port = int(self.configd['xengine']['10gbe_port'])
        info_dict = {host.host: (feng_port, 'fhost') for host in self.fhosts}
        info_dict.update(
            {host.host: (xeng_port, 'xhost') for host in self.xhosts})
        timeout = len(self.fhosts[0].tengbes) * 30 * 1.1
        THREADED_FPGA_FUNC(
                self.fhosts + self.xhosts, timeout=timeout,
                target_function=('setup_host_gbes',
                                 (self.logger, info_dict), {}))

    def post_program_initialise(self, programming_done, qdr_cal):
        """
        Run this if boards in the system have been programmed. Basic setup
        of devices.
        :param programming_done: True if the boards were newly programmed
        :param qdr_cal: should we attempt to calibrate the QDRs on the boards?
        :return:
        """
        if not programming_done:
            # only run the contents of this function after programming.
            return

        # cal the qdr on all boards
        # logging.getLogger('casperfpga.qdr').setLevel(logging.INFO + 7)
        if qdr_cal:
            self.qdr_calibrate()
        else:
            self.logger.info(
                'Skipping QDR cal - are you sure you want to do this?')

        # init the engines
        self.fops.initialise_pre_gbe()
        self.xops.initialise_pre_gbe()

        # set up the tengbe ports in parallel
        self._gbe_setup()

        # continue with init
        self.fops.initialise_post_gbe()
        self.xops.initialise_post_gbe()
        if self.found_beamformer:
            self.bops.initialise()

        # subscribe all the engines to the multicast groups
        self.fops.subscribe_to_multicast()
        self.xops.subscribe_to_multicast()

        # start F-engine TX
        self.logger.info('Starting F-engine datastream')
        self.fops.tx_enable()

        # jason's hack to force a reset on the F-engines
        for ctr in range(0, 2):
            time.sleep(1)
            self.fops.sys_reset()

        # wait for switches to learn, um, stuff
        self.logger.info('post mess-with-the-switch delay of %is' %
                         self.post_switch_delay)
        time.sleep(self.post_switch_delay)

        # reset all counters on fhosts and xhosts
        self.fops.clear_status_all()
        self.xops.clear_status_all()

        # check to see if the f engines are receiving all their data
        if not self.fops.check_rx():
            raise RuntimeError('The F-engines RX have a problem.')

        # check that the timestamps received on the F-engines make sense
        result, times, times_unix = self.fops.check_rx_timestamps()
        if not result:
            raise RuntimeError('The timestamps received by the F-engines '
                               'are not okay. Check the logs')

        # check the F-engine QDR uses for parity errors
        if not self.fops.check_qdr_devices():
            raise RuntimeError('The F-engine QDRs are reporting errors.')

        # check that the F-engines are transmitting data correctly
        if not self.fops.check_tx():
            LOGGER.info('The F-engines TX have a problem, retrying.')
            if not self.fops.resync_and_check():
                raise RuntimeError('The F-engines TX have a problem.')

        # check that the X-engines are receiving data
        if not self.xops.check_rx():
            raise RuntimeError('The x-engines RX have a problem.')

        # arm the vaccs on the x-engines
        self.xops.vacc_sync()

    def configure(self):
        """
        Operations to run to configure the instrument, after programming.
        :return:
        """
        self.configure_digitiser_streams()
        self.fops.configure()
        self.xops.configure()
        if self.found_beamformer:
            self.bops.configure()

    @staticmethod
    def configure_digitiser_streams():
        """
        Set up the digitiser streams available to this correlator.
        :return:
        """
        pass

    def get_scale_factor(self):
        """
        By what number do we divide timestamps to get seconds?
        :return:
        """
        return self.sample_rate_hz

    def est_synch_epoch(self):
        """
        Estimates the synchronisation epoch based on current F-engine
        timestamp, and the system time.
        """
        self.logger.info('Estimating synchronisation epoch:')
        # get current time from an F-engine
        feng_mcnt = self.fhosts[0].get_local_time()
        self.logger.info('\tcurrent F-engine mcnt: %i' % feng_mcnt)
        if feng_mcnt & 0xfff != 0:
            errmsg = 'Bottom 12 bits of timestamp from F-engine are not ' \
                   'zero?! feng_mcnt(%i)' % feng_mcnt
            self.logger.error(errmsg)
            raise RuntimeError(errmsg)
        t_now = time.time()
        self.synchronisation_epoch = t_now - feng_mcnt / self.sample_rate_hz
        self.logger.info('\tnew epoch: %.3f' % self.synchronisation_epoch)

    def time_from_mcnt(self, mcnt):
        """
        Returns the unix time UTC equivalent to the board timestamp. Does
        NOT account for wrapping timestamps.
        :param mcnt: the time from system boards (ADC ticks since startup)
        """
        if self.synchronisation_epoch < 0:
            self.logger.info('time_from_mcnt: synch epoch unset, estimating')
            self.est_synch_epoch()
        return self.synchronisation_epoch + (
            float(mcnt) / self.sample_rate_hz)

    def mcnt_from_time(self, time_seconds):
        """
        Returns the board timestamp from a given UTC system time
        (seconds since Unix Epoch). Accounts for wrapping timestamps.
        :param time_seconds: UNIX time
        """
        if self.synchronisation_epoch < 0:
            self.logger.info('mcnt_from_time: synch epoch unset, estimating')
            self.est_synch_epoch()
        time_diff_from_synch_epoch = time_seconds - self.synchronisation_epoch
        time_diff_in_samples = int(time_diff_from_synch_epoch *
                                   self.sample_rate_hz)
        _tmp = 2**self.timestamp_bits
        return time_diff_in_samples % _tmp

    def qdr_calibrate(self, timeout=120 * MAX_QDR_ATTEMPTS):
        """
        Run a software calibration routine on all the FPGA hosts.
        Do it on F- and X-hosts in parallel.
        :param timeout: how many seconds to wait for it to complete
        :return:
        """
        def _qdr_cal(_fpga):
            """
            Calibrate the QDRs found on a given FPGA.
            :param _fpga:
            :return:
            """
            _tic = time.time()
            attempts = 0
            _results = {_qdr.name: False for _qdr in _fpga.qdrs}
            while True:
                all_passed = True
                for _qdr in _fpga.qdrs:
                    if not _results[_qdr.name]:
                        try:
                            _res = _qdr.qdr_cal(fail_hard=False)
                        except RuntimeError:
                            _res = False
                        try:
                            _resval = _res[0]
                        except TypeError:
                            _resval = _res
                        if not _resval:
                            all_passed = False
                        _results[_qdr.name] = _resval
                attempts += 1
                if all_passed or (attempts >= MAX_QDR_ATTEMPTS):
                    break
            _toc = time.time()
            return {'results': _results, 'tic': _tic, 'toc': _toc,
                    'attempts': attempts}

        self.logger.info('Calibrating QDR on F- and X-engines, this may '
                         'take a while.')
        qdr_calfail = False
        results = THREADED_FPGA_OP(
            self.fhosts + self.xhosts, timeout, (_qdr_cal,))
        for fpga, result in results.items():
            _time_taken = result['toc'] - result['tic']
            self.logger.info('FPGA %s QDR cal: %.3fs, %i attempts' %
                             (fpga, _time_taken, result['attempts']))
            for qdr, qdrres in result['results'].items():
                if not qdrres:
                    qdr_calfail = True
                    break
                self.logger.info('\t%s: cal okay: %s' %
                                 (qdr, 'True' if qdrres else 'False'))
        if qdr_calfail:
            raise RuntimeError('QDR calibration failure.')
        # for host in self.fhosts:
        #     for qdr in host.qdrs:
        #         qdr.qdr_delay_in_step(0b111111111111111111111111111111111111,
        # -1)
        # for host in self.xhosts:
        #     for qdr in host.qdrs:
        #         qdr.qdr_delay_in_step(0b111111111111111111111111111111111111,
        # -1)

    def set_input_labels(self, new_labels):
        """
        Apply new source labels to the configured fengine sources.
        :param new_labels: a list of new input labels
        :return:
        """
        old_labels = self.get_input_labels()
        if len(new_labels) != len(old_labels):
            errmsg = 'Number of supplied source labels (%i) does not match ' \
                     'number of configured sources (%i).' % \
                     (len(new_labels), len(old_labels))
            self.logger.error(errmsg)
            raise ValueError(errmsg)
        all_the_same = True
        for ctr, new_label in enumerate(new_labels):
            if new_label != old_labels[ctr]:
                all_the_same = False
                break
        if all_the_same:
            self.logger.info('New list of labels is the same as old labels.')
            return

        # match old labels to input streams
        for ctr, old_label in enumerate(old_labels):
            self.get_data_stream(old_label).name = new_labels[ctr]

        # update the list of baselines
        self.baselines = utils.baselines_from_source_list(new_labels)

        if self.sensor_manager:
            self.sensor_manager.sensors_input_labels()
            self.sensor_manager.sensors_baseline_ordering()

        self.logger.info('Source labels updated from %s to %s' % (
            old_labels, self.get_input_labels()))

    def get_input_mapping(self):
        """
        Get a more complete input mapping of inputs to positions and boards
        :return:
        """
        fengsorted = sorted(self.fops.fengines,
                            key=lambda fengine: fengine.input_number)
        return [
            (f.input.name, f.input_number, f.host.host, f.offset)
            for f in fengsorted
        ]

    def get_input_labels(self):
        """
        Get the current fengine source labels as a list of label names.
        :return:
        """
        fengsorted = sorted(self.fops.fengines,
                            key=lambda fengine: fengine.input_number)
        return [feng.name for feng in fengsorted]

    def _check_bitstreams(self):
        """
        Are the bitstreams from the config accessible?
        :return:
        """
        _d = self.configd
        try:
            open(_d['fengine']['bitstream'], 'r').close()
            open(_d['xengine']['bitstream'], 'r').close()
        except IOError:
            self.logger.error('xengine bitstream: '
                              '%s' % _d['xengine']['bitstream'])
            self.logger.error('fengine bitstream: '
                              '%s' % _d['fengine']['bitstream'])
            self.logger.error('One or more bitstream files not found.')
            raise IOError('One or more bitstream files not found.')

    def _create_hosts(self):
        """
        Set up the different kind of hosts that make up this correlator.
        :return:
        """
        _feng_d = self.configd['fengine']
        _target_class = fhost_fpga.FpgaFHost
        self.fhosts = []
        for host in _feng_d['hosts'].split(','):
            host = host.strip()
            fpgahost = _target_class.from_config_source(
                host, self.katcp_port, config_source=_feng_d)
            self.fhosts.append(fpgahost)
        # choose class (b-engine inherits x-engine functionality)
        if self.found_beamformer:
            _target_class = bhost_fpga.FpgaBHost
        else:
            _target_class = xhost_fpga.FpgaXHost
        self.xhosts = []
        _xeng_d = self.configd['xengine']
        hostlist = _xeng_d['hosts'].split(',')
        for hostindex, host in enumerate(hostlist):
            host = host.strip()
            fpgahost = _target_class.from_config_source(
                host, hostindex, self.katcp_port, config_source=_xeng_d)
            self.xhosts.append(fpgahost)
        # check that no hosts overlap
        for _fh in self.fhosts:
            for _xh in self.xhosts:
                if _fh.host == _xh.host:
                    self.logger.error('Host %s is assigned to '
                                      'both X- and F-engines' % _fh.host)
                    raise RuntimeError

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return:
        """
        Instrument._read_config(self)
        _d = self.configd

        # do the bitstreams exist?
        self._check_bitstreams()

        # TODO: Load config values from the bitstream meta
        # information - f per fpga, x per fpga, etc
        _fxcorr_d = self.configd['FxCorrelator']
        self.arp_wait_time = int(_fxcorr_d['arp_wait_time'])
        self.sensor_poll_time = int(_fxcorr_d['sensor_poll_time'])
        self.katcp_port = int(_fxcorr_d['katcp_port'])
        self.sample_rate_hz = float(_fxcorr_d['sample_rate_hz'])
        self.timestamp_bits = int(_fxcorr_d['timestamp_bits'])
        self.time_jitter_allowed_ms = int(_fxcorr_d['time_jitter_allowed_ms'])
        self.time_offset_allowed_s = int(_fxcorr_d['time_offset_allowed_s'])
        try:
            self.post_switch_delay = int(_fxcorr_d['switch_delay'])
        except KeyError:
            self.post_switch_delay = 10
        if 'spead_metapacket_ttl' in _fxcorr_d:
            import data_stream
            data_stream.SPEAD_PKT_TTL = int(_fxcorr_d['spead_metapacket_ttl'])

        _feng_d = self.configd['fengine']
        self.adc_demux_factor = int(_feng_d['adc_demux_factor'])
        self.n_chans = int(_feng_d['n_chans'])
        self.n_antennas = int(_feng_d['n_antennas'])
        self.min_load_time = float(_feng_d['min_load_time'])
        self.f_per_fpga = int(_feng_d['f_per_fpga'])
        self.ports_per_fengine = int(_feng_d['ports_per_fengine'])
        self.analogue_bandwidth = int(_feng_d['bandwidth'])
        self.true_cf = float(_feng_d['true_cf'])
        self.quant_format = _feng_d['quant_format']
        self.adc_bitwidth = int(_feng_d['sample_bits'])
        self.fft_shift = int(_feng_d['fft_shift'])

        try:
            self.qdr_ct_error_threshold = int(_feng_d['qdr_ct_error_threshold'])
        except KeyError:
            self.qdr_ct_error_threshold = 100
        try:
            self.qdr_cd_error_threshold = int(_feng_d['qdr_cd_error_threshold'])
        except KeyError:
            self.qdr_cd_error_threshold = 100

        _xeng_d = self.configd['xengine']
        self.x_per_fpga = int(_xeng_d['x_per_fpga'])
        self.accumulation_len = int(_xeng_d['accumulation_len'])
        self.xeng_accumulation_len = int(_xeng_d['xeng_accumulation_len'])
        try:
            self.qdr_vacc_error_threshold = int(
                _xeng_d['qdr_vacc_error_threshold'])
        except KeyError:
            self.qdr_vacc_error_threshold = 100

        # TODO - get this from the running x-engines?
        self.xeng_clk = int(_xeng_d['x_fpga_clock'])
        self.xeng_outbits = int(_xeng_d['xeng_outbits'])

        # TODO - get this from the config file
        # check if beamformer exists with x-engines
        self.found_beamformer = False
        if 'bengine' in self.configd.keys():
            self.found_beamformer = True
            try:
                self.beng_outbits = int(self.configd['bengine']['beng_outbits'])
            except KeyError:
                self.beng_outbits = 8

        # create the host objects
        self._create_hosts()

        # update the list of baselines on this system
        self.baselines = utils.baselines_from_config(config=self.configd)

        # what digitiser data streams have we been allocated?
        self._create_digitiser_streams()

    def _create_digitiser_streams(self):
        """
        Parse the config of the given digitiser streams.
        :return:
        """
        _fengd = self.configd['fengine']
        source_names = utils.sources_from_config(config=self.configd)
        source_mcast = _fengd['source_mcast_ips'].strip().split(',')
        for ctr, src in enumerate(source_mcast):
            source_mcast[ctr] = src.strip()
        assert len(source_mcast) == len(source_names), (
            'Source names (%d) must be paired with multicast source '
            'addresses (%d)' % (len(source_names), len(source_mcast)))
        for ctr, source in enumerate(source_names):
            addr = StreamAddress.from_address_string(source_mcast[ctr])
            dig_src = DigitiserStream(source, addr, ctr, self)
            self.add_data_stream(dig_src)

    def _read_config_file(self):
        """
        Read the instrument configuration from self.config_source.
        :return: True if we read the file successfully, False if not
        """
        self.configd = utils.parse_ini_file(self.config_source)

    def _read_config_server(self):
        """
        Get instance-specific setup information from a given server. Via KATCP?
        :return:
        """
        raise NotImplementedError('_read_config_server not implemented')

    def stream_set_destination(self, stream_name, address):
        """
        Set the destination for a data stream.
        :param stream_name:
        :param address: A dotted-decimal string representation of the
        IP address, range and port. e.g. '1.2.3.4+0:7890'
        :return: <nothing>
        """
        stream = self.get_data_stream(stream_name)
        stream.set_destination(address)
        if self.sensor_manager:
            self.sensor_manager.sensors_stream_destinations()

    def stream_issue_metadata(self, stream_name=None):
        """
        Issue metadata for a stream produced by this instrument.
        :param stream_name: if none is given, do all streams
        :return:
        """
        if stream_name is None:
            streams = self.data_streams
        else:
            streams = [self.get_data_stream(stream_name)]
        for stream in streams:
            if hasattr(stream, 'metadata_issue'):
                stream.metadata_issue()
            else:
                self.logger.debug('SPEADStream {} is not a metadata stream'
                                  ''.format(stream.name))

# end
