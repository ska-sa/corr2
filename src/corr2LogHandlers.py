import logging
import termcolors
import datetime
import time
import os

from katcp import Message as KatcpMessage
from casperfpga import CasperLogHandlers

# Easier to re-declare constants than import them from data_stream
DIGITISER_ADC_SAMPLES = 0  # baseband-voltage
FENGINE_CHANNELISED_DATA = 1  # antenna-channelised-voltage
XENGINE_CROSS_PRODUCTS = 2  # baseline-correlation-products
BEAMFORMER_FREQUENCY_DOMAIN = 3  # tied-array-channelised-voltage
BEAMFORMER_TIME_DOMAIN = 4  # tied-array-voltage
BEAMFORMER_INCOHERENT = 5  # incoherent-beam-total-power
FLYS_EYE = 6  # antenna-correlation-products
ANTENNA_VOLTAGE_BUFFER = 7  # antenna-voltage-buffer

# Define the log-level ratio between corr2 objects and casperfpga objects up here
LOGGING_RATIO_CASPER_CORR = 2
# This returns an xrange object that can be iterated over when needed
# - It does not need to be re-initialised after iteration
LOG_LEVELS = xrange(0,60,10)


"""
Please note the following:
1. StreamHandler's in the context of logging refers to a log-handler that handles
   log messages printed to the screen
   -> NOT handling streams of data!
   -> I've since renamed logging StreamHandlers to ConsoleHandlers wherever possible
      and necessary to avoid confusion

"""

LOGGER = logging.getLogger(__name__)
console_handler = CasperLogHandlers.CasperConsoleHandler(name=__name__)
LOGGER.addHandler(console_handler)
LOGGER.setLevel(logging.ERROR)

# region --- Custom getLogger command(s) for corr2 ---

def getLogger(logger_name, log_level=logging.DEBUG, *args, **kwargs):
    """
    First point of contact whenever an object tries to getLogger
    - This will change according to application, i.e. ipython or corr2_servlet
    - By default, this will point to getConsoleLogger
    Params logger_name and log_level are common to all (custom) getLogger's
    """
    # This is common to all getLogger's
    
    return getConsoleLogger(logger_name, log_level, *args, **kwargs)


def getConsoleLogger(logger_name, log_level=logging.DEBUG, *args, **kwargs):
    """
    Custom method allowing us to add default handlers to a logger
    :param logger_name: Mandatory, logger needs to have a name!
    :param log_level: All Instrument-level entities log at logging.DEBUG
                    - All Board-level entities log at logging.ERROR
    :return: Tuple - Boolean Success/Fail, True/False
                   - Logger entity with ConsoleHandler added as default
    """
    
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        # logger has handlers already... ?
        return True, logger
    else:
        # Add ConsoleHandler
        console_handler_name = '{}_console'.format(logger_name)
        if not CasperLogHandlers.configure_console_logging(logger, console_handler_name):
            return False, logger

    # Set the log-level before returning
    logger.setLevel(log_level)

    return True, logger


# def getKatcpLogger(logger_name, sock, log_level=logging.DEBUG, *args, **kwargs):
def getKatcpLogger(logger_name, mass_inform_func, log_level=logging.DEBUG, *args, **kwargs):
    """
    Custom method allowing us to add default handlers to a logger
    :param logger_name:
    :param sock:
    :return: Tuple - Boolean Success/Fail, True/False
                   - Logger entity with Katcp and File Handlers added as default
    """
    try:
        # Doing it this way for now
        filename = kwargs['log_filename']
    except KeyError:
        filename = '{}.log'.format(logger_name)
    try:
        file_dir = kwargs['log_file_dir']
        # Check if the log_file_dir specified exists
        if not os.path.exists(file_dir):
            # Problem
            warningmsg = 'Problem with the file-directory specified: {}' \
                    '\nMake sure you have write access to the path.' \
                    '\nDefaulting to current working directory...'.format(file_dir)
            LOGGER.warning(warningmsg)
            file_dir = '.'
    except KeyError:
        file_dir = '.'

    abs_path = os.path.abspath(file_dir)
    full_log_file_path = '{}/{}'.format(abs_path, filename)

    logger = logging.getLogger(logger_name)

    if logger.handlers:
        # We can remove them
        # - If we instantiate a logger with the same name
        #   it will still maintain 'object ID'
        # logger.handlers = []

        # Yes, isinstance(handler, logging.HandlerType),
        # but it isn't working as expected
        logger.handlers = [handler for handler in logger.handlers if type(handler) != CasperLogHandlers.CasperConsoleHandler]

    katcp_handler_name = '{}_katcp'.format(logger_name)
    new_katcp_handler = KatcpHandler(name=katcp_handler_name, mass_inform_func=mass_inform_func) #sock=sock)
    logger.addHandler(new_katcp_handler)

    # Now add the FileHandler
    # - Better practice to keep FileHandler and KatcpHandler separate
    # - All instances of the FileHandler will need to point towards the same file
    # - Filename follows the format: instrument_name.log
    corr2_file_handler = logging.FileHandler(filename=full_log_file_path)
    corr2_file_handler.name = '{}_file'.format(logger_name)

    format_string = '%(asctime)s - %(levelname)s - %(name)s %(filename)s:%(lineno)s - %(msg)s'
    file_handler_formatter = logging.Formatter(format_string)
    corr2_file_handler.setFormatter(file_handler_formatter)

    logger.addHandler(corr2_file_handler)

    # Set the log-level before returning
    logger.setLevel(log_level)

    return True, logger


def create_casper_file_handler(logger, filename, file_dir='/var/log/'):
    """
    Packaging adding logging.FileHandler to an existing logger purely because
    it's much easier than overloading the class
    :param logger: Logging entity to add FileHandler to
    :param filename: Filename to log log-records to
    :param file_dir: Optional, might be included in the filename
    :return: Tuple - Boolean Success/Fail
                   -
    """
    # Not done yet!
    raise NotImplementedError

    # First, check if a file-directory has been specified
    if len(file_dir) > 0:
        if os.path.exists(file_dir):
            # It's legit
            LOGGER.debug('Path exists')
        else:
            # Ignore it (?)
            LOGGER.error('Path does not exist')
    new_file_handler = logging.FileHandler(filename=filename)

    return True

# endregion

# region -- KatcpHandler --

class KatcpHandler(CasperLogHandlers.CasperConsoleHandler):
    """
    Custom ConsoleHandler to log messages to Katcp
    - Basically like any other logging.Handler, except here we sock.inform
      instead of print()
    - It is worth noting that sock.mass_inform needs a Katcp Message object
        - The message itself 
    """

    def __init__(self, name, mass_inform_func, *args, **kwargs):
        """
        Initialise the KatcpHandler with the intended comms socket
        :param sock: KatcpHandler always needs a socket to log to!
        :return: None
        """

        super(KatcpHandler, self).__init__(name, *args, **kwargs)

        # These always need to be present
        self.name = name
        # self.sock = sock
        self.mass_inform_func = mass_inform_func

        try:
            self._max_len = kwargs['max_len']
        except KeyError:
            self._max_len = 1000

        self._records = []

    def emit(self, message):
        """
        Handle a log message
        :param message: Log message as a dictionary
        :return: True/False - Success/Fail
        """
        if len(self._records) >= self._max_len:
            self._records.pop(0)

        # Might as well check here for the initial 'Successfully created instrument'
        # message here and remove any fancy formatting

        self._records.append(message)
        # import IPython
        # IPython.embed()
        # Need to construct the katcp.Message object
        # - The pass it to a sock.mass_inform() to ensure it is #log'd
        message_type = KatcpMessage.INFORM
        message_name = 'log'
        # - LEVEL timestamp_ms name message
        # - LEVEL E {INFO, WARN, ERROR, FATAL}

        time_now = str(time.time())
        # "arguments" argument of KatcpMessage needs to be such a list.
        message_data = [message.levelname, time_now, message.name, message.msg]
        log_message = KatcpMessage(message_type, message_name, arguments=message_data)
        
        # self.sock.mass_inform(log_message)
        self.mass_inform_func(log_message)
        
    def format(self, record):
        """
        :param record: Log message as a dictionary, of type logging.LogRecord
        :return: Formatted message
        """

        formatted_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-4]
        formatted_string = '{} {} {} {}:{} - {}'.format(formatted_datetime, record.levelname, record.name,
                                                        record.filename, str(record.lineno), record.msg)
        
        return formatted_string

# endregion

# ----------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------

# region --- Logger configuration methods ---

def get_all_loggers():
    """
    Packaging a logging library function call, for testing
    :return: dictionary of logging objects
    """
    return logging.Logger.manager.loggerDict


def check_logging_level(logging_level):
    """
    Generic function to carry out a sanity check on the logging_level
    used to setup the logger
    :param logging_level: String input defining the logging_level:
                             Level      | Numeric Value
                             --------------------------
                             CRITICAL   | 50
                             ERROR      | 40
                             WARNING    | 30
                             INFO       | 20
                             DEBUG      | 10
                             NOTSET     | 0

    :return: Tuple - (Success/Fail, None/logging_level)
    """
    logging_level_numeric = getattr(logging, logging_level, None)
    if not isinstance(logging_level_numeric, int):
        return False, None
    # else: Continue
    return True, logging_level_numeric


def increase_log_levels(logger_group=None, log_level_increment=10):
    """
    Neatly packaged function to increase log_levels of certain 
    """

    return NotImplementedError


def get_logger_group(logger_dict=None, group_name=None):
    """
    Method to fetch all logger entities that match the group_name specified
    :param logger_dict: Dictionary of loggers - {logger_name, logging_entity}
    :param group_name: String that is found in loggers to be fetched
    :return: Dictionary of logger entities whose keys match group_name
    """
    if group_name is None or group_name is '':
        # Problem
        errmsg = 'Logger group name cannot be empty'
        LOGGER.error(errmsg)
        return None
    if logger_dict is None:
        logger_dict = logging.Logger.manager.loggerDict
    keys = logger_dict.keys()

    logger_group = {}

    for key in keys:
        if key.lower().find(group_name) >= 0:
            logger_group[key] = logger_dict[key]
            # else: pass

    return logger_group


def set_logger_group_level(logger_group, log_level=logging.DEBUG):
    """
    ** Take in log_level as an INTEGER **
    Method to set the log-level of a group of loggers
    :param logger_group: List of logging entities
    :param log_level: Effectively of type integer E logging.{CRITICAL,ERROR,WARNING,DEBUG,INFO}
    :return: Boolean - Success/Fail - True/False
    """

    # First, error-check the log_level specified
    # result, log_level_numeric = check_logging_level(log_level)
    result = isinstance(log_level, int)
    if not result:
        # Problem
        errmsg = 'Error with log_level specified: {}'.format(log_level)
        LOGGER.error(errmsg)
        return False

    for logger_value in logger_group:
        # logger_value.setLevel(log_level_numeric)
        logger_value.setLevel(log_level)

    debugmsg = 'Successfully updated log-level of {} SKARABs to {}'.format(str(len(logger_group)), log_level)
    LOGGER.debug(debugmsg)
    return True


def add_handler_to_loggers(logger_dict, log_handler):
    """
    Adds a log handler to a group of loggers
    :param logger_dict: dictionary of logger objects
    :param log_handler: log-handler specified/instantiated by the user
    :return: Boolean - True/False, Success/Fail
    """

    # Need to error-check that the log_handler specified is actually
    # of type logging.Handler
    if not hasattr(log_handler, 'emit'):
        # Impostor!
        errmsg = 'Log-handler specified is not of type logging.Handler. ' \
                 'Unable to add Handler {} to logger group'.format(log_handler)
        LOGGER.error(errmsg)
        return False

    for logger_key, logger_value in logger_dict.items():
        if not _add_handler_to_logger(logger_value, log_handler):
            # Problem
            return False
            # else: Continue
    debugmsg = 'Successfully added log_handler to group of {} loggers'.format(str(len(logger_dict)))
    LOGGER.debug(debugmsg)

    return True


def _add_handler_to_logger(logger, log_handler):
    """
    Abstracted method from adding log-handler to group to localise error-checking
    :param logger: logging entity
    :param log_handler: log-handler specified/instantiated by the user
    :return: Boolean - True/False, Success/Fail
    """
    # First check if the log_handler has already been added to the logger
    # Or if the logger already has a log-handler with the same name
    handlers = logger.handlers
    for handler in handlers:
        # ** We don't care what type of handler it is **
        # if hasattr(handler, 'baseFilename'):
        #     # It's a FileHandler, not a StreamHandler(/KatcpHandler)
        #     continue
        # else:
            # StreamHandler, probably
        if handler.name.lower() == log_handler.name.lower():
            # Problem
            errmsg = 'skarab "{}" have multiple log-handlers with ' \
                     'the same name: {}'.format(logger.name, log_handler.name)
            LOGGER.error(errmsg)
            return False
        # else: All good

    # Separate method to set the log-level
    logger.addHandler(log_handler)

    debugmsg = 'Successfully added log_handler to logger-{}'.format(logger.name)
    LOGGER.debug(debugmsg)
    return True


def get_log_handler_by_name(log_handler_name, logger_dict=None):
    """

    :param log_handler_name:
    :param logger_dict:
    :return: log_handler_return - Should be of type logging.Handler (at least parent)
    """

    # Sanity check on log_handler_name
    if log_handler_name is None or log_handler_name is '':
        # Problem
        errmsg = 'No log-handler name specified'
        LOGGER.error(errmsg)
        return False

    for logger_key, logger_value in logger_dict:
        if type(logger_value) is not logging.Logger:
            # Don't need it
            continue
        else:
            for handler in logger_value.handlers:
                # We stop when we find the first instance of this handler
                if handler.name.find(log_handler_name) >= 0:
                    # Found it
                    return handler


def set_feng_loglevel(feng_logger_dict, log_level=logging.DEBUG):
    """
    Neatly packaged function for setting all F-engine loggers to some log_level
    :param feng_logger_dict: Dictionary of F-engines - {feng_name: feng_logger}
    :param log_level: log-level required to set logger entities to
    :return: Boolean - Success/Fail - True/False
    """

    for feng_name, feng_logger in feng_logger_dict.iter():
        feng_logger.setLevel(log_level)


def _remove_handler_from_logger(logger, log_handler_name):
    """
    Removes handler from logging entity
    - Just easier to do it by name, rather than type
    :return:
    """
    # Because we can't act on the list we need to scroll through
    log_handlers = logger.handlers

    for handler in log_handlers:
        if handler.name.find(log_handler_name) > 0:
            # Nice
            logger.removeHandler(handler)

    return True


def remove_all_loggers(logger_dict=None):
    """

    :param logger_dict: Dictionary of loggers and their corresponding
                        logging entities
    :return: Boolean - Success/Fail - True/False
    """

    if logger_dict is None:
        logger_dict = logging.Logger.manager.loggerDict

    num_handlers = 0
    for logger_key, logger_value in logger_dict.items():
        num_handlers = len(logger_value.handlers)
        logger_value.handlers = []
        debugmsg = 'Successfully removed {} Handlers from ' \
                   'logger-{}'.format(num_handlers, logger_key)
        LOGGER.debug(debugmsg)

    return True

# endregion


# region --- Methods related to getting specific logger groups ---

def get_instrument_loggers(corr_obj, group_name):
        """
        Separating concerns from corr2LogHandlers because the instrument object already exists here.
        :param corr_obj: Correlator object to get all these loggers from!
        :param group_name: Should correspond to names in logger_group_dict.keys() below
        :return: tuple - (list, list) - (corr2-based loggers, casperfpga-based loggers)
        """
        # Silly dictionary doesn't keep order by default!
        # logger_group_keys = logger_group_dict.keys()
        
        if corr_obj is None:  # i.e. if the instrument hasn't been initialised yet.
            return None, None

        if group_name == '' or group_name == 'instrument':
            # Need to get all loggers
            instrument_loggers = []
            instrument_loggers.append(corr_obj.logger)
            for value in get_f_loggers(corr_obj):
                instrument_loggers.append(value)
            for value in get_x_loggers(corr_obj):
                instrument_loggers.append(value)
            for value in get_b_loggers(corr_obj):
                instrument_loggers.append(value)

            skarab_loggers = []
            for value in get_ffpga_loggers(corr_obj):
                skarab_loggers.append(value)
            for value in get_xfpga_loggers(corr_obj):
                skarab_loggers.append(value)
            
            # Just so I don't have to separate the list on the other side again
            return instrument_loggers, skarab_loggers

        elif group_name == 'feng':
            # Get f-related loggers
            return get_f_loggers(corr_obj), None
            
        elif group_name == 'xeng':
            # Get x-related loggers
            return get_x_loggers(corr_obj), None
            
        elif group_name == 'beng':
            # Get b-related loggers
            return get_b_loggers(corr_obj), None
            
        elif group_name == 'delaytracking':
            # Get delaytracking loggers
            return get_feng_stream_loggers(corr_obj), None
            
        elif group_name == 'ffpgas':
            # Get fhost_fpga CasperFpga loggers
            return get_ffpga_loggers(corr_obj), None

        elif group_name == 'xfpgas':
            # Get f-related loggers
            return get_xfpga_loggers(corr_obj), None
        else:
            # Problem?
            return None, None


def get_f_loggers(corr_obj):
    return_list = []
    return_list.append(corr_obj.fops.logger)
    for value in get_feng_loggers(corr_obj):
        return_list.append(value)
    for value in get_fhost_loggers(corr_obj):
        return_list.append(value)
    for value in get_feng_stream_loggers(corr_obj):
        return_list.append(value)
    return return_list


def get_x_loggers(corr_obj):
    return_list = []
    return_list.append(corr_obj.xops.logger)
    for value in get_xhost_loggers(corr_obj):
        return_list.append(value)
    for value in get_xeng_stream_loggers(corr_obj):
        return_list.append(value)
    return return_list


def get_b_loggers(corr_obj):
    return_list = []
    return_list.append(corr_obj.bops.logger)
    for value in get_bhost_loggers(corr_obj):
        return_list.append(value)
    for value in get_beng_stream_loggers(corr_obj):
        return_list.append(value)
    return return_list

def get_feng_loggers(corr_obj):
    return (feng.logger for feng in corr_obj.fops.fengines)

def get_fhost_loggers(corr_obj):
    return (fhost.logger for fhost in corr_obj.fhosts)

def get_xhost_loggers(corr_obj):
    return (xhost.logger for xhost in corr_obj.xhosts)

def get_bhost_loggers(corr_obj):
    return (bhost.logger for bhost in corr_obj.bops.hosts)

def get_feng_stream_loggers(corr_obj):
    return_list = []
    for value in corr_obj.get_data_streams_by_type(FENGINE_CHANNELISED_DATA):
        return_list.append(value.logger)
    for value in corr_obj.get_data_streams_by_type(DIGITISER_ADC_SAMPLES):
        return_list.append(value.logger)

    return return_list

def get_xeng_stream_loggers(corr_obj):
    return (stream.logger for stream in corr_obj.get_data_streams_by_type(XENGINE_CROSS_PRODUCTS))

def get_beng_stream_loggers(corr_obj):
    return_list = []
    for value in corr_obj.get_data_streams_by_type(BEAMFORMER_FREQUENCY_DOMAIN):
        return_list.append(value.logger)
    for value in corr_obj.get_data_streams_by_type(BEAMFORMER_TIME_DOMAIN):
        return_list.append(value.logger)
    for value in corr_obj.get_data_streams_by_type(BEAMFORMER_INCOHERENT):
        return_list.append(value.logger)

    return return_list
    
def get_ffpga_loggers(corr_obj):
    return (fhost.transport.logger for fhost in corr_obj.fhosts)

def get_xfpga_loggers(corr_obj):
    return (xhost.transport.logger for xhost in corr_obj.xhosts)

# endregion