'''
Miscellaneous functions that are used in a few places but don't really belong
anywhere.
'''

import logging
logger = logging.getLogger(__name__)

def log_runtime_error(log, error_string):
    '''Write an error string to the given log file and then raise a
    runtime error.
    '''
    log.error(error_string)
    raise RuntimeError(error_string)

def bin2fp(bits, mantissa=8, exponent=7, signed=False):
    '''Convert a raw fixed-point number to a float based on a given
    mantissa and exponent.
    '''
    if (signed == False) and (exponent == 0):
        return float(bits)
    from numpy import int32 as numpy_signed, uint32 as numpy_unsigned
    if mantissa > 32:
        raise RuntimeError('Unsupported fixed format: %i.%i' % (mantissa,
                                                                exponent))
    shift = 32 - mantissa
    bits = bits << shift
    mantissa = mantissa + shift
    exponent = exponent + shift
    if signed:
        return float(numpy_signed(bits)) / (2**exponent)
    return float(numpy_unsigned(bits)) / (2**exponent)
