from __future__ import division

import logging
import time
import re

from casperfpga.attribute_container import AttributeContainer
from casperfpga import tengbe

from corr2.host_fpga import FpgaHost

LOGGER = logging.getLogger(__name__)

def get_prefixed_name(prefix, string):
    if not string.startswith(prefix):
        return None
    if string.startswith(prefix+'_'):
        return string[len(prefix)+1:]
    else:
        return string[len(prefix):]

def remove_nones(write_vars):
    return {k:v for k, v in write_vars.items() if v is not None}

class Source(object):
    def __init__(self, register, name):
        self.register = register
        self.parent = register.parent
        self.name = name

class SineSource(Source):
    def __init__(self, register, name):
        super(SineSource, self).__init__(register, name)
        self.sample_rate_hz = float(self.parent.config['sample_rate_hz'])
        freq_field = self.register.field_get_by_name('frequency')
        self.nr_freq_steps = 2**(freq_field.width_bits)
        self.max_freq = self.sample_rate_hz / 2.
        self.delta_freq = self.max_freq / (self.nr_freq_steps - 1)

    @property
    def frequency(self):
        return self.register.read()['data']['frequency'] * self.delta_freq

    @property
    def scale(self):
        return self.register.read()['data']['scale']

    def set(self, scale=None, frequency=None):
        freq_steps = (int(round(frequency / self.delta_freq))
                      if frequency is not None else None)
        write_vars = remove_nones(dict(scale=scale, frequency=freq_steps))
        self.register.write(**write_vars)

class NoiseSource(Source):
    @property
    def scale(self):
        return self.register.read()['data']['scale']

    def set(self, scale=None):
        # TODO work in 'human' units such W / Hz?
        write_vars = remove_nones(dict(scale=scale))
        self.register.write(**write_vars)

class Output(object):
    def __init__(self, name, scale_register, control_register):
        self.name = name
        self.scale_register = scale_register
        self.control_register = control_register
        self.tgv_select_field = 'tvg_select' + self.name

    @property
    def output_type(self):
        """Curently selected output type"""
        if self.control_register.read()[
            'data'][self.tgv_select_field] == 0:
            return 'test_vectors'
        else:
            return 'signal'

    def select_output(self, output_type):
        if output_type == 'test_vectors':
            self.control_register.write(**{self.tgv_select_field: 0})
        elif output_type == 'signal':
            self.control_register.write(**{self.tgv_select_field: 1})
        else:
            raise ValueError(
                'Valid output_type values: "test_vectors" and "signal"')

    def scale_output(self, scale):
        self.scale_register.write(scale=scale)

class FpgaDsimHost(FpgaHost):
    def __init__(self, host, katcp_port=7147, boffile=None, connect=True, config=None):
        if config:
            if boffile:
                raise ValueError('Cannot specify "boffile" parameter if config is used')
            boffile = config['bitstream']
        self.config = config
        FpgaHost.__init__(
            self, host, katcp_port=katcp_port, boffile=boffile, connect=connect)
        self.boffile = boffile
        self.sine_sources = AttributeContainer()
        self.noise_sources = AttributeContainer()
        self.outputs = AttributeContainer()

    def get_system_information(self, filename=None, fpg_info=None):
        """Get system information and build D-engine sources"""
        FpgaHost.get_system_information(self, filename=filename, fpg_info=fpg_info)
        self.sine_sources.clear()
        self.noise_sources.clear()
        self.outputs.clear()
        for reg in self.registers:
            sin_name = get_prefixed_name('freq_cwg', reg.name)
            noise_name = get_prefixed_name('scale_wng', reg.name)
            output_scale_name = get_prefixed_name('scale_out', reg.name)
            if sin_name is not None:
                setattr(self.sine_sources, 'sin_'+ sin_name, SineSource(reg, sin_name))
            elif noise_name is not None:
                setattr(self.noise_sources, 'noise_' + noise_name,
                        NoiseSource(reg, noise_name))
            elif output_scale_name is not None:
                setattr(self.outputs, 'out_' + output_scale_name,
                        Output(output_scale_name, reg, self.registers.control))

    def initialise(self):
        """Program (if self.boffile is specified) and init Dsim roach"""
        if not self.is_connected():
            self.connect()
        if self.boffile:
            self._program()
        else:
            LOGGER.info('Not programming host {} since no boffile is configured'
                        .format(self.host))
        if not self.is_running():
            raise RuntimeError('D-engine {host} not running'
                               .format(**self.__dict__))
        self.get_system_information()
        self.setup_tengbes()
        # Set digitizer polarisation IDs, 0 - h, 1 - v
        self.registers.receptor_id.write(pol0_id=0, pol1_id=1)
        self.data_resync()
        # Default to generating test-vectors
        for output in self.outputs:
            output.select_output('test_vectors')

    def reset(self):
        self.registers.control.write(mrst='pulse')

    def data_resync(self):
        """start the local timer on the test d-engine - mrst, then a fake sync"""
        self.reset()
        self.registers.control.write(msync='pulse')

    def enable_data_output(self, enabled=True):
        """(dis)Enable 10GbE data output"""
        enabled = bool(enabled)
        pol_tx_reg = self.registers.pol_tx_always_on
        reg_vals = {n: enabled for n in pol_tx_reg.field_names()
                    if n.endswith('_tx_always_on')}
        pol_tx_reg.write(**reg_vals)
        if enabled:
            self.registers.control_output.write(load_en_time='pulse')

    def pulse_data_output(self, no_packets):
        """Produce a data output pulse of no_packets per polarisation

        Does nothing if data is already being transmitted
        """
        num_regs = [r for r in self.registers if re.match(
            r'^pol\d_num_pkts$', r.name)]
        for r in num_regs:
            r.write(**{r.name: no_packets})
        self.registers.pol_traffic_trigger.write(**{
            n: 'pulse' for n in self.registers.pol_traffic_trigger.field_names()})

    def _program(self):
        """Program the boffile to fpga and ensure 10GbE's are not transmitting"""
        LOGGER.info('Programming Dsim roach {host} with file {boffile}'
                    .format(**self.__dict__))
        stime = time.time()
        self.upload_to_ram_and_program(self.boffile)
        LOGGER.info('Programmed %s in %.2f seconds.' % (
            self.host, time.time() - stime))
        # Ensure data is not sent before the tengbe's are configured
        self.enable_data_output(False)

    def setup_tengbes(self):
        """Set up 10GbE MACs, IPs and destination address/port"""
        start_ip = self.config['10gbe_start_ip']
        start_mac = self.config['10gbe_start_mac']
        port = int(self.config['10gbe_port'])
        num_tengbes = 4         # Hardcoded assumption
        gbes_per_pol = 2        # Hardcoded assumption
        num_pols = num_tengbes // gbes_per_pol

        ip_bits = start_ip.split('.')
        ipbase = int(ip_bits[3])
        mac_bits = start_mac.split(':')
        macbase = int(mac_bits[5])
        for ctr in range(num_tengbes):
            mac = '%s:%d' % (':'.join(mac_bits[0:5]), macbase + ctr)
            ip = '%s.%s.%s.%d' % (ip_bits[0], ip_bits[1], ip_bits[2], ipbase + ctr)
            self.tengbes['gbe%d' % ctr].setup(mac=mac, ipaddress=ip, port=port)
        for gbe in self.tengbes:
            gbe.tap_start(True)

        # set the destination IP and port for the tx
        gbe_ctr = 0             # pol-global counter for gbe's
        for pol in range(0, num_pols):
            # Get address configuration for current polarisation
            single_destination = int(self.config.get(
                'pol{}_single_destination'.format(pol), 0))
            txaddr_start = self.config['pol{}_destination_start_ip'.format(pol)]
            txaddr_bits = txaddr_start.split('.')
            txaddr_base = int(txaddr_bits[3])
            txaddr_prefix = '.'.join(txaddr_bits[0:3])

            # Set the gbe destination addres for each gbe used by this pol
            addr_offset = 0
            for pol_gbe_ctr in range(0, gbes_per_pol):
                txip = txaddr_base + addr_offset
                LOGGER.info('%s sending to: %s.%d port %d' % (
                    self.host, txaddr_prefix, txip, port))
                self.write_int('gbe_iptx%i' % gbe_ctr,
                               tengbe.IpAddress.str2ip(
                                   '%s.%d' % (txaddr_prefix, txip)))
                if not single_destination:
                    addr_offset += 1

                gbe_ctr += 1

        self.write_int('gbe_porttx', port)
        self.registers.control.write(gbe_rst=False)
