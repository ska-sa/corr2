from threading import Event
import logging
import numpy

LOGGER = logging.getLogger(__name__)


class DelaysUnsetError(Exception):
    pass


def process_list(delay_list, sample_rate_hz):
    """
    Given a list of strings or delay tuples, return a list of delay tuples
    NOTE: THIS WILL CONVERT SECONDS TO SAMPLES FOR DELAY!
    :param delay_list: a list of strings (delay,rate:phase,rate) or
        delay tuples ((delay,rate),(phase,rate))
    :param sample_rate_hz: the sample rate of the incoming data
    :return: a list of Delay objects
    """
    def process_string(delaystr):
        bits = delaystr.strip().split(':')
        delay = bits[0]
        delay = delay.split(',')
        delay = (float(delay[0]), float(delay[1]))
        fringe = bits[1]
        fringe = fringe.split(',')
        fringe = (float(fringe[0]), float(fringe[1]))
        return delay, fringe
    rv = []
    for ctr, delay in enumerate(delay_list):
        try:
            if isinstance(delay, str):
                delaytup = process_string(delay)
            else:
                delaytup = delay
            rv.append(prepare_delay_vals(delaytup, sample_rate_hz))
        except:
            errmsg = 'delay.process_list(): given delay \'%s\' at position %i' \
                     ' is not a valid delay setting' % (delay, ctr)
            LOGGER.error(errmsg)
            raise ValueError(errmsg)
    return rv


def prepare_delay_vals(coefficients, sample_rate):
    """

    :param coefficients: the delay and phase coefficients, as a tuple
    :param sample_rate: system sample rate, in Hz
    :return:
    """
    if len(coefficients) != 2:
        errmsg = 'Incorrectly supplied coefficient tuple: %s. Expecting ((delay,rate),(phase,rate)).' % coefficients
        LOGGER.error(errmsg)
        raise ValueError(errmsg)
    delay_coeff = coefficients[0]
    phase_coeff = coefficients[1]
    # convert delay in time into delay in clock cycles
    delay_s = float(delay_coeff[0]) * sample_rate
    # convert to fractions of a sample
    phase_offset_s = float(phase_coeff[0])/float(numpy.pi)
    # convert from radians per second to fractions of sample per sample
    delta_phase_offset_s = (float(phase_coeff[1]) / float(numpy.pi) /
                            sample_rate)
    return Delay(delay_s, delay_coeff[1], phase_offset_s, delta_phase_offset_s)


class Delay(object):
    def __init__(self, delay=0.0, delay_delta=0.0,
                 phase_offset=0.0, phase_offset_delta=0.0,
                 load_mcnt=None, load_count=-1, last_load_success=True):
        """
        :param delay is in samples
        :param delay_delta is in samples per sample
        :param phase_offset is in fractions of a sample
        :param phase_offset_delta is in samples per sample
        :param load_mcnt is in samples since epoch
        :param last_load_success: boolean, did the last delay load succeed?
        """
        self.delay = delay
        self.delay_delta = delay_delta
        self.phase_offset = phase_offset
        self.phase_offset_delta = phase_offset_delta
        self.load_mcnt = load_mcnt
        self.last_load_success = last_load_success
        self.load_count = load_count
        self.error = Event()

    # @classmethod
    # def from_coefficients(cls, coefficients, sample_rate):
    #     coeff_tuple = process_list([coefficients])[0]
    #     return prepare_delay_vals(coeff_tuple, sample_rate)

    def __str__(self):
        return '{},{}:{},{}'.format(self.delay, self.delay_delta,
                                    self.phase_offset, self.phase_offset_delta)

# end
