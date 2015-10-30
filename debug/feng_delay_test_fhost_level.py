#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
"""
Test delay tracking from fhost level

Created on Tuesday Oct  6 2015

@author: andrew
"""
import corr2, os, time, logging
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO)

ant_name = 'ant0_x'
stream_offset = 1

sample_rate = 1712*(10**6)
shift_bits = 23
sleep_time = 2
ld_time = 1
wait_time = 2

offset = 1
load_check_wait_time = None
load_check = False

#delay
delay_val = 2.9999999999999

#delta delay
delta_delay_val_samples = 0
delta_delay_val = float(delta_delay_val_samples) / (float(sleep_time) * sample_rate)

#phase
phase_val = 0

#delta phase
delta_phase_val_samples = 0
delta_phase_val = float(delta_phase_val_samples) / (float(sleep_time) * sample_rate)

c = corr2.fxcorrelator.FxCorrelator('rts wbc', config_source=os.environ['CORR2INI'])
c.initialise(qdr_cal=False,program=False)
c.est_sync_epoch()
f = c.fhosts[stream_offset]

# set up tvg
f.registers.impulse1.write(amplitude=0.5, offset=offset)
f.registers.control.write(tvg_adc=1)

# capture data before setting up delays
x_0 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

mcnt = None
if ld_time is not None:
    mcnt = c.mcnt_from_time(time.time() + float(ld_time))

# set delay

f.set_delay(1, delay_val, delta_delay_val, phase_val, delta_phase_val, mcnt, load_check_wait_time, load_check)
vals = f.write_delays_all()

#vals = f.write_delay(ant_name, delay_val, delta_delay_val, phase_val, delta_phase_val, mcnt, load_check_wait_time, load_check)

# capture data just after setting up delays
x_1 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

print('delay after = %f'%vals[stream_offset]['act_delay'])
print('delta delay after = %f'%vals[stream_offset]['act_delta_delay'])
print('phase offset after = %f'%vals[stream_offset]['act_phase_offset'])
print('delta phase offset after = %f'%vals[stream_offset]['act_delta_phase_offset'])

status_before = f.registers.tl_cd1_status.read()['data']
print('counters before: arm => %d load => %d'%(status_before['arm_count'], status_before['arm_count']))

# sleep 
time.sleep(sleep_time+wait_time)

status_after = f.registers.tl_cd1_status.read()['data']
print('counters after: arm => %d load => %d'%(status_after['arm_count'], status_after['arm_count']))

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
