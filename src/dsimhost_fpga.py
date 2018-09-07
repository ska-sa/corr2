from __future__ import division
import logging
import math
import numpy as np
import os.path
import re
import struct
import time
import matplotlib.pyplot as plt

from casperfpga.attribute_container import AttributeContainer
from casperfpga.network import Mac, IpAddress
from casperfpga.transport_skarab import SkarabTransport

from host_fpga import FpgaHost
from utils import parse_ini_file

LOGGER = logging.getLogger(__name__)

# for DM in [pc cm ^{ -3}] , time in [s] , and frequency in [Hz]
alpha = 2.410e-16


def get_prefixed_name(prefix, string):
    if not string.startswith(prefix):
        return None
    if string.startswith(prefix + '_'):
        return string[len(prefix) + 1:]
    else:
        return string[len(prefix):]


def remove_nones(write_vars):
    return {k: v for k, v in write_vars.items() if v is not None}


class Source(object):
    def __init__(self, register, name):
        self.parent = register.parent
        self.name = name


class SineSource(Source):
    """

    """

    def __init__(self, freq_register, scale_register, name,
                 repeat_en_register=None,
                 repeat_len_register=None, repeat_len_field_name=None):
        """

        :param freq_register:
        :param scale_register:
        :param name:
        :param repeat_en_register:
        :param repeat_len_register:
        :param repeat_len_field_name:
        """
        super(SineSource, self).__init__(freq_register, name)
        self.freq_register = freq_register
        self.scale_register = scale_register
        self.repeat_len_register = repeat_len_register
        self.repeat_len_field_name = repeat_len_field_name
        self.repeat_en_register = repeat_en_register
        self.sample_rate_hz = float(self.parent.config['sample_rate_hz'])
        freq_field = self.freq_register.field_get_by_name('frequency')
        self.nr_freq_steps = 2**freq_field.width_bits
        self.max_freq = self.sample_rate_hz / 2.0
        self.delta_freq = self.max_freq / (self.nr_freq_steps - 1)

    @property
    def frequency(self):
        return self.freq_register.read()['data']['frequency'] * self.delta_freq

    @property
    def scale(self):
        return self.scale_register.read()['data']['scale']

    @property
    def repeat(self):
        if self.repeat_len_register is None or self.repeat_en_register is None:
            return None
        else:
            return self.repeat_len_register.read()['data'][self.repeat_len_field_name]

    def set(self, scale=None, frequency=None, repeat_n=None):
        """Set source parameters

        Keyword Arguments
        ----------------
        scale : float, 0 to 1
            Scaling factor for source
        frequency : float in Hz
            Frequency of source, from 0 to the Nyquist freq
        repeat_n : int
            Forces output to be periodic every N samples, or disables repeat
            if set to 0

        """
        if scale is not None:
            self.scale_register.write(scale=scale)
        if frequency is not None:
            freq_steps = int(round(frequency / self.delta_freq))
            self.freq_register.write(frequency=freq_steps)
        if repeat_n is not None:
            if self.repeat_len_register is None:
                raise NotImplementedError(
                    'Required repeat length register not found')
            if self.repeat_len_field_name is None:
                raise NotImplementedError(
                    'Required repeat length field name not specified')
            if self.repeat_en_register is None:
                raise NotImplementedError(
                    'Required repeat enable register not found')
            repeat_n = int(repeat_n)
            self.repeat_len_register.write(**{
                self.repeat_len_field_name: repeat_n})
            if repeat_n == 0:
                self.repeat_en_register.write(en=0)
            else:
                self.repeat_en_register.write(en=1)


class NoiseSource(Source):
    def __init__(self, scale_register, name):
        self.scale_register = scale_register
        super(NoiseSource, self).__init__(scale_register, name)

    @property
    def scale(self):
        return self.scale_register.read()['data']['scale']

    def set(self, scale=None):
        # TODO work in 'human' units such W / Hz?
        write_vars = remove_nones(dict(scale=scale))
        self.scale_register.write(**write_vars)


class Output(object):
    """

    """

    def __init__(self, name, scale_register, control_register):
        """

        :param name:
        :param scale_register:
        :param control_register:
        """
        self.name = name
        self.scale_register = scale_register
        self.control_register = control_register
        self.tgv_select_field = 'tvg_select' + self.name

    @property
    def output_type(self):
        """
        Curently selected output type
        :return:
        """
        if self.control_register.read()['data'][self.tgv_select_field] == 0:
            return 'test_vectors'
        else:
            return 'signal'

    @property
    def scale(self):
        return self.scale_register.read()['data']['scale']

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
    """
    An FpgaHost that acts as a Digitiser unit.
    """

    def __init__(self, host, katcp_port=7147, bitstream=None,
                 connect=True, config=None, config_file=None):
        """

        :param host:
        :param katcp_port:
        :param bitstream:
        :param connect:
        :param config:
        """
        FpgaHost.__init__(self, host=host, katcp_port=katcp_port)
        if config is not None and config_file is not None:
            LOGGER.warn('config file and config supplied, defaulting to config')
        self.config = config or parse_ini_file(config_file)['dsimengine']
        self.bitstream = bitstream
        self.sine_sources = AttributeContainer()
        self.noise_sources = AttributeContainer()
        self.pulsar_sources = AttributeContainer()
        self.outputs = AttributeContainer()

    def get_system_information(self, filename=None, fpg_info=None, **kwargs):
        """
        Get system information and build D-engine sources
        :param filename:
        :param fpg_info:
        :return:
        """
        FpgaHost.get_system_information(
            self, filename=filename, fpg_info=fpg_info, **kwargs)
        self.sine_sources.clear()
        self.noise_sources.clear()
        self.pulsar_sources.clear()
        self.outputs.clear()
        for reg in self.registers:
            sin_name = get_prefixed_name('freq_cwg', reg.name)
            noise_name = get_prefixed_name('scale_wng', reg.name)
            pulsar_name = get_prefixed_name('freq_pulsar', reg.name)
            output_scale_name = get_prefixed_name('scale_out', reg.name)
            if sin_name is not None:
                scale_reg_postfix = ('_' + sin_name if reg.name.endswith(
                    '_' + sin_name) else sin_name)
                scale_reg = getattr(self.registers, 'scale_cwg' +
                                    scale_reg_postfix)
                repeat_en_reg_name = 'rpt_en_cwg' + scale_reg_postfix
                repeat_len_reg_name = 'rpt_length_cwg{}'.format(scale_reg_postfix)
                repeat_en_reg = getattr(self.registers,
                                        repeat_en_reg_name, None)
                repeat_len_reg = getattr(self.registers,
                                         repeat_len_reg_name, None)
                repeat_len_field_name = 'repeat_length'
                setattr(self.sine_sources, 'sin_' + sin_name, SineSource(
                    reg, scale_reg, sin_name,
                    repeat_len_register=repeat_len_reg,
                    repeat_en_register=repeat_en_reg,
                    repeat_len_field_name=repeat_len_field_name))
            elif noise_name is not None:
                setattr(self.noise_sources, 'noise_' + noise_name,
                        NoiseSource(reg, noise_name))
            elif pulsar_name is not None:
                scale_reg_postfix = ('_' + pulsar_name if reg.name.endswith(
                    '_' + pulsar_name) else pulsar_name)
                scale_reg = getattr(self.registers, 'scale_pulsar' + scale_reg_postfix)
                setattr(self.pulsar_sources, 'pulsar_' + pulsar_name,
                        PulsarSource(reg, scale_reg, pulsar_name))
            elif output_scale_name is not None:
                # TODO TEMP hack due to misnamed register
                if output_scale_name.startswith('arb'):
                    continue
                setattr(self.outputs, 'out_' + output_scale_name,
                        Output(output_scale_name, reg, self.registers.control))

    def initialise(self):
        """
        Program (if self.bitstream is specified) and init Dsim host
        :return:
        """
        if not self.is_connected():
            self.connect()
        if self.bitstream:
            self._program()
        else:
            LOGGER.info('Not programming host {} since no bitstream is configured'.format(self.host))
        if not self.is_running():
            raise RuntimeError('D-engine {host} not running'.format(**self.__dict__))
        self.get_system_information(self.bitstream)
        self.setup_gbes()
        # Set digitizer polarisation IDs, 0 - h, 1 - v
        self.registers.receptor_id.write(pol0_id=0, pol1_id=1)
        self.data_resync()
        # Default to generating test-vectors
        for output in self.outputs:
            output.select_output('test_vectors')

    def reset(self):
        self.registers.control.write(mrst='pulse')

    def data_resync(self):
        """
        Start the local timer on the test d-engine - mrst, then a fake sync
        """
        self.reset()
        self.registers.control.write(msync='pulse')

    def enable_data_output(self, enabled=True):
        """
        En/disable 10GbE data output
        """
        enabled = bool(enabled)
        pol_tx_reg = self.registers.pol_tx_always_on
        reg_vals = {n: enabled for n in pol_tx_reg.field_names()
                    if n.endswith('_tx_always_on')}
        pol_tx_reg.write(**reg_vals)
        if 'gbe_control' in self.registers.names():
            self.registers.gbe_control.write_int(15 if enabled else 0)
        elif 'gbecontrol' in self.registers.names():
            self.registers.gbecontrol.write_int(15 if enabled else 0)
        if enabled:
            self.registers.control_output.write(load_en_time='pulse')

    def pulse_data_output(self, no_packets):
        """
        Produce a data output pulse of no_packets per polarisation

        Does nothing if data is already being transmitted
        """
        num_regs = [
            r for r in self.registers if re.match(r'^pol\d_num_pkts$', r.name)
        ]
        for r in num_regs:
            r.write(**{r.name: no_packets})
        reg_field_names = self.registers.pol_traffic_trigger.field_names()
        self.registers.pol_traffic_trigger.write(**{n: 'pulse' for n in reg_field_names})

    def _program(self):
        """
        Program the bitstream to fpga and ensure 10GbE's are not transmitting
        """
        LOGGER.info('Programming Dsim roach {host} with file {bitstream}'.format(**self.__dict__))
        stime = time.time()
        self.upload_to_ram_and_program(self.bitstream)
        LOGGER.info('Programmed {} in {:.2f} seconds.'.format(self.host, time.time() - stime))
        # Ensure data is not sent before the gbes are configured
        self.enable_data_output(False)

    def setup_gbes_skarab(self):
        """
        Set up the 40gbe core on a SKARAB DSIM
        :return:
        """
        port = int(self.config['10gbe_port'])
        gbe = self.gbes[self.gbes.names()[0]]
        if gbe.get_port() != port:
            gbe.set_port(port)
        self.write_int('gbe_porttx', port)
        for pol in [0, 1]:
            pol_start = self.config['pol%1i_destination_start_ip' % pol]
            pol_bits = pol_start.split('.')
            pol_base = int(pol_bits[3])
            pol_prefix = '.'.join(pol_bits[0:3])
            for polstream in [0, 1]:
                txip = pol_base + polstream
                txid = (pol * 2) + polstream
                self.write_int('gbe_iptx%1i' % txid, IpAddress.str2ip('{}.{}'.format(pol_prefix, txip)))
        self.registers.control.write(gbe_rst=False)

    def setup_gbes(self):
        """
        Set up 10GbE MACs, IPs and destination address/port
        """

        if isinstance(self.transport, SkarabTransport):
            return self.setup_gbes_skarab()
        port = int(self.config['10gbe_port'])
        num_gbes = len(self.gbes)
        if num_gbes < 1:
            raise RuntimeError('D-engine with no 10gbe cores {}'.format(self.host))
        gbes_per_pol = 2        # Hardcoded assumption
        num_pols = num_gbes // gbes_per_pol
        mac_ctr = 1
        for ctr in range(num_gbes):
            this_mac = Mac.from_roach_hostname(self.host, mac_ctr)
            self.gbes['gbe{}'.format(ctr)].setup(mac=this_mac, ipaddress='0.0.0.0', port=port)
            mac_ctr += 1
        for gbe in self.gbes:
            gbe.dhcp_start()
        # set the destination IP and port for the tx
        gbe_ctr = 0             # pol-global counter for gbes
        for pol in range(0, num_pols):
            # Get address configuration for current polarisation
            single_destination = int(self.config.get(
                'pol{}_single_destination'.format(pol), 0))
            txaddr_start = self.config['pol{}_destination_start_ip'.format(pol)]
            txaddr_bits = txaddr_start.split('.')
            txaddr_base = int(txaddr_bits[3])
            txaddr_prefix = '.'.join(txaddr_bits[0:3])

            # Set the gbe destination address for each gbe used by this pol
            addr_offset = 0
            for pol_gbe_ctr in range(0, gbes_per_pol):
                txip = txaddr_base + addr_offset
                LOGGER.info('{} sending to: {}.{} port {}'.format(self.host, txaddr_prefix, txip, port))
                self.write_int('gbe_iptx{}'.format(gbe_ctr), IpAddress.str2ip('{}.{}'.format(
                    txaddr_prefix, txip)))
                if not single_destination:
                    addr_offset += 1
                gbe_ctr += 1
        self.write_int('gbe_porttx', port)
        self.registers.control.write(gbe_rst=False)

# end
