"""
Created on Feb 28, 2013

@author: paulp
"""

from __future__ import print_function

# things all fxcorrelators Instruments do

import re
import time
import katcp
import signal
# Yes, I know it's just an integer value
from logging import INFO

# from memory_profiler import profile

from casperfpga import utils as fpgautils
from casperfpga import skarab_fileops as skfops
import utils
import xhost_fpga
import fhost_fpga
import bhost_fpga
import resource
from instrument import Instrument
from fxcorrelator_fengops import FEngineOperations
from fxcorrelator_xengops import XEngineOperations
from fxcorrelator_bengops import BEngineOperations
from fxcorrelator_filterops import FilterOperations
from data_stream import StreamAddress

from corr2LogHandlers import getLogger as _getLogger

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

def _disable_write(*args, **kwargs):
    """

    :param args:
    :param kwargs:
    :return:
    """
    raise RuntimeError('WRITE ACCESS TO CORRELATOR DISABLED')


class ReadOnlyDict(dict):
    def __readonly__(self, *args, **kwargs):
        raise RuntimeError(
            'Cannot modify ReadOnlyDict: {}, {}'.format(
                args, kwargs))
    __setitem__ = __readonly__
    __delitem__ = __readonly__
    pop = __readonly__
    popitem = __readonly__
    clear = __readonly__
    update = __readonly__
    setdefault = __readonly__
    del __readonly__


class FxCorrelator(Instrument):
    """
    A generic FxCorrelator composed of fengines that channelise antenna inputs
    and xengines that each produce cross products from a continuous portion
    of the channels and accumulate the result.
    SPEAD data streams are produced.
    """

    # @profile
    def __init__(
            self,
            descriptor,
            config_source=None,
            identifier=-1,
            **kwargs):
        """
        An abstract base class for instruments.
        :param descriptor: A text description of the instrument. Required.
        :param config_source: The instrument configuration source. Can be a
                              text file, hostname, whatever.
        :param identifier: An optional integer identifier.
        :return: <nothing>
        """
        # we know about f and x hosts and engines, not just engines and hosts
        # TODO: these things should be in the _read_config() method. Do we really want to initialise them to None here?
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
        self.timeout = None

        # Parent constructor invokes reading the config file, generic hosts, data streams and logging.
        Instrument.__init__(self, descriptor, config_source, identifier, **kwargs)

        # up the filedescriptors so we can handle bigger arrays.
        # 64A needs ~1100, mainly for spead descriptor sockets,
        # since spead2 needs a separate socket per destination
        # (it uses send rather than sendto).
        fd_limit = int(self.configd['FxCorrelator'].get('max_fd', 4096))
        resource.setrlimit(resource.RLIMIT_NOFILE, (fd_limit, fd_limit))

        # create the host objects
        #self._create_hosts(**kwargs)

        new_connection_string = '\n==========================================\n'
        self.logger.info('{0}Successfully created Instrument: {1}{0}'.format(new_connection_string, self.descriptor))

    # @profile
    def initialise(self, program=True, configure=True,
                   require_epoch=False, *args, **kwargs):
        """
        Set up the correlator using the information in the config file.
        :param program: program the FPGA boards, implies configure
        :param configure: configure the system
        :param require_epoch: the synch epoch MUST be set before init
        :return:
        """
        # check that the instrument's synch epoch has been set
        if self.synchronisation_epoch <= 0:
            try:
                self.synchronisation_epoch = float(self.configd['FxCorrelator']['synchronisation_epoch'])
            except ValueError:
                self.logger.error("Sync epoch malformed in config file, and epoch not pre-set.")
            except KeyError:
                self.logger.warn("Sync epoch not found in config file, and epoch not pre-set.")
        else:
            self.logger.info("Sync epoch pre-set to {}.".format(self.synchronisation_epoch))
        
        if (require_epoch) and (self.synchronisation_epoch < 0):
            raise RuntimeError(
                'System sync epoch has not been set prior to initialisation!')

        # clear the data streams. These will be re-added during configuration.
        self.data_streams = []

        # set up the F, X, B and filter handlers
        self.fops = FEngineOperations(self, timeout=self.timeout, **kwargs)
        self.xops = XEngineOperations(self, timeout=self.timeout, **kwargs)
        self.bops = BEngineOperations(self, timeout=self.timeout, **kwargs)
        self.filtops = FilterOperations(self, **kwargs)

        # set up the filter boards if we need to
        if 'filter' in self.configd:
            try:
                self.filtops.initialise(program=program, *args, **kwargs)
            except Exception as err:
                errmsg = 'Failed to initialise filter boards: %s' % str(err)
                self.logger.error(errmsg)
                raise RuntimeError(errmsg)

        # connect to the other hosts that make up this correlator
        THREADED_FPGA_FUNC(self.fhosts + self.xhosts, timeout=self.timeout,
                           target_function='connect')


        # if we need to program the FPGAs, do so
        xbof = self.xhosts[0].bitstream
        fbof = self.fhosts[0].bitstream
        if program:
            # skfops = casperfpga.skarab_fileops
            # force the new programming method
            try:
                function_call = ""
                def progska_timeout_handler(signum, frame):
                    raise Exception("Function: {} timed out.".format(function_call))
    
                #Setting up timeout signal
                signal.signal(signal.SIGALRM, progska_timeout_handler)

                function_call = "skfops.upload_to_ram_progska(fbof, self.fhosts)"
                signal.alarm(int(self.timeout * (len(self.fhosts)**0.5) + 60))
                skfops.upload_to_ram_progska(fbof, self.fhosts)
                function_call = "skfops.reboot_skarabs_from_sdram(self.fhosts)"
                signal.alarm(int(self.timeout))
                skfops.reboot_skarabs_from_sdram(self.fhosts)

                signal.alarm(int(self.timeout * (len(self.xhosts)**0.5) + 60))
                function_call = "skfops.upload_to_ram_progska(xbof, self.xhosts)"
                skfops.upload_to_ram_progska(xbof, self.xhosts)
                signal.alarm(int(self.timeout))
                function_call = "skfops.reboot_skarabs_from_sdram(self.xhosts)"
                skfops.reboot_skarabs_from_sdram(self.xhosts)
                signal.alarm(0)

                #This signal.alarm is probably not necessary. This is just a catch-all in case things get stuck
                signal.alarm(self.timeout * (len(self.fhosts) + len(self.xhosts)))
                function_call = "skfops.wait_after_reboot(self.fhosts + self.xhosts... "
                skfops.wait_after_reboot(self.fhosts +
                            self.xhosts, timeout=self.timeout *
                (len(self.fhosts) + len(self.xhosts)))
    
                #Cancel all timeout sigals
                signal.alarm(0)

            except Exception as err:
                errmsg = 'Failed to program the boards: %s' % str(err)
                signal.alarm(0)
                self.logger.error(errmsg)
                raise

        fisskarab = True
        xisskarab = True
        if (not program) or fisskarab or xisskarab:
            self.logger.info('Loading design information')
            THREADED_FPGA_FUNC(
                self.fhosts, timeout=self.timeout * 10,
                target_function=('get_system_information', [fbof], {}))
            #THREADED_FPGA_FUNC(
            #    self.fhosts, timeout=self.timeout * 10,
            #    target_function=('get_system_information', [fbof], {'legacy_reg_map' : False}))
            THREADED_FPGA_FUNC(
                self.xhosts, timeout=self.timeout * 10,
                target_function=('get_system_information', [xbof], {}))

        #Log the bitstreams we're using...
        # Better to stitch a log-string together
        # than to log in a for-loop
        for _h in [self.fhosts[0],self.xhosts[0]]:
            bitstream_info_str = _h.bitstream + ':\n'
            if 'git' in _h.rcs_info:
                for gitfile, gitparams in _h.rcs_info['git'].items():
                    bitstream_info_str += (str(gitfile) + ':' + str(gitparams)+'\n')
            self.logger.info(bitstream_info_str)

        # remove test hardware from designs
        utils.disable_test_gbes(self)
        utils.remove_test_objects(self)
        # # disable write access to the correlator
        # if not (enable_write_access or program):
        #     for host in self.xhosts + self.fhosts:
        #         host.blindwrite = _disable_write

        # run configuration on the parts of the instrument
        # this is independant of programming!
        # - Passing args and kwargs through here, for completeness
        if 'getLogger' in kwargs:
            self.configure(*args, **kwargs)
        else:
            self.configure(getLogger=self.getLogger, *args, **kwargs)
        # run post-programming initialisation
        if program or configure:
            # Passing args and kwargs through here, for completeness
            self._post_program_initialise(*args, **kwargs)

        # set an initialised flag
        self._initialised = True

    def _gbe_setup(self):
        """
        Set up the Ethernet ports on the hosts
        :return:
        """
        THREADED_FPGA_FUNC(
            self.fhosts + self.xhosts, timeout=self.timeout,
            target_function=('setup_host_gbes', (), {}))

    def _post_program_initialise(self, *args, **kwargs):
        """
        Run this if boards in the system have been programmed. Basic setup
        of devices.
        :return:
        """
        # init the engines
        self.fops.initialise(*args, **kwargs)
        self.xops.initialise(*args, **kwargs)
        if self.found_beamformer:
            self.bops.initialise(*args, **kwargs)

        # start F-engine TX
        self.logger.info('Starting F-engine datastream')
        self.fops.tx_enable(force_enable=True)

        # wait for switches to learn, um, stuff
        self.logger.info(
            'post mess-with-the-switch delay of {}s'.format(self.post_switch_delay))
        time.sleep(self.post_switch_delay)

        #Forcefully resync the Fengines once the DIG data is flowing reliably:
        #self.fops.sys_reset()
        #time.sleep(5)
        self.fops.auto_rst_enable()
        self.fops.sys_reset()

        if self.synchronisation_epoch == -1:
            self.est_synch_epoch()

        # arm the vaccs on the x-engines
        if self.xops.vacc_sync() > 0:
            # reset all counters on fhosts and xhosts
            self.fops.clear_status_all()
            self.xops.clear_status_all()
        self.xops.auto_rst_enable()


    def configure(self, *args, **kwargs):
        """
        Operations to run to configure the instrument, after programming.
        :return:
        """
        self.configure_digitiser_streams()
        self.fops.configure(*args, **kwargs)
        self.xops.configure(*args, **kwargs)
        if self.found_beamformer:
            self.bops.configure(*args, **kwargs)

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

    def est_synch_epoch(self,f_index=0):
        """
        Estimates the synchronisation epoch based on current F-engine
        timestamp, and the system time.
        """
        self.logger.info('Estimating synchronisation epoch:')
        # get current time from an F-engine
        feng_mcnt = self.fhosts[f_index].get_local_time()
        self.logger.info('\tcurrent F-engine mcnt: {}'.format(feng_mcnt))
        t_now = time.time()
        self.synchronisation_epoch = t_now - feng_mcnt / self.sample_rate_hz
        self.logger.info(
            '\tnew epoch: {} ({})'.format(
                self.synchronisation_epoch, time.ctime(
                    self.synchronisation_epoch)))

    def time_from_mcnt(self, mcnt):
        """
        Returns the unix time UTC equivalent to the board timestamp. Does
        NOT account for wrapping timestamps.
        :param mcnt: the time from system boards (ADC ticks since startup)
        """
        if self.synchronisation_epoch < 0:
            self.logger.info('time_from_mcnt: synch epoch unset, estimating')
            self.est_synch_epoch()
        return self.synchronisation_epoch + (float(mcnt) / self.sample_rate_hz)

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
        time_diff_in_samples = int(
            time_diff_from_synch_epoch *
            self.sample_rate_hz)
        _tmp = 2**self.timestamp_bits
        return time_diff_in_samples % _tmp

    def set_input_labels(self, new_labels):
        """
        Apply new source labels to the configured fengine sources.
        :param new_labels: a list of new input labels
        :return:
        """
        old_labels = self.get_input_labels()
        if len(new_labels) != len(old_labels):
            errmsg = (
                'Number of supplied source labels ({}) does not match'
                ' number of configured sources ({}).'.format(
                    len(new_labels), len(old_labels)))
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
#        fengsorted = sorted(
#            self.fops.fengines,
#            key=lambda fengine: fengine.input_number)
        for ctr, feng in enumerate(self.fops.fengines):
            feng.name = new_labels[ctr]

        if self.sensor_manager:
            self.sensor_manager.sensors_input_labels()
            self.sensor_manager.sensors_baseline_ordering()

        self.logger.info(
            'Source labels updated from {} to {}'.format(
                old_labels, self.get_input_labels()))

    def get_input_mapping(self):
        """
        Get a more complete input mapping of inputs to positions and boards
        :return:
        """
#        fengsorted = sorted(
#            self.fops.fengines,
#            key=lambda fengine: fengine.input_number)
        return [(f.input.name, f.input_number, f.host.host, f.offset)
                for f in self.fops.fengines]

    def get_input_labels(self):
        """
        Get the current fengine source labels as a list of label names.
        :return:
        """
#        fengsorted = sorted(
#            self.fops.fengines,
#            key=lambda fengine: fengine.input_number)
        return [feng.name for feng in self.fops.fengines]

    def _check_bitstreams(self):
        """
        Are the bitstreams from the config accessible?
        :return:
        """
        _d = self.configd
        try:
            open(_d['fengine']['bitstream'], 'r').close()
        except IOError:
            errmsg = 'One or more fengine bitstream ({}) files not found'.format(
                _d['fengine']['bitstream'])
            self.logger.error(errmsg)
            raise IOError(errmsg)

        try:
            open(_d['xengine']['bitstream'], 'r').close()
        except IOError:
            errmsg = 'One or more xengine bitstream ({}) files not found'.format(
                _d['xengine']['bitstream'])
            self.logger.error(errmsg)
            raise IOError(errmsg)

    def _create_hosts(self, **kwargs):
        """
        Set up the different kind of hosts that make up this correlator.
        :return:
        """
        _target_class = fhost_fpga.FpgaFHost

        _feng_d = self.configd.get('fengine')
        assert isinstance(_feng_d, dict)
        fhostlist = re.split(r'[,\s]+', _feng_d.get('hosts'))
        assert isinstance(fhostlist, list)
        self.fhosts = []
        for hostindex, host in enumerate(fhostlist):
            host = host.strip()
            try:
                fpgahost = _target_class.from_config_source(
                    host,
                    self.katcp_port,
                    config_source=_feng_d,
                    host_id=hostindex,
                    descriptor=self.descriptor,
                    getLogger=self.getLogger,
                    **kwargs)
            except Exception as exc:
                self.logger.error(
                    'Could not create fhost {}: {}'.format(
                        host, str(exc)))
                raise
            self.fhosts.append(fpgahost)
        # choose class (b-engine inherits x-engine functionality)
        if self.found_beamformer:
            _target_class = bhost_fpga.FpgaBHost
        else:
            _target_class = xhost_fpga.FpgaXHost
        _xeng_d = self.configd.get('xengine')
        assert isinstance(_xeng_d, dict)
        xhostlist = re.split(r'[,\s]+', _xeng_d.get('hosts'))
        assert isinstance(xhostlist, list)
        self.xhosts = []
        for hostindex, host in enumerate(xhostlist):
            host = host.strip()
            try:
                fpgahost = _target_class.from_config_source(
                    host,
                    hostindex,
                    self.katcp_port,
                    self.configd,
                    descriptor=self.descriptor,
                    getLogger=self.getLogger,
                    **kwargs)
            except Exception as exc:
                errmsg = 'Could not create xhost {}: {}'.format(host, str(exc))
                self.logger.error(errmsg)
                raise
            self.xhosts.append(fpgahost)
        # check that no hosts overlap
        for _fh in self.fhosts:
            for _xh in self.xhosts:
                if _fh.host == _xh.host:
                    errmsg = 'Host {} is assigned to both X- and F-engines'.format(
                        _fh.host)
                    self.logger.error(errmsg)
                    raise RuntimeError(errmsg)

    def _read_config(self):
        """
        Read the instrument configuration from self.config_source.
        :return:
        """
        if self.config_source is None:
            raise RuntimeError(
                'Running _read_config with no config source. Explosions!!!')
        errmsg = ''
        try:
            self._read_config_file()
        except (IOError, ValueError) as excep:
            errmsg += str(excep) + '\n'
            try:
                self._read_config_server()
            except katcp.KatcpClientError as excep:
                errmsg += str(excep) + '\n'
            # If a file-path is given, but the file doesn't exist, then it will try to find a server
            # but obviously it's not going to work, so we'll get a SyntaxError. This just catches it
            # in a sane manner.
            except SyntaxError:
                pass

        if self.configd is None:
            self.logger.error(errmsg)
            raise RuntimeError('Supplied config_source {} is invalid.'.format(self.config_source))

        # do the bitstreams exist?
        self._check_bitstreams()
        # =====================================================================
        _fxcorr_d = self.configd['FxCorrelator']
        
        # Can't continue if these values are not present in config file.
        self.sample_rate_hz = float(_fxcorr_d['sample_rate_hz'])
        self.timestamp_bits = int(_fxcorr_d['timestamp_bits'])
        self.n_antennas = int(_fxcorr_d['n_ants'])

        # Warn user if sensor poll interval is not in config file and default is set.
        try:
            self.sensor_poll_interval = float(_fxcorr_d['sensor_poll_interval'])
        except KeyError:
            self.logger.warn('sensor_poll_interval config file variable is not available, default interval set to: 0.003.')
            self.sensor_poll_interval = 0.003

        # These ones are fine, we'll just use a default if they're not there.
        self.katcp_port = int(_fxcorr_d.get('katcp_port', 7147))
        self.time_jitter_allowed = float(_fxcorr_d.get('time_jitter_allowed', 0.5))
        self.time_offset_allowed = float(_fxcorr_d.get('time_offset_allowed', 1))
        self.timeout = int(_fxcorr_d.get('default_timeout', 15))
        self.post_switch_delay = int(_fxcorr_d.get('switch_delay', 10))

        if 'spead_metapacket_ttl' in _fxcorr_d:
            import data_stream
            data_stream.SPEAD_PKT_TTL = int(_fxcorr_d['spead_metapacket_ttl'])

        # Derived values.
        self.analogue_bandwidth = self.sample_rate_hz/2

        # =====================================================================
        _feng_d = self.configd['fengine']

        # Can't continue without these values present.
        self.n_chans = int(_feng_d['n_chans'])
        # Not good enough that it's an int, has to actually be a supported mode.
        if self.n_chans not in [1024, 4096, 32768]:
            errmsg = "fengine n_chans - received invalid number: {}".format(self.n_chans)
            self.logger.error(errmsg)
            raise ValueError(errmsg)
        self.n_input_streams_per_fengine = int(_feng_d['n_input_streams_per_fengine'])
        self.fft_shift = int(_feng_d.get('fft_shift', None))

        # If these are not present, fill in defaults.
        self.decimation_factor = int(_feng_d.get('decimation_factor', 1))
        self.ct_readgap = int(_feng_d.get('ct_readgap', 45))
        self.min_load_time = float(_feng_d.get('min_load_time', 0.2))
        self.f_per_fpga = int(_feng_d.get('f_per_fpga', 2))
        self.adc_bitwidth = int(_feng_d.get('sample_bits', 10))
        self.pfb_group_delay = int(_feng_d.get('pfb_group_delay', 0))
        self.f_stream_payload_len = int(_feng_d.get('feng_stream_payload_len', 1024))

        # =====================================================================
        _xeng_d = self.configd['xengine']

        # Missing values here can be replaced with defaults.
        self.x_per_fpga = int(_xeng_d.get('x_per_fpga', 4))
        self.xeng_outbits = int(_xeng_d.get('xeng_outbits', 32))
        self.x_stream_payload_len = int(_xeng_d.get('xeng_stream_payload_len', 2048))

        # check if beamformer exists with x-engines
        try:
            _beam_d = self.configd['beam0']
        except KeyError:
            self.found_beamformer = False
            self.logger.info('No beamfomer found in the config.')
        else:
            self.found_beamformer = True
            self.beng_outbits = int(_beam_d['beng_outbits'])

            # currently, 64A1K beam has a different payload size
            _sixty_four_1k = (self.n_antennas == 64 and self.n_chans == 1024)
            default_b_eng_pkt_size = 2048 if _sixty_four_1k else 4096
            self.b_stream_payload_len = int(_beam_d.get('beam0_stream_payload_len', default_b_eng_pkt_size))

    def _read_config_file(self):
        """
        Read the instrument configuration from self.config_source.
        """
        self.configd = ReadOnlyDict(utils.parse_ini_file(self.config_source))

    def _read_config_server(self):
        """
        Get instance-specific setup information from a given katcp server.
        :return:
        """
        print(type(self.config_source))
        server = eval(self.config_source)[0]
        port = eval(self.config_source)[1]
        client = katcp.CallbackClient(server, port, auto_reconnect=True)
        client.setDaemon(True)
        client.start()
        res = client.wait_connected(1)
        if not res:
            raise katcp.KatcpClientError(
                'Can\'t connect to {}'.format(str(self.config_source)))
        msg = katcp.Message(katcp.Message.REQUEST, 'get-config')
        res, resp = client.blocking_request(msg)
        client.stop()
        if res.arguments[0] != 'ok':
            raise RuntimeError('Could not read config from corr2_servlet.')
        if res.arguments[1] == '':
            raise RuntimeError('corr2_servlet returned no config data.')
        tempdict = eval(res.arguments[1])
        tempdict2 = ReadOnlyDict(tempdict)
        self.configd = tempdict2
        self.logger.info('Read config from {} okay'.format(self.config_source))

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
        raise DeprecationWarning('I do not think this is used any longer?')
        if stream_name is None:
            streams = self.data_streams
        else:
            streams = [self.get_data_stream(stream_name)]
        for stream in streams:
            if hasattr(stream, 'metadata_issue'):
                stream.metadata_issue()
            else:
                self.logger.debug(
                    'SPEADStream {} is not a metadata stream'.format(
                        stream.name))

    def get_version_info(self):
        """
        Get the version information for this instrument.
        :return: a dict of items: [(name, (version, build-state)), ]
        """
        rv = {}
        for fname, fver in self.fops.get_version_info():
            rv['fengine_firmware_' + fname] = (fver, '')
        for fname, fver in self.xops.get_version_info():
            rv['xengine_firmware_' + fname] = (fver, '')
        for fname, fver in self.bops.get_version_info():
            rv['bengine_firmware_' + fname] = (fver, '')
        return rv

# end
