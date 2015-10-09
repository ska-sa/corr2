#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
"""
Test delay tracking

Created on Tuesday Oct  6 2015

@author: andrew
"""
import corr2, os, time
import matplotlib.pyplot as plt

sample_rate = 1712*(10**6)
shift_bits = 23
sleep_time = 4

#delay
coarse_delay_val = 0 
fractional_delay_val = 0

#delta delay
delta_delay_val_samples = 0  # the final delay value to reach in the sleep time allocated
delta_delay_val = delta_delay_val_samples / (sleep_time * sample_rate)
delta_delay_val_shifted = delta_delay_val * (2 ** shift_bits)

#phase
phase_val = 0

#delta phase
delta_phase_val_samples = 2
delta_phase_val = float(delta_phase_val_samples) / (float(sleep_time) * sample_rate)
delta_phase_val_shifted = delta_phase_val * (2 ** shift_bits)

c = corr2.fxcorrelator.FxCorrelator('rts wbc', config_source=os.environ['CORR2INI'])
c.initialise(qdr_cal=False,program=False)
f = c.fhosts[0]

# set up tvg
f.registers.impulse1.write(amplitude=0.5, offset=1)
f.registers.control.write(tvg_adc=1)

# capture data before setting up delays
x_0 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

# set up delay values
f.registers.coarse_delay1.write(coarse_delay=coarse_delay_val)
f.registers.fractional_delay1.write(initial=fractional_delay_val, delta=delta_delay_val_shifted)
f.registers.phase1.write(initial=phase_val, delta=delta_phase_val_shifted)
 
# trigger values
f.registers.tl_cd1_control0.write(arm='pulse', load_immediate='pulse')
f.registers.tl_fd1_control0.write(arm='pulse', load_immediate='pulse')

# capture data just after setting up delaysa
x_1 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

# sleep 
#time.sleep(sleep_time)
time.sleep(sleep_time)

# capture data after
x_2 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

plt.figure()
plt.plot(x_0['real0'])
plt.plot(x_0['imag0'])

plt.figure()
plt.plot(x_1['real0'])
plt.plot(x_1['imag0'])

plt.figure()
plt.plot(x_2['real0'])
plt.plot(x_2['imag0'])
plt.show()
