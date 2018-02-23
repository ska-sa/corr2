import spead2
import spead2.send as sptx
import numpy

ig = sptx.ItemGroup(flavour=spead2.Flavour(4, 64, 48))

streamconfig = sptx.StreamConfig(max_packet_size=9200,
                                 max_heaps=8)
speadstream = sptx.UdpStream(spead2.ThreadPool(),
                             '127.0.0.1',
                             7890,
                             streamconfig,
                             51200000)

# how is one meant to send single-value numpy.dtypes? as below?
ig.add_item(name='a_number', id=0x1025,
            description='A 32-bit unsigned number.',
            shape=(),
            dtype=numpy.uint32,
            value=17)

# this works, too
ig.add_item(name='another_number', id=0x1026,
            description='Another number.',
            shape=[],
            format=[('u', 32)],
            value=18)

# this one breaks the receiver
str_to_send = numpy.array('i am string, hear me roar')
ig.add_item(name='a_first_string', id=0x1027,
            description='a string that we need to send',
            shape=str_to_send.shape,
            dtype=str_to_send.dtype,
            value=str_to_send)

# this one is okay
str_to_send = 'i am only a secondstring'
ig.add_item(name='a_nother_string', id=0x1028,
            description='a string that we do not need to send',
            shape=(None,),
            format=[('c', 8)],
            value=str_to_send)

# list of strings?
alistofstrings = ['this is a string', 'this is a string as well']
b = numpy.array(alistofstrings)
ig.add_item(name='list_of_strings', id=0x1029,
            description='a list of strings',
            shape=b.shape,
            dtype=b.dtype,
            value=b)

# list of numbers
alist = [1, 2, 3, 4]
b = numpy.array(alist)
ig.add_item(name='alistofnumbers', id=0x1030,
            description='A list of numbers?',
            shape=b.shape,
            dtype=b.dtype,
            value=b)

heap = ig.get_heap()

speadstream.send_heap(heap)

print('sent heapspead2test.py'

# list of strings?
alistofstrings = ['so short', 'abcde']
b = numpy.array(alistofstrings)
ig.add_item(name='list_of_strings', id=0x1029,
            description='a list of strings',
            shape=b.shape,
            dtype=b.dtype,
            value=b)

heap = ig.get_heap()

speadstream.send_heap(heap)


print('sent heap again'
