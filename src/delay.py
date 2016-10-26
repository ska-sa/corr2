from threading import Event
import logging
import numpy

LOGGER = logging.getLogger(__name__)

debug_logging = False


class DelaysUnsetError(Exception):
    pass


def process_list(delay_list):
    """
    Given a list of strings, return a list of delay tuples
    :param delay_list:
    :return:
    """
    rv = []
    for ctr, delay in enumerate(delay_list):
        bits = delay.strip().split(':')
        if len(bits) != 2:
            errmsg = 'Given delay %s at position %i is not a valid ' \
                     'delay setting' % (delay, ctr)
            LOGGER.error(errmsg)
            raise ValueError(errmsg)
        delay = bits[0]
        delay = delay.split(',')
        delay = (float(delay[0]), float(delay[1]))
        fringe = bits[1]
        fringe = fringe.split(',')
        fringe = (float(fringe[0]), float(fringe[1]))
        rv.append((delay, fringe))
    return rv


def prepare_delay_vals(coefficients, sample_rate):
    """

    :param coefficients: the delay and phase coefficients, as a tuple
    :param sample_rate: system sample rate, in Hz
    :return:
    """
    delay_coeff = coefficients[0]
    phase_coeff = coefficients[1]

    # convert delay in time into delay in clock cycles
    delay_s = float(delay_coeff[0]) * sample_rate

    # convert to fractions of a sample
    phase_offset_s = float(phase_coeff[0])/float(numpy.pi)

    # convert from radians per second to fractions of sample per sample
    delta_phase_offset_s = (float(phase_coeff[1]) / float(numpy.pi) /
                            sample_rate)

    return {'delay': delay_s,
            'delay_delta': delay_coeff[1],
            'phase_offset': phase_offset_s,
            'phase_offset_delta': delta_phase_offset_s}


class Delay(object):
    def __init__(self, delay=0, delay_delta=0,
                 phase_offset=0, phase_offset_delta=0,
                 load_time=None, load_wait=None, load_check=True):
        """
        :param delay is in samples
        :param delay_delta is in samples per sample
        :param phase_offset is in fractions of a sample
        :param phase_offset_delta is in samples per sample
        :param load_time is in samples since epoch
        :param load_wait is seconds to wait for delay values to load
        :param load_check whether to check if load happened
        """
        self.delay = delay
        self.delay_delta = delay_delta
        self.phase_offset = phase_offset
        self.phase_offset_delta = phase_offset_delta
        self.load_time = load_time
        self.load_wait = load_wait
        self.load_check = load_check
        self.load_count = -1
        self.error = Event()
