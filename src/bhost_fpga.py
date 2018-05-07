"""
A BHost is an extension of an XHost. It contains memory and registers
to set up and control one or more beamformers.

Author: Jason Manley, Andrew Martens, Ruby van Rooyen, Monika Obrocka
"""

import logging
import time

from xhost_fpga import FpgaXHost
from casperfpga.CasperLogHandlers import CasperConsoleHandler

LOGGER = logging.getLogger(__name__)


class FpgaBHost(FpgaXHost):
    def __init__(self, host, index, katcp_port=7147, bitstream=None,
                 connect=True, config=None, **kwargs):
        # parent constructor
        FpgaXHost.__init__(self, host, index, katcp_port=katcp_port,
                           bitstream=bitstream, connect=connect, config=config, **kwargs)
        try:
            descriptor = kwargs['descriptor']
        except KeyError:
            descriptor = 'InstrumentName'
        logger_name = '{}_bhost-{}-{}'.format(descriptor, str(index), host)
        self.logger = logging.getLogger(logger_name)
        console_handler_name = '{}_stream'.format(logger_name)
        console_handler = CasperConsoleHandler(name=console_handler_name)
        self.logger.addHandler(console_handler)
        self.logger.setLevel(logging.ERROR)
        infomsg = 'Successfully created logger for {}'.format(logger_name)
        self.logger.info(infomsg)

        self.beng_per_host = self.x_per_fpga

    # @classmethod
    # def from_config_source(cls, hostname, index, katcp_port,
    #                        config_source, corr):
    #     bitstream = config_source['bitstream']
    #     return cls(hostname, index, katcp_port=katcp_port,
    #                bitstream=bitstream, connect=True, config=config_source)

    def beam_destination_set(self, beam):
        """
        Set the data destination for this beam.
        :param beam: The Beam() on which to act
        :return
        """
        beam_cfgreg = self.registers['bf%i_config' % beam.index]
        beam_ipreg = self.registers['bf%i_ip' % beam.index]
        beam_cfgreg.write(port=beam.destination.port)
        beam_ipreg.write(ip=int(beam.destination.ip_address))
        LOGGER.info('%s:%i: Beam %i:%s destination set to %s' % (
            self.host, self.index, beam.index, beam.name,
            beam.destination))

    def beam_index_set(self, beam):
        """
        Set the beam index.
        :param beam: The Beam() on which to act
        :return:
        """
        beam_cfgreg = self.registers['bf%i_config' % beam.index]
        beam_cfgreg.write(beam_id=beam.index)
        LOGGER.info('%s:%i: Beam %i:%s index set - %i' % (
            self.host, self.index, beam.index, beam.name, beam.index))

    def beam_weights_set(self, beam, source_labels=None):
        """
        Set the beam weights for the given beam and given input labels.
        :param beam: The Beam() on which to act
        :param source_labels: a list of the input/ant/source labels to set
        """
        if not source_labels:
            source_labels = []
            for source in beam.source_streams:
                source_labels.append(source.name)
        LOGGER.info('%s: setting beamweights for beam %i' % (self.host, beam.index))
        for source_name in source_labels:
            source = beam.get_source(source_name)
            source_info = beam.source_streams[source]
            source_weight = source_info['weight']
            source_index = source_info['index']
            self.registers.bf_value_in0.write(bw=source_weight)
            for beng_ctr in range(0, self.beng_per_host):
                self.registers.bf_control.write(
                    stream=beam.index, beng=beng_ctr, antenna=source_index)
                self.registers.bf_value_ctrl.write(bw='pulse')
                LOGGER.debug(
                    '%s:%i: Beam %i:%s set beng(%i) antenna(%i) weight(%.5f)'
                    '' % (self.host, self.index, beam.index, beam.name,
                          beng_ctr, source_index, source_weight))
            time.sleep(0.1)

    def beam_weights_get(self, beam, source_labels=None):
        """
        Get the beam weights for the given beam.
        :param beam: The Beam() on which to act
        :param source_labels: a list of the input/ant/source names to get
        """
        if not source_labels:
            source_labels = []
            for source in beam.source_streams:
                source_labels.append(source.name)
        rv = []
        for source_name in source_labels:
            source = beam.get_source(source_name)
            source_info = beam.source_streams[source]
            source_index = source_info['index']
            self.registers.bf_control.write(
                stream=beam.index, beng=0, antenna=source_index)
            d = self.registers.bf_valout_bw1.read()['data']
            d.update(self.registers.bf_valout_bw0.read()['data'])
            drv = [d['bw%i' % beng_ctr] for beng_ctr in range(self.x_per_fpga)]
            rv.append(drv)
        return rv

    def beam_quant_gains_set(self, beam, new_gain):
        """
        Set the beam quantiser gains for the given beam on the host.
        :param beam: The Beam() on which to act
        :param new_gain: the new gain value to apply, float
        :return the value actually written to the host
        """
        if hasattr(self.registers, 'bf0_gain'):
            # new style gain setting
            reg = self.registers['bf{}_gain'.format(beam.index)]
            reg.write(gain=new_gain)
        else:
            LOGGER.warning('OLD STYLE B-ENGINE GAIN SETTING DEPRECATED.')
            self.registers.bf_value_in1.write(quant=new_gain)
            for beng_ctr in range(0, self.beng_per_host):
                self.registers.bf_control.write(
                    stream=beam.index, beng=beng_ctr, antenna=0)
                self.registers.bf_value_ctrl.write(quant='pulse')
                LOGGER.info(
                    '%s:%i: Beam %i:%s set beng(%i) quant_gain(%.5f)' % (
                        self.host, self.index, beam.index, beam.name,
                        beng_ctr, new_gain))
        return self.beam_quant_gains_get(beam)

    def beam_quant_gains_get(self, beam):
        """
        Read the beam quantiser gains for the given beam from the host.
        :param beam: The Beam() on which to act
        :return one value for the quant gain set on all b-engines on this host
        """
        if hasattr(self.registers, 'bf0_gain'):
            # new style gain setting
            reg = self.registers['bf{}_gain'.format(beam.index)]
            return reg.read()['data']['gain']
        else:
            LOGGER.warning('OLD STYLE B-ENGINE GAIN SETTING DEPRECATED.')
            self.registers.bf_control.write(stream=beam.index, beng=0,
                                            antenna=0)
            d = self.registers.bf_valout_quant0.read()['data']
            d.update(self.registers.bf_valout_quant1.read()['data'])
            drv = [d['quant%i' % beng_ctr]
                   for beng_ctr in range(self.x_per_fpga)]
            for v in drv:
                if v != drv[0]:
                    errmsg = 'Host({host}) Beam({bidx}:{beam}): quantiser ' \
                             'gains differ across b-engines on ' \
                             'this host: {vals}'.format(host=self.host,
                                                        bidx=beam.index,
                                                        beam=beam.name,
                                                        vals=drv)
                    LOGGER.error(errmsg)
                    raise ValueError(errmsg)
            return drv[0]

    def check_beng(self, x_indices=None):
        """

        :param x_indices: a list of the beng indices to check
        :return:
        """
        if x_indices is None:
            x_indices = range(self.x_per_fpga)
        stat0 = self.get_beng_status(x_indices)
        time.sleep(self._get_checktime())
        stat1 = self.get_beng_status(x_indices)
        rv = []
        for xeng in x_indices:
            rvb = []
            for beng in range(2):
                st0 = stat0[xeng][beng]
                st1 = stat1[xeng][beng]
                if st0['of_err_cnt'] != st1['of_err_cnt']:
                    msg = '{host}: beng{b},{x} errors incrementing'.format(
                        host=self.host, x=xeng, b=beng)
                    LOGGER.error(msg)
                    rvb.append(1)
                elif st0['pkt_cnt'] == st1['pkt_cnt']:
                    msg = '{host}: beng{b},{x} not sending packets'.format(
                        host=self.host, x=xeng, b=beng)
                    LOGGER.warn(msg)
                    rvb.append(2)
                else:
                    rvb.append(0)
            rv.append(rvb)
        return rv

