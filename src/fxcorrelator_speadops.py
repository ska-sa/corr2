SPEAD_ADDRSIZE = 48

def add_item(sig, stx=None, **kwargs):
    """
    Add an item to a SPEAD ItemGroup, send if SPEAD TX provided
    :param sig: SPEAD ItemGroup
    :param stx: SPEAD transmitter
    :param kwargs:
    :return:
    """
    # sid = kwargs['id']
    # spead2 metadata create (and send)
    if sig is not None:
        sig.add_item(**kwargs)
    if stx is not None:
        stx.send_heap(sig.get_heap(descriptors='all', data='all'))

def item_0x1600(sig, stx=None):
    add_item(
        sig=sig, stx=stx,
        name='timestamp', id=0x1600,
        description='Timestamp of start of this integration. uint '
                    'counting multiples of ADC samples since last sync '
                    '(sync_time, id=0x1027). Divide this number by '
                    'timestamp_scale (id=0x1046) to get back to seconds '
                    'since last sync when this integration was actually '
                    'started.',
        shape=[],
        format=[('u', SPEAD_ADDRSIZE)])

