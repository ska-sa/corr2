import logging
logger = logging.getLogger(__name__)

def log_runtime_error(logger, error_string):
    logger.error(error_string)
    raise RuntimeError(error_string)

def bin2fp(bits, m=8, e=7, signed=False):
    from numpy import int32 as numpy_signed, uint32 as numpy_unsigned
    if m > 32:
        raise RuntimeError('Unsupported fixed format: %i.%i' % (m,e))
    shift = 32 - m
    bits = bits << shift
    m = m + shift
    e = e + shift
    if signed: return float(numpy_signed(bits)) / (2**e)
    return float(numpy_unsigned(bits)) / (2**e)

def ip2str(ip_integer, verbose = False):
    """
    Returns a dot notation IPv4 address given a 32-bit number.
    """
    ip_4 = (ip_integer & ((2**32) - (2**24))) >> 24
    ip_3 = (ip_integer & ((2**24) - (2**16))) >> 16
    ip_2 = (ip_integer & ((2**16) - (2**8)))  >> 8
    ip_1 = (ip_integer & ((2**8)  - (2**0)))  >> 0
    ipstr = '%i.%i.%i.%i' % (ip_4, ip_3, ip_2, ip_1)
    if verbose:
        print 'IP(%i) decoded to:' % ip_integer, ipstr
    return ipstr