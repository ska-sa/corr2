#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
"""
Test delay tracking

Created on Tuesday Oct  6 2015

@author: andrew
"""
import corr2, os, time, logging
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO)

sample_rate = 1712*(10**6)
shift_bits = 23
sleep_time = 1
ld_time = 1
wait_time = 2
offset = 1

#delay
coarse_delay_val = 0 
fractional_delay_val = 0

#delta delay
delta_delay_val_samples = 0  # the final delay value to reach in the sleep time allocated
delta_delay_val = float(delta_delay_val_samples) / (sleep_time * sample_rate)
delta_delay_val_shifted = delta_delay_val * (2 ** shift_bits)

#phase
phase_val = 0

#delta phase
delta_phase_val_samples = 0
delta_phase_val = float(delta_phase_val_samples) / (float(sleep_time) * sample_rate)
delta_phase_val_shifted = delta_phase_val * (2 ** shift_bits)

c = corr2.fxcorrelator.FxCorrelator('rts wbc', config_source=os.environ['CORR2INI'])
c.initialise(qdr_cal=False,program=False)
c.est_sync_epoch()
f = c.fhosts[0]

# set up tvg
f.registers.impulse1.write(amplitude=0.5, offset=offset)
f.registers.control.write(tvg_adc=1)

# capture data before setting up delays
x_0 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

# set up delay values
f.registers.coarse_delay1.write(coarse_delay=coarse_delay_val)
f.registers.fractional_delay1.write(initial=fractional_delay_val, delta=delta_delay_val_shifted)
f.registers.phase1.write(initial=phase_val, delta=delta_phase_val_shifted)

mcnt = None
if ld_time is not None:
    mcnt = c.mcnt_from_time(time.time() + float(ld_time))
    mcnt_msw = int(mcnt/(2**32))
    mcnt_lsw = int(mcnt - mcnt_msw*(2**32))

status_before = f.registers.tl_cd1_status.read()['data']
print('cd status before: armed => %d arm count => %d load count => %d'%(status_before['armed'], status_before['arm_count'], status_before['load_count']))
status_before = f.registers.tl_fd1_status.read()['data']
print('fd status before: armed => %d arm count => %d load count => %d'%(status_before['armed'], status_before['arm_count'], status_before['load_count']))
 
# trigger values
f.registers.tl_cd1_control.write(load_time_lsw=int(mcnt_lsw))
f.registers.tl_cd1_control0.write(arm='pulse', load_time_msw=int(mcnt_msw))

f.registers.tl_fd1_control.write(load_time_lsw=int(mcnt_lsw))
f.registers.tl_fd1_control0.write(arm='pulse', load_time_msw=int(mcnt_msw))

status_before = f.registers.tl_cd1_status.read()['data']
print('cd status before: armed => %d arm count => %d load count => %d'%(status_before['armed'], status_before['arm_count'], status_before['load_count']))
status_before = f.registers.tl_fd1_status.read()['data']
print('fd status before: armed => %d arm count => %d load count => %d'%(status_before['armed'], status_before['arm_count'], status_before['load_count']))

# capture data just after setting up delays
x_1 = f.snapshots.snap_quant1_ss.read(man_valid=False, man_trig=False)['data']

# sleep 
time.sleep(sleep_time+wait_time)

status_after = f.registers.tl_cd1_status.read()['data']
print('cd status after: armed => %d arm count => %d load count => %d'%(status_after['armed'], status_after['arm_count'], status_after['load_count']))
status_after = f.registers.tl_fd1_status.read()['data']
print('fd status after: armed => %d arm count => %d load count => %d'%(status_after['armed'], status_after['arm_count'], status_after['load_count']))

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
