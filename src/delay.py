from threading import Event


class DelaysUnsetError(Exception):
    pass


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
