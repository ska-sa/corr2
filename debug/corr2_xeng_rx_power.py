import time,corr2,casperfpga,numpy,sys
c=corr2.fxcorrelator.FxCorrelator('bob',config_source='/etc/corr/avdbyl_test_1k_16t.ini')
c.initialise(program=False,configure=False,require_epoch=False)

def print_xeng_rx_power(xhost_n):
    print 'Xhost %i:'%xhost_n
    raw_data = c.xhosts[xhost_n].snapshots.snap_rx_unpack0_ss.read()['data']
    xeng_id = numpy.array(raw_data['xeng_id'])
    feng_id = numpy.array(raw_data['fengid'])
    freq_this_eng = numpy.array(raw_data['freq_this_eng'])
    data = numpy.array(raw_data['data'])
    choicelist = [data]
    data0 = numpy.select([(xeng_id==(xhost_n*4+0))&(feng_id==0)],choicelist)
    data1 = numpy.select([(xeng_id==(xhost_n*4+1))&(feng_id==0)],choicelist)
    data2 = numpy.select([(xeng_id==(xhost_n*4+2))&(feng_id==0)],choicelist)
    data3 = numpy.select([(xeng_id==(xhost_n*4+3))&(feng_id==0)],choicelist)
    print "RX power from feng0, pol1, xeng0: ",numpy.sum(numpy.abs([(numpy.int8(i&0xff) + numpy.int8(i>>8)*1j) for i in data0]))
    print "RX power from feng0, pol1, xeng1: ",numpy.sum(numpy.abs([(numpy.int8(i&0xff) + numpy.int8(i>>8)*1j) for i in data1]))
    print "RX power from feng0, pol1, xeng2: ",numpy.sum(numpy.abs([(numpy.int8(i&0xff) + numpy.int8(i>>8)*1j) for i in data2]))
    print "RX power from feng0, pol1, xeng3: ",numpy.sum(numpy.abs([(numpy.int8(i&0xff) + numpy.int8(i>>8)*1j) for i in data3]))


def print_xeng_reordered_power(xhost_n):
    return


for xhost_n in range(4):
    print_xeng_rx_power(xhost_n)
print 'done!'
