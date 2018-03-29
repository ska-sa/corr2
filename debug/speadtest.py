import spead64_48 as spead

import spead2
import spead2.send as sptx
import numpy

ig = spead.ItemGroup()
stx = spead.Transmitter(spead.TransportUDPtx('127.0.0.1', 8887))

ig2 = sptx.ItemGroup(flavour=spead2.Flavour(4, 64, 48))
streamconfig = sptx.StreamConfig(max_packet_size=9200,
                                 max_heaps=8)
speadstream2 = sptx.UdpStream(spead2.ThreadPool(),
                              '127.0.0.1',
                              8888,
                              streamconfig,
                              51200000)

# xraw_array = numpy.dtype(numpy.int32), (4096, 40, 2)
# ig.add_item(
#     name='xeng_raw', id=0x1800,
#     description='Raw data for %i xengines in the system. This item '
#                 'represents a full spectrum (all frequency channels) '
#                 'assembled from lowest frequency to highest '
#                 'frequency. Each frequency channel contains the data '
#                 'for all baselines (baselines given by SPEAD ID 0x100C). '
#                 'Each value is a complex number -- two (real and '
#                 'imaginary) unsigned integers.' % 32,
#     ndarray=xraw_array)
#
# ig.add_item(
#     name='xeng_raw', id=0x1800,
#     description='Raw data for %i xengines in the system. This item '
#                 'represents a full spectrum (all frequency channels) '
#                 'assembled from lowest frequency to highest '
#                 'frequency. Each frequency channel contains the data '
#                 'for all baselines (baselines given by SPEAD ID 0x100C). '
#                 'Each value is a complex number -- two (real and '
#                 'imaginary) unsigned integers.' % 32,
#     shape=[4096, 40, 2], fmt=spead.mkfmt(('i', 32)))
# ig['xeng_raw'] = numpy.arange(4096*40*2)
# ig['xeng_raw'].shape = (4096,40,2)
#
ig2.add_item(
    name='xeng_raw', id=0x1800,
    description='Raw data for %i xengines in the system. This item '
                'represents a full spectrum (all frequency channels) '
                'assembled from lowest frequency to highest '
                'frequency. Each frequency channel contains the data '
                'for all baselines (baselines given by SPEAD ID '
                '0x100C). Each value is a complex number -- two (real '
                'and imaginary) unsigned integers.' % 32,
    # dtype=numpy.int32,
    dtype=numpy.dtype('>i4'),
    shape=[4096, 40, 2])

# ig2.add_item(
#     name='xeng_raw', id=0x1800,
#     description='Raw data for %i xengines in the system. This item '
#                 'represents a full spectrum (all frequency channels) '
#                 'assembled from lowest frequency to highest '
#                 'frequency. Each frequency channel contains the data '
#                 'for all baselines (baselines given by SPEAD ID '
#                 '0x100C). Each value is a complex number -- two (real '
#                 'and imaginary) unsigned integers.' % 32,
#     format=[('i', 32)],
#     # dtype=numpy.int32,
#     shape=[4096, 40, 2])

# send the heaps
stx.send_heap(ig.get_heap())
speadstream2.send_heap(ig2.get_heap())
print('sent heaps'
