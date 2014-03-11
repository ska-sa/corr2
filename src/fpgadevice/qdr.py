# -*- coding: utf-8 -*-
"""
Created on Fri Mar  7 07:15:45 2014

@author: paulp
"""

# pylint: disable-msg = C0103
# pylint: disable-msg = C0301

import logging
LOGGER = logging.getLogger(__name__)

import numpy, struct

from fpgadevice import register

calibration_data = [[0xAAAAAAAA, 0x55555555] * 16,
    [0, 0, 0xFFFFFFFF, 0, 0, 0, 0, 0],
    numpy.arange(256) << 0,
    numpy.arange(256) << 8,
    numpy.arange(256) << 16,
    numpy.arange(256) << 24]

def find_cal_area(area):
    '''?????
    '''
    max_so_far = area[0]
    max_ending_here = area[0]
    begin_index = 0
    begin_temp = 0
    end_index = 0
    for i in range(len(area)):
        if max_ending_here < 0:
            max_ending_here = area[i]
            begin_temp = i
        else:
            max_ending_here += area[i]
        if max_ending_here >= max_so_far:
            max_so_far = max_ending_here
            begin_index = begin_temp
            end_index = i
    return max_so_far, begin_index, end_index

class Qdr(object):
    '''Qdr memory on an FPGA.
    '''
    def __init__(self, parent, name, info):
        '''Make the QDR instance, given a parent, name and info from Simulink.
        '''
        self.parent = parent
        self.name = name
        self.block_info = info
        self.qdr_number = self.block_info['which_qdr']
        self.ctrl_reg = register.Register(self.parent, self.qdr_number + '_ctrl',
            info={'tag': 'xps:sw_reg', 'mode': 'one\_value',
                  'io_dir': 'From\_Processor', 'io_delay': '0',
                  'sample_period': '1', 'names': 'reg', 'bitwidths': '32',
                  'arith_types': '0', 'bin_pts': '0', 'sim_port': 'on',
                  'show_format': 'off'})
        self.memory = self.qdr_number + '_memory'

    def post_create_update(self, raw_device_info):
        '''Update the QDR using device info from Simulink.
        '''
        return

    def reset(self):
        '''Reset the QDR controller by toggling the lsb of the control register.
        Sets all taps to zero (all IO delays reset).
        '''
        self.ctrl_reg.write_int(1, blindwrite=True)
        self.ctrl_reg.write_int(0, blindwrite=True)

    def _delay_step(self, bitmask, step, offset, offset_mask):
        '''Steps all bits in bitmask by 'step' number of taps.
        '''
        if step == 0:
            return
        if step > 0:
            self.ctrl_reg.write_int(0xffffffff, blindwrite=True, offset=7)
        else:
            self.ctrl_reg.write_int(0, blindwrite=True, offset=7)
        for _ in range(abs(step)):
            self.ctrl_reg.write_int(0, blindwrite=True, offset=offset)
            self.ctrl_reg.write_int(0, blindwrite=True, offset=5)
            self.ctrl_reg.write_int(0xffffffff & bitmask, blindwrite=True,
                                    offset=offset)
            self.ctrl_reg.write_int(offset_mask, blindwrite=True, offset=5)

    def delay_out_step(self, bitmask, step):
        '''Steps all OUT bits in bitmask by 'step' number of taps.
        '''
        self._delay_step(bitmask, step, 6, ((0xf) & (bitmask >> 32)) << 4)

    def delay_in_step(self, bitmask, step):
        '''Steps all IN bits in bitmask by 'step' number of taps.
        '''
        self._delay_step(bitmask, step, 4, (0xf) & (bitmask >> 32))

    def delay_clk_step(self, step):
        '''Steps the output clock by 'step' amount.
        '''
        if step == 0:
            return
        elif step > 0:
            self.ctrl_reg.write_int(0xffffffff, blindwrite=True, offset=7)
        elif step < 0:
            self.ctrl_reg.write_int(0, blindwrite=True, offset=7)
        for _ in range(abs(step)):
            self.ctrl_reg.write_int(0, blindwrite=True, offset=5)
            self.ctrl_reg.write_int(1 << 8, blindwrite=True, offset=5)

    def delay_clk_get(self):
        '''Gets the current value for the clk delay.
        '''
        raw = self.ctrl_reg.read_uint(offset=8)
        if (raw & 0x1f) != ((raw & (0x1f << 5)) >> 5):
            raise RuntimeError("Counter values not the same - logic error, got back %i.", raw)
        return raw & 0x1f

    def cal_check(self):
        '''Checks calibration on a qdr. Raises an exception if it failed.
        '''
        pattern_fail = 0
        for pattern in calibration_data:
            self.parent.blindwrite(self.memory, struct.pack('>%iL' % len(pattern), *pattern))
            data = self.parent.read(self.memory, len(pattern) * 4)
            retdat = struct.unpack('>%iL' % len(pattern), data)
            for word_n, word in enumerate(pattern):
                pattern_fail = pattern_fail | (word ^ retdat[word_n])
                LOGGER.debug('{0:032b}'.format(word),
                             '{0:032b}'.format(retdat[word_n]),
                             '{0:032b}'.format(pattern_fail))
        if pattern_fail > 0:
            LOGGER.error('Calibration of %s failed: 0b%s.', self.name, '{0:032b}'.format(pattern_fail))
            return False
        return True

    def find_in_delays(self):
        '''??????????????TODO
        '''
        n_steps = 32
        n_bits = 32
        fail = []
        bit_cal = [[] for bit in range(n_bits)]
        for step in range(n_steps):
            stepfail = self.cal_check()
            fail.append(stepfail)
            for bit in range(n_bits):
                bit_cal[bit].append(1-2*((fail[step]&(1<<bit))>>bit))
            LOGGER.debug('STEP input delays to %i!', step + 1)
            self.delay_in_step(0xfffffffff, 1)
        LOGGER.info('Eye for QDR %i (0 is pass, 1 is fail):', self.qdr_number)
        for step in range(n_steps):
            LOGGER.info('\tTap step %2i: %s', step, '{0:032b}'.format(fail[step]))
            for bit in range(n_bits):
                LOGGER.debug('Bit %2i: %i', bit, bit_cal[bit])
        # find indices where calibration passed and failed:
        for bit in range(n_bits):
            try:
                bit_cal[bit].index(1)
            except ValueError:
                raise RuntimeError("Calibration failed for bit %i.", bit)
        cal_steps = numpy.zeros(n_bits + 4)
        # find the largest contiguous cal area
        for bit in range(n_bits):
            cal_area = find_cal_area(bit_cal[bit])
            if cal_area[0] < 4:
                raise RuntimeError('Could not find a robust calibration setting for QDR%i', self.qdr_number)
            cal_steps[bit] = sum(cal_area[1:3])/2
            LOGGER.debug('Selected tap for bit %i: %i', bit, cal_steps[bit])
        #since we don't have access to bits 32-36, we guess the number of taps required based on the other bits:
        median_taps = numpy.median(cal_steps)
        LOGGER.debug('Median taps: %i', median_taps)
        for bit in range(32, 36):
            cal_steps[bit] = median_taps
            LOGGER.debug('Selected tap for bit %i: %i', bit, cal_steps[bit])
        return cal_steps

    def apply_cals(self, in_delays, out_delays, clk_delay):
        self.reset()
        assert len(in_delays) == 36
        assert len(out_delays) == 36
        self.delay_clk_step(clk_delay)
        # in delays
        for step in range(int(max(in_delays))):
            mask = 0
            for bit in range(len(in_delays)):
                mask += (1<<bit if (step < in_delays[bit]) else 0)
            LOGGER.debug('Step in %i: %s', step, '{0:036b}'.format(mask))
            self.delay_in_step(mask, 1)
        # out delays
        for step in range(int(max(out_delays))):
            mask = 0
            for bit in range(len(out_delays)):
                mask += (1<<bit if (step < out_delays[bit]) else 0)
            LOGGER.debug('Step in %i: %s', step, '{0:036b}'.format(mask))
            self.delay_out_step(mask, 1)

    def calibrate(self):
        '''Calibrate a QDR controller, stepping input delays and (if that fails) output delays.
        Returns True if calibrated, raises a runtime exception if it doesn't.
        '''
        calibrated = False
        out_step = 0
        while (not calibrated) and (out_step < 32):
#            try:
            self.reset()
            in_delays = self.find_in_delays()
#            except Exception:
#                calibrated = False
#                in_delays = [0 for bit in range(36)]
            out_delays = [out_step for bit in range(36)]
            self.apply_cals(in_delays, out_delays, clk_delay=out_step)
            calibrated = self.cal_check()
            out_step += 1
            LOGGER.info('--- === STEPPING OUT DELAYS to %i=== --- was: %i', out_step, self.delay_clk_get())
        if self.cal_check():
            return True
        else:
            raise RuntimeError("QDR %i calibration failed.", self.qdr_number)

# end
