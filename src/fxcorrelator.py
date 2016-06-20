"""
Created on Feb 28, 2013

@author: paulp
"""

# things all fxcorrelators Instruments do

import logging
import time
from katcp import Sensor


from casperfpga import utils as fpgautils

import log
import utils
import xhost_fpga
import fhost_fpga
import bhost_fpga

from instrument import Instrument
from data_source import DataSource

from fxcorrelator_fengops import FEngineOperations
from fxcorrelator_xengops import XEngineOperations
from fxcorrelator_bengops import BEngineOperations
from fxcorrelator_filterops import FilterOperations
from fxcorrelator_speadops import SpeadOperations

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

LOGGER = logging.getLogger(__name__)

MAX_QDR_ATTEMPTS = 5


class FxCorrelator(Instrument):
    """
    A generic FxCorrelator composed of fengines that channelise antenna inputs
    and xengines that each produce cross products from a continuous portion
    of the channels and accumulate the result.
    SPEAD data products are produced.
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
        self.loghandler = None

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
        self.fengine_sources = None
        self.baselines = None

        self._sensors = {}

        # parent constructor
        Instrument.__init__(self, descriptor, identifier, config_source, logger)

    def standard_log_config(self, log_level=logging.INFO, silence_spead=True):
        """Convenience method for setting up logging in scripts etc.
        :param log_level: The loglevel to use by default, logging.INFO.
        :param silence_spead: Set 'spead' logger to level WARNING if True

        """
        # Set the root logging handler - submodules loggers will automatically
        # use it
        self.loghandler = log.Corr2LogHandler()
        logging.root.addHandler(self.loghandler)
        logging.root.setLevel(log_level)
        self.logger.setLevel(log_level)
        self.logger.addHandler(self.loghandler)

        if silence_spead:
            # set the SPEAD logger to warning only
            spead_logger = logging.getLogger('spead')
            spead_logger.setLevel(logging.WARNING)

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
            if self.get_synch_time() == -1:
                raise RuntimeError('System synch epoch has not been set prior'
                                   ' to initialisation!')

        # set up the F, X, B and filter handlers
        self.fops = FEngineOperations(self)
        self.xops = XEngineOperations(self)
        self.bops = BEngineOperations(self)
        self.filtops = FilterOperations(self)
        self.speadops = SpeadOperations(self)

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
        self._initialise(program, qdr_cal)

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
                target_function=('setup_host_gbes', (self.logger, info_dict), {}))

    def _initialise(self, program, qdr_cal):
        """
        Run this if boards in the system have been programmed. Basic setup
        of devices.
        :return:
        """
        if not program:
            # only run the contents of this function after programming.
            return

        # cal the qdr on all boards
        # logging.getLogger('casperfpga.qdr').setLevel(logging.INFO + 7)
        if qdr_cal:
            self.qdr_calibrate()
        else:
            self.logger.info('Skipping QDR cal - are you sure you '
                             'want to do this?')

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

        # start f-engine TX
        self.logger.info('Starting f-engine datastream')
        self.fops.tx_enable()

        # jason's hack to force a reset on the f-engines
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
            raise RuntimeError('The f-engines RX have a problem.')

        # check that the timestamps received on the f-engines make sense
        if not self.fops.check_rx_timestamps():
            raise RuntimeError('The timestamps received by the f-engines '
                               'are not okay. Check the logs')

        # check that the F-engines are transmitting data correctly
        if not self.fops.check_tx():
            raise RuntimeError('The f-engines TX have a problem.')

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
        self.fops.configure()
        self.xops.configure()
        if self.found_beamformer:
            self.bops.configure()

    def sensors_clear(self):
        """
        Clear the current sensors
        :return:
        """
        self._sensors = {}

    def sensors_add(self, sensor):
        """
        Add a sensor to the dictionary of instrument sensors
        :param sensor:
        :return:
        """
        if sensor.name in self._sensors.keys():
            raise KeyError('Sensor {} already exists'.format(sensor.name))
        self._sensors[sensor.name] = sensor

    def sensors_get(self, sensor_name):
        """
        Get a sensor from the dictionary of instrument sensors
        :param sensor_name:
        :return:
        """
        if sensor_name not in self._sensors.keys():
            raise KeyError('Sensor {} does not exist'.format(sensor_name))
        return self._sensors[sensor_name]

    def set_synch_time(self, new_synch_time):
        """
        Set the last sync time for this system
        :param new_synch_time: UNIX time
        :return: <nothing>
        """
        time_now = time.time()
        # future?
        if new_synch_time > time_now:
            _err = 'Synch time in the future makes no sense? %.3f > %.3f' % (
                new_synch_time, time_now)
            self.logger.error(_err)
            raise RuntimeError(_err)
        # too far in the past?
        if new_synch_time < time_now - (2**self.timestamp_bits):
            _err = 'Synch epoch supplied is too far in the past: now(%.3f) ' \
                   'epoch(%.3f)' % (time_now, new_synch_time)
            self.logger.error(_err)
            raise RuntimeError(_err)
        self._synchronisation_epoch = new_synch_time
        self.logger.info('Set synch epoch to %.5f' % new_synch_time)

    def est_synch_epoch(self):
        """
        Estimates the synchronisation epoch based on current F-engine
        timestamp, and the system time.
        """
        self.logger.info('Estimating synchronisation epoch:')
        # get current time from an f-engine
        feng_mcnt = self.fhosts[0].get_local_time()
        self.logger.info('    current f-engine mcnt: %i' % feng_mcnt)
        if feng_mcnt & 0xfff != 0:
            _err = 'Bottom 12 bits of timestamp from f-engine are not ' \
                   'zero?! feng_mcnt(%i)' % feng_mcnt
            self.logger.error(_err)
            raise RuntimeError(_err)
        t_now = time.time()
        self.set_synch_time(t_now - feng_mcnt / float(self.sample_rate_hz))
        self.logger.info('    new epoch: %.3f' % self.get_synch_time())

    def time_from_mcnt(self, mcnt):
        """
        Returns the unix time UTC equivalent to the board timestamp. Does
        NOT account for wrapping timestamps.
        """
        if self.get_synch_time() < 0:
            self.logger.info('time_from_mcnt: synch epoch unset, estimating')
            self.est_synch_epoch()
        return self.get_synch_time() + (
            float(mcnt) / float(self.sample_rate_hz))

    def mcnt_from_time(self, time_seconds):
        """
        Returns the board timestamp from a given UTC system time
        (seconds since Unix Epoch). Accounts for wrapping timestamps.
        """
        if self.get_synch_time() < 0:
            self.logger.info('mcnt_from_time: synch epoch unset, estimating')
            self.est_synch_epoch()
        time_diff_from_synch_epoch = time_seconds - self.get_synch_time()
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

    def set_labels(self, newlist):
        """
        Apply new source labels to the configured fengine sources.
        :param newlist:
        :return:
        """
        if len(newlist) != len(self.fengine_sources):
            errstr = 'Number of supplied source labels (%i) does not match ' \
                     'number of configured sources (%i).' % \
                     (len(newlist), len(self.fengine_sources))
            self.logger.error(errstr)
            raise ValueError(errstr)
        oldnames = []
        newnames = []
        for ctr, source in enumerate(self.fengine_sources):
            _source = source['source']
            # update the source name
            old_name = _source.name
            _source.name = newlist[ctr]
            oldnames.append(old_name)
            newnames.append(newlist[ctr])
            # update the eq associated with that name
            found_eq = False
            for fhost in self.fhosts:
                if old_name in fhost.eqs.keys():
                    fhost.eqs[_source.name] = fhost.eqs.pop(old_name)
                    found_eq = True
                    break
            if not found_eq:
                raise ValueError(
                    'Could not find the old EQ value, %s, to update '
                    'to new name, %s.' % (old_name, _source.name))

        # update the hostname sensors
        try:
            for fhost in self.fhosts:
                sensor = self.sensors_get('%s_input_mapping' % fhost.host)
                rv = [dsrc.name for dsrc in fhost.data_sources]
                sensor.set(time.time(), Sensor.NOMINAL, str(rv))
        except Exception as ve:
            self.logger.WARNING('Could not update input_mapping '
                                'sensors!\n\n%s' % ve.message)

        # update the list of baselines
        self.baselines = utils.baselines_from_source_list(newlist)

        self.logger.info('Source labels updated from %s to %s' % (
            oldnames, newnames))
        # update the beam input labels
        if self.found_beamformer:
            self.bops.update_labels(oldnames, newnames)
        self.speadops.update_metadata([0x100e])

    def get_labels(self):
        """
        Get the current fengine source labels as a list of label names.
        :return:
        """
        return [src['source'].name for src in self.fengine_sources]

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return:
        """
        Instrument._read_config(self)
        _d = self.configd

        # check that the bitstream names are present
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

        # TODO: Load config values from the bitstream meta information -
        # f per fpga, x per fpga, etc
        _fxcorr_d = self.configd['FxCorrelator']
        self.arp_wait_time = int(_fxcorr_d['arp_wait_time'])
        self.sensor_poll_time = int(_fxcorr_d['sensor_poll_time'])
        self.katcp_port = int(_fxcorr_d['katcp_port'])
        self.sample_rate_hz = int(_fxcorr_d['sample_rate_hz'])
        self.timestamp_bits = int(_fxcorr_d['timestamp_bits'])
        self.time_jitter_allowed_ms = int(_fxcorr_d['time_jitter_allowed_ms'])
        self.time_offset_allowed_s = int(_fxcorr_d['time_offset_allowed_s'])
        try:
            self.post_switch_delay = int(_fxcorr_d['switch_delay'])
        except KeyError:
            self.post_switch_delay = 10

        _feng_d = self.configd['fengine']
        self.adc_demux_factor = int(_feng_d['adc_demux_factor'])
        self.n_chans = int(_feng_d['n_chans'])
        self.n_antennas = int(_feng_d['n_antennas'])
        self.min_load_time = float(_feng_d['min_load_time'])
        self.f_per_fpga = int(_feng_d['f_per_fpga'])
        self.ports_per_fengine = int(_feng_d['ports_per_fengine'])
        self.analogue_bandwidth = int(_feng_d['bandwidth'])

        _xeng_d = self.configd['xengine']
        self.x_per_fpga = int(_xeng_d['x_per_fpga'])
        self.accumulation_len = int(_xeng_d['accumulation_len'])
        self.xeng_accumulation_len = int(_xeng_d['xeng_accumulation_len'])

        # get this from the running x-engines?
        self.xeng_clk = int(_xeng_d['x_fpga_clock'])
        self.xeng_outbits = int(_xeng_d['xeng_outbits'])

        # check if beamformer exists with x-engines
        self.found_beamformer = False
        if 'bengine' in self.configd.keys():
            self.found_beamformer = True

        # set up hosts and engines based on the configuration in the ini file
        _targetClass = fhost_fpga.FpgaFHost
        self.fhosts = []
        for host in _feng_d['hosts'].split(','):
            host = host.strip()
            fpgahost = _targetClass.from_config_source(host, self.katcp_port,
                                                       config_source=_feng_d)
            self.fhosts.append(fpgahost)

        # choose class (b-engine inherits x-engine functionality)
        if self.found_beamformer:
            _targetClass = bhost_fpga.FpgaBHost
        else:
            _targetClass = xhost_fpga.FpgaXHost
        self.xhosts = []
        hostlist = _xeng_d['hosts'].split(',')
        for hostindex, host in enumerate(hostlist):
            host = host.strip()
            fpgahost = _targetClass.from_config_source(
                host, hostindex, self.katcp_port, config_source=_xeng_d)
            self.xhosts.append(fpgahost)

        # check that no hosts overlap
        for _fh in self.fhosts:
            for _xh in self.xhosts:
                if _fh.host == _xh.host:
                    self.logger.error('Host %s is assigned to '
                                      'both X- and F-engines' % _fh.host)
                    raise RuntimeError

        # update the list of baselines on this system
        self.baselines = utils.baselines_from_config(config=self.configd)

        # what data sources have we been allocated?
        self._handle_sources()

        # turn the product names into a list
        prodlist = _xeng_d['output_products'].replace('[', '')
        prodlist = prodlist.replace(']', '').split(',')
        _xeng_d['output_products'] = []
        for prod in prodlist:
            _xeng_d['output_products'].append(prod.strip(''))

    def _handle_sources(self):
        """
        Sort out sources and eqs for them
        :return:
        """
        assert len(self.fhosts) > 0
        _feng_cfg = self.configd['fengine']
        source_names = utils.sources_from_config(config=self.configd)
        source_mcast = _feng_cfg['source_mcast_ips'].strip().split(',')
        assert len(source_mcast) == len(source_names), (
            'Source names (%d) must be paired with multicast source '
            'addresses (%d)' % (len(source_names), len(source_mcast)))

        # match eq polys to source names
        eq_polys = {}
        for src_name in source_names:
            eq_polys[src_name] = utils.process_new_eq(
                _feng_cfg['eq_poly_%s' % src_name])

        # assemble the sources given into a list
        _fengine_sources = []
        for source_ctr, address in enumerate(source_mcast):
            new_source = DataSource.from_mcast_string(address)
            new_source.name = source_names[source_ctr]
            assert new_source.ip_range == self.ports_per_fengine, (
                'F-engines should be receiving from %d streams.' %
                self.ports_per_fengine)
            _fengine_sources.append(new_source)

        # assign sources and eqs to fhosts
        self.logger.info('Assigning DataSources, EQs and DelayTrackers to '
                         'f-engines...')
        source_ctr = 0
        self.fengine_sources = []
        for fhost in self.fhosts:
            self.logger.info('\t%s:' % fhost.host)
            _eq_dict = {}
            for fengnum in range(0, self.f_per_fpga):
                _source = _fengine_sources[source_ctr]
                _eq_dict[_source.name] = {'eq': eq_polys[_source.name],
                                          'bram_num': fengnum}
                assert _source.ip_range == _fengine_sources[0].ip_range, (
                    'All f-engines should be receiving from %d streams.' %
                    self.ports_per_fengine)
                self.fengine_sources.append({'source': _source,
                                             'source_num': source_ctr,
                                             'host': fhost,
                                             'numonhost': fengnum})
                fhost.add_source(_source)
                self.logger.info('\t\t%s' % _source)
                source_ctr += 1
            fhost.eqs = _eq_dict
        if source_ctr != len(self.fhosts) * self.f_per_fpga:
            raise RuntimeError('We have different numbers of sources (%d) and '
                               'f-engines (%d). Problem.', source_ctr,
                               len(self.fhosts) * self.f_per_fpga)
        self.logger.info('done.')

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

    def product_set_destination(self, product_name, txip_str=None, txport=None):
        """
        Set the destination for a data product.
        :param product_name:
        :param txip_str: A dotted-decimal string representation of the
        IP address. e.g. '1.2.3.4'
        :param txport: An integer port number.
        :return: <nothing>
        """
        if product_name not in self.data_products:
            raise ValueError('product %s is not in product list: %s' % (
                product_name, self.data_products))
        self.data_products[product_name].set_destination(txip_str, txport)

    def product_set_meta_destination(self, product_name,
                                     txip_str=None, txport=None):
        """
        Set the meta destination for a data product.
        :param product_name:
        :param txip_str: A dotted-decimal string representation of the
        IP address. e.g. '1.2.3.4'
        :param txport: An integer port number.
        :return: <nothing>
        """
        if product_name not in self.data_products:
            raise ValueError('product %s is not in product list: %s' % (
                product_name, self.data_products))
        self.data_products[product_name].set_meta_destination(txip_str, txport)

    def product_tx_enable(self, product_name):
        """
        Enable tranmission for a product
        :param product_name:
        :return:
        """
        if product_name not in self.data_products:
            raise ValueError('product %s is not in product list: %s' % (
                product_name, self.data_products))
        self.data_products[product_name].tx_enable()

    def product_tx_disable(self, product_name):
        """
        Disable tranmission for a product
        :param product_name:
        :return:
        """
        if product_name not in self.data_products:
            raise ValueError('product %s is not in product list: %s' % (
                product_name, self.data_products))
        self.data_products[product_name].tx_disable()

    def product_issue_metadata(self, product_name):
        """

        :param product_name:
        :return:
        """
        if product_name not in self.data_products:
            raise ValueError('product %s is not in product list: %s' % (
                product_name, self.data_products))
        self.data_products[product_name].meta_issue()

# end
