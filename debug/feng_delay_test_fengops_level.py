#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
"""
Test delay tracking from fhost level

Created on Tuesday Oct  6 2015

@author: andrew
"""
import corr2, os, time, numpy, logging
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO)

ant_name = 'ant1_y'
sample_rate = 1712*(10**6)
shift_bits = 23
sleep_time = 0.5
ld_offset = 0.5
offset = 1

#delay
delay_val_seconds = float(1) / float(sample_rate)
#delay_val_seconds = 0

#delta delay
#delta_delay_val_seconds_per_second = float(2) / (float(sample_rate) * sleep_time)
delta_delay_val_seconds_per_second = 0

#phase
#phase_val_radians = 0.5*numpy.pi
phase_val_radians = 0

#delta phase
#delta_phase_val_radians_per_second = (numpy.pi/2) / sleep_time
delta_phase_val_radians_per_second = 0

c = corr2.fxcorrelator.FxCorrelator('rts wbc', config_source=os.environ['CORR2INI'])
c.initialise(qdr_cal=False,program=False)
c.est_sync_epoch()
f = c.fhosts[0]

# set up tvg
f.registers.impulse1.write(amplitude=0.5, offset=offset)
f.registers.control.write(tvg_adc=1)

# capture data before setting up delays
x_0 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

# set delay

# defaults of 0
coeffs=[]
for cnt in range(len(c.fengine_sources)):
    delay_coeffs = [0,0]
    phase_coeffs = [0,0]
    coeffs.append([delay_coeffs, phase_coeffs])

coeffs[1] = [[delay_val_seconds, delta_delay_val_seconds_per_second],
                [phase_val_radians, delta_phase_val_radians_per_second]]

return_vals = c.fops.set_delays_all(time.time()+ld_offset, coeffs)

actual_val = return_vals[1]
print('actual delay = %es'%actual_val['act_delay'])
print('actual delta delay = %fs/s'%actual_val['act_delta_delay'])
print('actual phase offset = %f radians'%actual_val['act_phase_offset'])
print('actual delta phase offset = %f radians/s'%actual_val['act_delta_phase_offset'])

#ld_time=time.time()+ld_offset
#c.fops.set_delay(ant_name, delay=delay_val_seconds, delta_delay=delta_delay_val_seconds_per_second, 
#                phase_offset=phase_val_radians, delta_phase_offset=delta_phase_val_radians_per_second, 
#                ld_time=ld_time, ld_check=False)

# set delay
#ld_time=time.time()+ld_offset
#c.fops.set_delay(ant_name, delay=delay_val_seconds, delta_delay=delta_delay_val_seconds_per_second, 
#                phase_offset=phase_val_radians, delta_phase_offset=delta_phase_val_radians_per_second, 
#                ld_time=ld_time, ld_check=False)

# capture data just after setting up delaysa
x_1 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

# sleep 
time.sleep(sleep_time+ld_offset)

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
