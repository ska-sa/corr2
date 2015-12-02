import argparse
import logging
import spead2
import spead2.send as s2tx
import socket
import struct
import time
import numpy

parser = argparse.ArgumentParser(description='Set up the simple narrowband filters.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='the config file to use')
parser.add_argument('--comms', dest='comms', action='store', default='katcp', type=str,
                    help='katcp (default) or dcp?')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

log_level = 'INFO'
try:
    logging.basicConfig(level=eval('logging.%s' % log_level))
except AttributeError:
    raise RuntimeError('No such log level: %s' % log_level)
LOGGER = logging.getLogger(__name__)

SPEAD_ADDRSIZE = 48

speadig = s2tx.ItemGroup(
    flavour=spead2.Flavour(4, 64, SPEAD_ADDRSIZE))

streamconfig = s2tx.StreamConfig(max_packet_size=4096,
                                 max_heaps=8)
streamsocket = socket.socket(family=socket.AF_INET,
                             type=socket.SOCK_DGRAM,
                             proto=socket.IPPROTO_IP)
ttl_bin = struct.pack('@i', 2)
streamsocket.setsockopt(
    socket.IPPROTO_IP,
    socket.IP_MULTICAST_TTL,
    ttl_bin)
speadtx = s2tx.UdpStream(spead2.ThreadPool(),
                         '127.0.0.1',
                         8889,
                         streamconfig,
                         51200000,
                         streamsocket)

# add metadata that the receiver is expecting
speadig.add_item(
    name='xeng_raw', id=0x1800,
    description='Raw data for %i xengines in the system. This item '
                'represents a full spectrum (all frequency channels) '
                'assembled from lowest frequency to highest '
                'frequency. Each frequency channel contains the data '
                'for all baselines (n_bls given by SPEAD ID 0x100b). '
                'Each value is a complex number -- two (real and '
                'imaginary) unsigned integers.' % 32,
    dtype=numpy.int32,
    shape=[4096,
           10,
           2])

# send the metadata
speadtx.send_heap(speadig.get_heap())

# send some fake data in a loop
while True:

    # make some data
    data = numpy.array()

    speadig.add_item(
        name='xeng_raw', id=0x1800,
        value=data)

    speadtx.send_heap(speadig.get_heap())

    time.sleep(1)
