from __future__ import division
import logging
import time
import re
import math
import struct
import os.path
import numpy as np
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
    if string.startswith(prefix+'_'):
        return string[len(prefix)+1:]
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
        if not self.repeat_en_register.read()['data']['en']:
            return None
        return self.repeat_len_register.read()['data'][
            self.repeat_len_field_name]

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


class PulsarSource(Source):
    """

    """
    def __init__(self, freq_register, scale_register, name):
        """

        :param freq_register:
        :param scale_register:
        :param name:
        """
        super(PulsarSource, self).__init__(freq_register, name)
        self.freq_register = freq_register
        self.scale_register = scale_register
        # samples per second
        self.freq_sampling = float(self.parent.config['sample_rate_hz'])
        self.t_samp = 1/self.freq_sampling  # Time domain sample period
        self.fft_size = 1024  # size of FFT
        self.f_samp = self.freq_sampling/self.fft_size  # FFT bin width
        self.fft_period = self.fft_size * self.t_samp  # FFT period
        # [Hz] center frequency of passband (as received )
        self.freq_centre = float(self.parent.config['true_cf'])
        # duration of simulation
        self.sim_time = float(self.parent.config['pulsar_sim_time'])
        # number of FFT input blocks to process
        self.fft_blocks = math.ceil(self.sim_time/self.fft_period)
        self.n_samp = self.fft_blocks*self.fft_size  # number of samples
        self.raw_data = np.array([])
        freq_field = self.freq_register.field_get_by_name('frequency')
        self.nr_freq_steps = 2**freq_field.width_bits
        self.max_freq = self.freq_sampling / 2.
        self.delta_freq = self.max_freq / (self.nr_freq_steps - 1)
        self.dm = float(self.parent.config['pulsar_dm'])  # dispersion measure

    @property
    def frequency(self):
        return self.freq_register.read()['data']['frequency'] * self.delta_freq

    @property
    def scale(self):
        return self.scale_register.read()['data']['scale']

    def set(self, scale=None, frequency=None):
        """

        :param scale:
        :param frequency:
        :return:
        """
        if scale is not None:
            self.scale_register.write(scale=scale)
        if frequency is not None:
            freq_steps = int(round(frequency / self.delta_freq))
            self.freq_register.write(frequency=freq_steps)

    def _initialise_fft_bins(self):
        """
        FFT bin center frequencies (at baseband) [Hz]
        :return:
        """
        self.fft_bin = np.arange(-self.freq_sampling/2, self.freq_sampling/2,
                                 self.f_samp)

    def _initialise_start_freq(self):
        """
        start frequency (center freq of pulse at start of simulation) [Hz]
        :return:
        """
        self._initialise_fft_bins()
        self.fch1 = self.freq_centre + max(self.fft_bin)/2

    def _initialise_start_freq_delay(self):
        """
        Reference delay for start freq (f1) i.e. the shortest delay at
        the highest freq [s]
        :param dm: dispersion measure
        :return:
        """
        self._initialise_start_freq()
        self.dch1 = self.dm/(alpha*(self.fch1**2))

    def _initialise_delay_bins(self):
        """

        :param dm: dispersion measure
        :return:
        """
        self._initialise_start_freq_delay()
        fc = self.freq_centre
        df = self.f_samp
        f2 = fc + self.fft_bin - df/2
        t1 = self.dch1
        # [s] delay relative to t1 for lowest frequency in each bin
        tbin = (self.dm/(alpha*(f2**2))) - t1
        fbin = self.fft_bin
        lfft = self.fft_size
        # to simplify algorithm
        self.relative_delay = np.append(
            tbin, (self.dm/(alpha*((fc+fbin[lfft-1]+df/2)**2)))-t1)

    def initialise_data(self):
        """

        :param dm: dispersion measure
        :return:
        """
        self._initialise_delay_bins()
        self.raw_data = np.zeros(self.n_samples, dtype=np.complex64)

    def write_pulse_to_bin(self, duty_cycle=0.05, t=0):
        """

        :param duty_cycle: the fraction of the pulse period in which the
        pulse is actually on
        :param t: time
        :return: vector with delayed pulse
        """
        b = 0  # count bins
        beta = 1/math.log(2)  # constant
        tbin = self.relative_delay
        X = [0] * self.fft_size
        for f in range(len(self.fft_bin)):  # loop over FFT bins
            t2 = tbin[b+1]  # delay for max frequency in this bin
            # Gaussian shaped pulse
            X[b] = math.exp(-(t - t2)**2/(beta * duty_cycle ** 2))
            b += 1
        return X

    def write_impulse_to_bin(self, t=0):
        """

        :param t: time
        :return: vector with delayed pulse
        """
        b = 0  # count bins
        tbin = self.relative_delay
        X = [0] * self.fft_size
        fbin = self.fft_bin
        for f in range(len(fbin)):  # loop over FFT bins
            t2a = tbin[b+1]  # delay for max frequency in this bin
            t2b = tbin[b]  # delay for min frequency in this bin
            if t2b >= t > t2a:
                X[b] = 1  # impulse
            b += 1
        return X

    def fftshift(self, x):
        """
        FFT shift into screwy FFT order
        :param x:
        :return:
        """
        return np.fft.fftshift(x)

    def ifft(self, x):
        """
        Inverse FFT gives time domain
        :param x:
        :return:
        """
        return np.fft.ifft(x)

    def add_pulsar(self, duty_cycle=0.05):
        """

        :param duty_cycle: the fraction of the pulse period in which
        the pulse is actually on
        :return:
        """
        t = 0  # [s] initialize sim time
        k = 0
        lfft = self.fft_size
        while k < self.fft_blocks:
            k += 1
            X = self.write_pulse_to_bin(duty_cycle, t)
            t += self.fft_period  # update time
            X = self.fftshift(X)
            x = self.ifft(X)*lfft
            self.raw_data[(k-1)*lfft:k*lfft] = x

    def write_file(self, file_name='test', path_name=False):
        """

        :param file_name:
        :param path_name:
        :return:
        """
        if path_name:
            complete_name = os.path.join(path_name, file_name)
        else:
            complete_name = file_name
        xs = self.raw_data
        p_amp = 1  # amplitude of the pulse in time domain
        max_xs = max(np.absolute(xs))
        with open(complete_name, 'ab') as myfile:
            for l in range(len(xs)):
                xr = int(round(10*(p_amp*np.real(xs[l]) / max_xs +
                                   np.random.standard_normal())))
                xi = int(round(10*(p_amp*np.imag(xs[l]) / max_xs +
                                   np.random.standard_normal())))
                mybuffer = struct.pack("bb", xr, xi)
                myfile.write(mybuffer)

    def plot(self, file_name='test', path_name=False):
        """

        :param file_name:
        :param path_name:
        :return:
        """
        if path_name:
            complete_name = os.path.join(path_name, file_name)
        else:
            complete_name = file_name
        with open(complete_name, 'rb') as fh:
            loaded_array = np.frombuffer(fh.read(), dtype=np.int8)
        xr = loaded_array[0:len(loaded_array)-1:2]
        xi = loaded_array[1:len(loaded_array):2]
        c_x = xr + xi*1j
        fc = self.freq_centre
        fbin = self.fft_bin
        lfft = self.fft_size
        p1 = 1
        power_array = np.zeros((lfft, len(c_x)/lfft))
        for p in range(len(c_x)/lfft):
            power = np.abs(np.fft.fft(c_x[(p1-1)*lfft:p1*lfft], lfft))**2
            p1 += 1
            print('p1 = %d' % p1)
            power_array[:, p] = power
        power_array = np.fliplr(power_array)
        plt.imshow(power_array, extent=[0, self.sim_time, fc-max(fbin),
                                        fc+max(fbin)], aspect='auto')
        plt.show()


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

    def get_system_information(self, filename=None, fpg_info=None):
        """
        Get system information and build D-engine sources
        :param filename:
        :param fpg_info:
        :return:
        """
        FpgaHost.get_system_information(
            self, filename=filename, fpg_info=fpg_info)
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
                repeat_len_reg_name = 'rpt_length_cwg' + scale_reg_postfix
                repeat_en_reg = getattr(self.registers,
                                        repeat_en_reg_name, None)
                repeat_len_reg = getattr(self.registers,
                                         repeat_len_reg_name, None)
                repeat_len_field_name = 'cwg' + scale_reg_postfix + \
                                        '_repeat_length'
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
                scale_reg = getattr(self.registers, 'scale_pulsar' +
                                    scale_reg_postfix)
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
            LOGGER.info('Not programming host {} since no bitstream is '
                        'configured'.format(self.host))
        if not self.is_running():
            raise RuntimeError('D-engine {host} not '
                               'running'.format(**self.__dict__))
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
        self.registers.pol_traffic_trigger.write(
            **{n: 'pulse' for n in reg_field_names})

    def _program(self):
        """
        Program the bitstream to fpga and ensure 10GbE's are not transmitting
        """
        LOGGER.info('Programming Dsim roach {host} with file {bitstream}'
                    .format(**self.__dict__))
        stime = time.time()
        self.upload_to_ram_and_program(self.bitstream)
        LOGGER.info('Programmed %s in %.2f seconds.' % (
            self.host, time.time() - stime))
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
                self.write_int('gbe_iptx%1i' % txid,
                               IpAddress.str2ip('%s.%d' % (pol_prefix, txip)))
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
            raise RuntimeError('D-engine with no 10gbe cores %s' % self.host)
        gbes_per_pol = 2        # Hardcoded assumption
        num_pols = num_gbes // gbes_per_pol
        mac_ctr = 1
        for ctr in range(num_gbes):
            this_mac = Mac.from_roach_hostname(self.host, mac_ctr)
            self.gbes['gbe%d' % ctr].setup(
                mac=this_mac, ipaddress='0.0.0.0', port=port)
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
                LOGGER.info('%s sending to: %s.%d port %d' % (
                    self.host, txaddr_prefix, txip, port))
                self.write_int(
                    'gbe_iptx%i' % gbe_ctr,
                    IpAddress.str2ip('%s.%d' % (txaddr_prefix, txip)))
                if not single_destination:
                    addr_offset += 1
                gbe_ctr += 1
        self.write_int('gbe_porttx', port)
        self.registers.control.write(gbe_rst=False)

# end
