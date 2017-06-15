import logging


class Corr2LogHandler(logging.Handler):
    """
    Log handler for corr2 log messages
    """

    def __init__(self, max_len=1000):
        """
        Create a Corr2LogHandler.
        :param max_len: how many log messages should be stored in the FIFO
        :return:
        """
        raise DeprecationWarning
        logging.Handler.__init__(self)
        self._max_len = max_len
        self._records = []

    def emit(self, record):
        """
        Handle the arrival of a log message.
        """
        if len(self._records) >= self._max_len:
            self._records.pop(0)
        self._records.append(record)

    def clear_log(self):
        """
        Clear the log messages the handler is storing.
        """
        self._records = []

    def set_max_len(self, max_len):
        """
        Change the maximum number of log messages this handler stores.
        :param max_len:
        :return:
        """
        self._max_len = max_len

    def get_log_strings(self, num_to_print=-1):
        """
        Get the log record as strings
        :return:
        """
        log_list = []
        for ctr, record in enumerate(self._records):
            if ctr == num_to_print:
                break
            if record.exc_info:
                log_list.append('%s: %s Exception: ' % (record.name, record.msg))
            else:
                log_list.append('%s: %s' % (record.name, record.msg))
        return log_list

    def print_messages(self, num_to_print=-1):
        """
        Print the last num_to_print(messages. -1 is all of them.
        :return:
        """
        for ctr, record in enumerate(self._records):
            if ctr == num_to_print:
                break
            if record.exc_info:
                print('%s: %s Exception: ' % (record.name, record.msg))
            else:
                print('%s: %s' % (record.name, record.msg))
