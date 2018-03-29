import numpy, logging, sys

import spead64_48 as spead

logging.basicConfig(level=logging.INFO)
PORT = 8888

heapdata = []


def receive():
    timesdone = 0
    f = open('/tmp/woo', 'w')
    f.close()
    print('RX: Initializing...'
    t = spead.TransportUDPrx(PORT)
    ig = spead.ItemGroup()
    last_timestamp = 0
    timestamp = 0
    for heap in spead.iterheaps(t):
        #print(spead.readable_heap(heap)
        ig.update(heap)
        print('Got heap cnt(%d):' % ig.heap_cnt
        for name in ig.keys():
            print('   ', name
            item = ig.get_item(name)
            print('      Description: ', item.description
            print('           Format: ', item.format
            print('            Shape: ', item.shape
            # print('            Value: ', ig[name]
            if ig[name] is not None:
                if name == 'timestamp':
                    last_timestamp = timestamp
                    timestamp = ig[name]
                elif name == 'xeng_raw':
                    global heapdata
                    heapdata = []
                    heapdata[:] = ig[name]
                    f = open('/tmp/woo', 'a')
                    f.write('timestamp(%d) timediff(%d)\n' % (timestamp,  timestamp - last_timestamp))
                    for data in heapdata:
                        for bls_ctr, data_ in enumerate(data):
                            fstr = 'acc_ctr(%010d) baseline(%02d) freq(%04d) ' % (data_[1], data_[0] & 63,
                                                                                  (data_[0] >> 6) & 4095)
                            f.write('%s\n' % fstr)
                        # print(data
                        # data = int(data)
                        # timestep = data & 0xffffffff
                        # bls = (data >> 32) & 63
                        # freq = (data >> 38) & 4095
                        # f.write('%5i\t%3i\t%10i\n' % (freq, bls, timestep))
                    f.close()
                    timesdone += 1
                    if timesdone == 2:
                        del ig
                        del t
                        return
    print('RX: Done.'


def transmit():
    print('TX: Initializing...'
    tx = spead.Transmitter(spead.TransportUDPtx('127.0.0.1', PORT))
    ig = spead.ItemGroup()

    ig.add_item(name='Var1', description='Description for Var1',
        shape=[], fmt=spead.mkfmt(('u',32),('u',32),('u',32)),
        init_val=(1,2,3))
    tx.send_heap(ig.get_heap())
    ig['Var1'] = (4,5,6)
    tx.send_heap(ig.get_heap())

    ig.add_item(name='Var2', description='Description for Var2',
        shape=[100,100], fmt=spead.mkfmt(('u',32)))
    data = numpy.arange(100*100); data.shape = (100,100)
    ig['Var2'] = data
    tx.send_heap(ig.get_heap())

    tx.end()
    print('TX: Done.'

if sys.argv[-1] == 'tx': transmit()
elif sys.argv[-1] == 'rx': receive()
else: raise ValueError('Argument must be rx or tx')
