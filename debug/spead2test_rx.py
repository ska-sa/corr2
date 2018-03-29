import spead2
import spead2.recv as s2rx

PORT = 8888

strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0,
                   max_heaps=8, ring_heaps=8)
strm.add_udp_reader(port=PORT, max_size=4096,
                    buffer_size=51200000)

ig = spead2.ItemGroup()

for heap in strm:
    ig.update(heap)
    for key in ig.keys():
        itm = ig[key]
        print(key, ':'
        print('\t', 'id:', '0x%4x' % itm.id
        print('\t', 'name:', itm.name
        print('\t', 'description:', itm.description
        print('\t', 'value:', itm.value
        print('\t', 'dtype:', itm.dtype
        print('\t', 'format:', itm.format
        print('\t', 'itemsize_bits:', itm.itemsize_bits
        print('\t', 'order:', itm.order
        print('\t', 'shape:', itm.shape
        print('\t', 'version:', itm.version
        print('\t', 'allow_immediate:', itm.allow_immediate()
        print('\t', 'is_variable_size:', itm.is_variable_size()
        print(''
    print(50*'&*'

    # import IPython
    # IPython.embed()
