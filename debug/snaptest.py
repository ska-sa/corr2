import casperfpga

HOST = 'somehost'
FPG = 'snap.fpg'

f = casperfpga.CasperFpga(HOST)
f.upload_to_ram_and_program(FPG)

# read the snaps using fabric we/dv and trig
f.registers.snap_control.write(snap_arm=False)
f.snapshots.snap0_ss.arm()
f.snapshots.snap1_ss.arm()
f.registers.snap_control.write(snap_arm=True)
d = f.snapshots.snap0_ss.arm().read(arm=False)['data']
d.update(f.snapshots.snap1_ss.arm().read(arm=False)['data'])
f.registers.snap_control.write(snap_arm=False)

# read the snaps with man_trig, but not man_valid
# the man_trig has to be done via a register to get both snaps
# to trigger at the same time
f.registers.snap_control.write(snap_arm=False, snap_trigsel=1)
f.snapshots.snap0_ss.arm()
f.snapshots.snap1_ss.arm()
f.registers.snap_control.write(snap_arm=True, snap_trig='pulse')
d = f.snapshots.snap0_ss.arm().read(arm=False)['data']
d.update(f.snapshots.snap1_ss.arm().read(arm=False)['data'])
f.registers.snap_control.write(snap_arm=False, snap_trigsel=0)

# man_valid, but not man_trig
f.registers.snap_control.write(snap_arm=False)
f.snapshots.snap0_ss.arm(man_valid=True)
f.snapshots.snap1_ss.arm(man_valid=True)
f.registers.snap_control.write(snap_arm=True)
d = f.snapshots.snap0_ss.arm().read(arm=False)['data']
d.update(f.snapshots.snap1_ss.arm().read(arm=False)['data'])
f.registers.snap_control.write(snap_arm=False)

# man_valid and man_trig
f.registers.snap_control.write(snap_arm=False, snap_trigsel=1)
f.snapshots.snap0_ss.arm(man_valid=True)
f.snapshots.snap1_ss.arm(man_valid=True)
f.registers.snap_control.write(snap_arm=True, snap_trig='pulse')
d = f.snapshots.snap0_ss.arm().read(arm=False)['data']
d.update(f.snapshots.snap1_ss.arm().read(arm=False)['data'])
f.registers.snap_control.write(snap_arm=False, snap_trigsel=0)

# circular capture and start delay are as for a single snap, but you pass
# the args to arm(), not read()

# end
