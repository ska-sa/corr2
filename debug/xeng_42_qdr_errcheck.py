import casperfpga


host = 'roach02081a'

errors_undetected = {}
undetected_writes = {}

f = casperfpga.KatcpFpga(host)
f.get_system_information()

snapname = 'snap_vacc_ss'

snap = f.snapshots[snapname]

d = snap.read(circular_capture=True, man_trig=True, man_valid=True)['data']

print(len(d[d.keys()[0]])

print('ctr\t',
for key in d.keys():
    print(key, '\t',
print(''
for ctr in range(len(d['new_acc'])):
    print(ctr,
    for key in d.keys():
        print(d[key][ctr], '\t',
    print(''
