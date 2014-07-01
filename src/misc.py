# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
Miscellaneous functions that are used in a few places but don't really belong
anywhere.
"""

import logging

LOGGER = logging.getLogger(__name__)


def log_runtime_error(log, error_string):
    """Write an error string to the given log file and then raise a runtime error.
    """
    try:
        log.error(error_string)
    except AttributeError:
        pass
    raise RuntimeError(error_string)


def log_io_error(log, error_string):
    """Write an error string to the given log file and then raise an io error.
    """
    try:
        log.error(error_string)
    except AttributeError:
        pass
    raise IOError(error_string)


def log_value_error(log, error_string):
    """Write an error string to the given log file and then raise a value error.
    """
    try:
        log.error(error_string)
    except AttributeError:
        pass
    raise ValueError(error_string)


def log_not_implemented_error(log, error_string):
    """Write an error string to the given log file and then raise a not implemented error.
    """
    try:
        log.error(error_string)
    except AttributeError:
        pass
    raise NotImplementedError(error_string)


def bin2fp(bits, mantissa=8, exponent=7, signed=False):
    """Convert a raw fixed-point number to a float based on a given
    mantissa and exponent.
    """
    if not signed:
        if exponent == 0:
            return long(bits)
        else:
            return float(bits) / (2 ** exponent)
    from numpy import int32 as numpy_signed, uint32 as numpy_unsigned

    if (mantissa > 32) or (exponent >= mantissa):
        log_runtime_error(LOGGER, 'Unsupported fixed format: %i.%i' % (mantissa,
                                                                       exponent))
    shift = 32 - mantissa
    bits <<= shift
    # mantissa = mantissa + shift
    exponent += shift
    if signed:
        return float(numpy_signed(bits)) / (2 ** exponent)
    return float(numpy_unsigned(bits)) / (2 ** exponent)


def program_fpgas(fpga_list, timeout=10):
    """Program a list of fpgas/boffile tuple-pairs concurrently.
    """
    for fpga, boffile in fpga_list[0:-1]:
        fpga.upload_to_ram_and_program(boffile, timeout=timeout, wait_complete=False)
    fpga_list[-1][0].upload_to_ram_and_program(fpga_list[-1][1], timeout=45, wait_complete=True)
    all_done = False
    import time

    stime = time.time()
    while not all_done:
        time.sleep(0.05)
        all_done = True
        for fpga, _ in fpga_list:
            if not fpga.is_running():
                all_done = False
        if time.time() - stime > timeout:
            log_runtime_error(LOGGER, 'Programming fpgas timed out.')
    return