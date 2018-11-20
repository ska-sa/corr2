import time,corr2,casperfpga,numpy,sys,pylab
c=corr2.fxcorrelator.FxCorrelator('bob',config_source='/etc/corr/avdbyl_test_1k_16t.ini')
c.initialise(program=False,configure=False,require_epoch=False)

n_ants=4
n_chans=1024
x=c.xhosts[0]

x.registers.tvg_control.write(snap_reord_mux_we_sel=1) #only capture a specific frequency
x.registers.sys0_snap_reord_we_freq=4 #freq_this_engine
data=x.snapshots.sys0_snap_reord0_ss.read()['data']

i=0
pol0=[]
pol1=[]
for ant in range(n_ants):
    pol0.append([])
    pol1.append([])
while i < len(data['data']):
    for ant_n in range(n_ants):
        for pi in range(256):
            pol0[ant_n].append(complex(numpy.int8((data['data'][i+pi]&0xff000000)>>24),numpy.int8((data['data'][i+pi]&0x00ff0000)>>16)))
            pol1[ant_n].append(complex(numpy.int8((data['data'][i+pi]&0xff00)>>8),numpy.int8((data['data'][i+pi]&0x00ff))))
            #print ant_n,pol0[ant_n][-1],pol1[ant_n][-1]
        i+=256


for i in range(len(pol0[0])):
    print '{:4}'.format(i),
    for ant_n in range(n_ants):
        print '{:11}'.format(pol0[ant_n][i]),
    print '       |||| ',
    for ant_n in range(n_ants):
        print '{:11}'.format(pol1[ant_n][i]),
    print ''

#for ant_n in range(n_ants):
#    pylab.plot(numpy.abs(pol0[ant_n]))
#pylab.show()
#for ant_n in range(n_ants):
#    pylab.plot(pol0[ant_n])
#pylab.show()
