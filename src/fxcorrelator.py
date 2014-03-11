# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
LOGGER = logging.getLogger(__name__)

from misc import log_runtime_error
import instrument, katcp_client_fpga, fengine, xengine, types

import struct, socket, iniparse

class FxCorrelator(instrument.Instrument):
    '''
    An FxCorrelator implemented using FPGAs running BOF files for processing hosts.
    '''
    def __init__(self, name, description, config_file, connect):
        '''
        Constructor
        @param name: The instrument's unique name.
        @param description: A brief description of the correlator.
        @param config_file: An XML/YAML/ini config file describing the correlator.
        @param connect: True/False, should the a connection be established to the instrument after setup.
        '''
        super(FxCorrelator, self).__init__(name=name, description=description)

        # process config
        self.parse_config(config_file)

        # set up and calculate necessary params
#         self.set_up()

        # set up loggers

        # spead transmitter

        # connect to nodes - check katcp connections

        self.fhosts = {}
        self.xhosts = {}

        if connect:
            self.connect()

    def initialise(self):
        '''Initialise the FX correlator.
        '''
        raise NotImplementedError

    def check_katcp_connections(self):
        '''Ping all the nodes in this correlator to see if katcp connections are functioning.
        '''
        results = self.node_ping()
        for res in results.values():
            if not res:
                return False
        return True

    def __getattribute__(self, name):
        '''Overload __getattribute to make shortcuts for getting object data.
        '''
        if name == 'hosts':
            tmp = {}
            tmp.update(self.fhosts)
            tmp.update(self.xhosts)
            return tmp
        elif name == 'fengines':
            return self.engine_get(engine_id=None, engine_class=fengine.Fengine)
        elif name == 'xengines':
            return self.engine_get(engine_id=None, engine_class=xengine.Xengine)
        return object.__getattribute__(self, name)

    def parse_config(self, filename):
        '''Parse an XML/YAML config file for this correlator.
        @param filename: The filename for the config file.
        '''
        if filename == '':
            log_runtime_error(LOGGER, 'No config file provided.')
            return
        try:
            fptr = open(filename, 'r')
        except:
            raise IOError('Configuration file \'%s\' cannot be opened.' % filename)
        self.config_file = filename
        LOGGER.info('Using config file %s.', self.config_file)
        config_parser = iniparse.INIConfig(fptr)

        # some helper functions
        def cfg_set_string(section, param, overwrite=False):
            if self.config.has_key(param) and (not overwrite):
                log_runtime_error(LOGGER, 'Attempting to overwrite config variable \'%s\'' % param)
            try:
                self.config[param] = config_parser[section][param]
            except KeyError:
                log_runtime_error(LOGGER, 'Config asked for unknown param - %s/%s' % (section, param))
            if isinstance(self.config[param], iniparse.config.Undefined):
                log_runtime_error(LOGGER, 'Config asked for unknown param - %s/%s' % (section, param))
        def cfg_set_int(section, param, overwrite=False):
            cfg_set_string(section, param, overwrite)
            self.config[param] = int(self.config[param])
        def cfg_set_float(section, param, overwrite=False):
            cfg_set_string(section, param, overwrite)
            self.config[param] = float(self.config[param])

        # some constants
        self.config['pol_map'] = {'x':0, 'y':1}
        self.config['rev_pol_map'] = {0:'x', 1:'y'}
        self.config['pols'] = ['x', 'y']

        # check for bof names
        cfg_set_string('files', 'bitstream_f')
        cfg_set_string('files', 'bitstream_x')
        LOGGER.info('Using bof files F(%s) X(%s).', self.config['bitstream_f'], self.config['bitstream_x'])

        # read f and x host lists and create the basic FPGA hosts
        cfg_set_string('katcp', 'hosts_f')
        cfg_set_string('katcp', 'hosts_x')
        cfg_set_int('katcp', 'katcp_port')
        self.create_hosts()
        self.probe_fhosts()
        self.probe_xhosts()

        # other common correlator parameters
        cfg_set_int('correlator', 'pcnt_bits')
        cfg_set_int('correlator', 'mcnt_bits')
        cfg_set_int('correlator', 'n_chans')

        # f-engine
        cfg_set_int('correlator', 'adc_levels_acc_len')
        #cfg_set_int('correlator', 'adc_bits')                    # READ FROM F
        cfg_set_int('correlator', 'n_ants')
        #cfg_set_int('correlator', 'adc_clk')                     # READ FROM F
        cfg_set_int('correlator', 'n_ants_per_xaui')
        #cfg_set_float('correlator', 'ddc_mix_freq')              # READ FROM F
        #cfg_set_int('correlator', 'ddc_decimation')              # READ FROM F
        #cfg_set_int('correlator', 'feng_bits')                   # READ FROM F
        #cfg_set_int('correlator', 'feng_fix_pnt_pos')            # READ FROM F
        #cfg_set_string('correlator', 'feng_out_type')            # READ FROM F
        #cfg_set_int('correlator', 'n_xaui_ports_per_ffpga')      # READ FROM F
        #cfg_set_int('correlator', 'feng_sync_period')            # READ FROM F
        #cfg_set_int('correlator', 'feng_sync_delay')             # READ FROM F

        # x-engine
        #cfg_set_int('correlator', 'x_per_fpga')                  # READ FROM X
        #cfg_set_int('correlator', 'acc_len')                     # READ FROM X
        #cfg_set_int('correlator', 'xeng_acc_len')                # READ FROM X
        #cfg_set_int('correlator', 'xeng_clk')                    # READ FROM X
        #cfg_set_string('correlator', 'xeng_format')              # READ FROM X
        #cfg_set_int('correlator', 'n_xaui_ports_per_xfpga')      # READ FROM X

        #cfg_set_int('correlator','sync_time') #moved to /var/run/...

        print self.config
        return

        # 10gbe ports
        if self.config['feng_out_type'] == '10gbe':
            cfg_set_int('correlator', '10gbe_port')
            cfg_set_int('correlator', '10gbe_pkt_len')
            cfg_set_string('correlator', '10gbe_ip')
            self.config['10gbe_ip_int'] = struct.unpack('>I', socket.inet_aton(self.config['10gbe_ip']))[0]
            LOGGER.info('10GbE IP address is %s, %i', self.config['10gbe_ip'], self.config['10gbe_ip_int'])

        print self.config

    def calculate_integration_time(self):
        '''Calcuate the number of accumulations and integration time for this system.
        '''
        self.config['n_accs'] = self.config['acc_len'] * self.config['xeng_acc_len']
        self.config['int_time'] = float(self.config['n_chans']) * self.config['n_accs'] / self.config['bandwidth']

    def calculate_bandwidth(self):
        '''Determine the bandwidth the system is processing.
        The ADC on the running system must report how much bandwidth it is processing.
        '''
        self.config['rf_bandwidth'] = self.config['adc_clk'] / 2.
        # ask the f-engines how much bandwidth they are processing
        #self.fengines[0].get_bandwidth()

        MODE_WB = 0
        MODE_NB = 1
        self.config['mode'] = MODE_WB

        # is a DDC being used in the F engine?
        if self.config['ddc_mix_freq'] > 0:
            if self.config['mode'] == MODE_WB:
                self.config['bandwidth'] = float(self.config['adc_clk']) / self.config['ddc_decimation']
                self.config['center_freq'] = float(self.config['adc_clk']) * self.config['ddc_mix_freq']
            else:
                raise RuntimeError("Undefined for other modes.")
        else:
            if self.config['mode'] == MODE_WB:
                self.config['bandwidth'] = self.config['adc_clk'] / 2.
                self.config['center_freq'] = self.config['bandwidth'] / 2.
            elif self.config['mode'] == MODE_NB:
                self.config['bandwidth'] = (self.config['adc_clk'] / 2.) / self.config['coarse_chans']
                self.config['center_freq'] = self.config['bandwidth'] / 2.
            else:
                raise RuntimeError("Undefined for other modes.")

    def probe_fhosts(self):
        '''Read information from the F-host hardware.
        '''
        host = self.fhosts.values()[0]
        print self.fhosts.values()

        #host.progdev()
        host.process_new_core_info('/home/paulp/projects/code/c05f12_01_2013_Sep_20_1548_info.xml')

#         # retrieve selected info from the programmed device
#         self.config['feng_sync_period'] = host.system_info['feng_sync_period']
#         self.config['f_xaui_ports'] = host.system_info['xaui_ports']
#         self.config['feng_sync_delay'] = host.system_info['feng_sync_delay']

    def probe_xhosts(self):
        '''Read information from the X-host hardware.
        '''
        host = self.xhosts.values()[0]
        print self.xhosts.values()

        #host.progdev()
        host.process_new_core_info('/home/paulp/projects/code/c05f12_01_2013_Sep_20_1548_info.xml')

#         # retrieve selected info from the programmed device
#         self.config['xeng_out_type'] = host.system_info['xeng_out_type']
#         self.config['x_per_fpga'] = host.system_info['x_per_fpga']
#         self.config['x_xaui_ports_per_fpga'] = host.system_info['xaui_ports_per_fpga']
#         self.config['x_clock'] = host.system_info['clock']

    def setup(self):
        '''Perform any remaining startup and setup after configuration has been done.
        '''
        self.calculate_bandwidth()
        self.calculate_integration_time()

    def create_hosts(self, program=True):
        '''Create the Hosts that make up this FX correlator.
        '''
        if (self.config['hosts_f'] == None) or (self.config['hosts_x'] == None):
            log_runtime_error(LOGGER, 'Must have string describing F and X nodes.')
        self.config['hosts_f'] = self.config['hosts_f'].split(types.LISTDELIMIT)
        self.config['hosts_x'] = self.config['hosts_x'].split(types.LISTDELIMIT)
        self.fhosts = {}
        self.xhosts = {}
        for hostconfig, hostbitstream, hostdict in [[self.config['hosts_f'], self.config['bitstream_f'], self.fhosts], [self.config['hosts_x'], self.config['bitstream_x'], self.xhosts]]:
            for hostname in hostconfig:
                host = katcp_client_fpga.KatcpClientFpga(hostname, self.config['katcp_port'])
                host.set_bof(hostbitstream)
                hostdict[host.host] = host
        LOGGER.info('Created %i hosts.', len(self.hosts))
        if program:
            for host in self.fhosts:
                host.progdev()
            for host in self.xhosts:
                host.progdev()
        LOGGER.info('Programmed %i hosts.', len(self.hosts))

    def connect(self):
        '''Connect to the correlator and test connections to all the nodes.
        '''
        raise NotImplementedError

# end
