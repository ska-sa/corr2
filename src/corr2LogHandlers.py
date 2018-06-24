import logging
import termcolors
import datetime
import os

from katcp import Message as KatcpMessage
from casperfpga import CasperLogHandlers


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

def modify_getLogger(module_name, source_function_name, dest_function_name):
    """
    Used to dynamically switch between getLogger function-calls across an entire module

    """

    module_object_names = [value for value in dir(module) if not value.startswith('__')]
    
    for this_object_name in module_object_names:
        # Get entities from this_object
        
        # Scroll through each entity for the object
        object_entities = []


def modify_getLogger_katcp():
    """
    Used to dynamically switch between getLogger function-calls across corr2

    """

    module_object_names = [value for value in dir(corr2) if not value.startswith('__')]
    
    for this_object_name in module_object_names:
        # Get entities from this_object
        
        # Scroll through each entity for the object
        object_entities = []


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


def getKatcpLogger(logger_name, sock, log_level=logging.DEBUG, *args, **kwargs):
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
    new_katcp_handler = KatcpHandler(name=katcp_handler_name, sock=sock)
    logger.addHandler(new_katcp_handler)

    # Now add the FileHandler
    # - Better practice to keep FileHandler and KatcpHandler separate
    # - All instances of the FileHandler will need to point towards the same file
    # - Filename follows the format: instrument_name.log
    corr2_file_handler = logging.FileHandler(filename=full_log_file_path)
    corr2_file_handler.name = '{}_file'.format(logger_name)

    formatted_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-4]
    format_string = formatted_datetime + ' - %(levelname)s - %(name)s %(filename)s:%(lineno)s - %(msg)s'
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

    def __init__(self, name, sock, *args, **kwargs):
        """
        Initialise the KatcpHandler with the intended comms socket
        :param sock: KatcpHandler always needs a socket to log to!
        :return: None
        """

        super(KatcpHandler, self).__init__(name, *args, **kwargs)

        # These always need to be present
        self.name = name
        self.sock = sock

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

        self._records.append(message)
        # import IPython
        # IPython.embed()
        # Need to construct the katcp.Message object
        # - The pass it to a sock.mass_inform() to ensure it is #log'd
        message_type = KatcpMessage.INFORM
        message_name = 'log'
        message_data = [self.format(message)]
        
        log_message = KatcpMessage(message_type, message_name, message_data)
        
        self.sock.mass_inform(log_message)

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

    for value in keys:
        if value.find(group_name) >= 0:
            logger_group[value] = logger_dict[value]
            # else: pass

    return logger_group


def set_logger_group_level(logger_group, log_level=logging.DEBUG):
    """
    ** Take in log_level as an INTEGER **
    Method to set the log-level of a group of loggers
    :param logger_group: Dictionary of logger and logging entities
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

    for logger_key, logger_value in logger_group.items():
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
        if handler.name.upper() == log_handler.name.upper():
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


def configure_console_log_feng(feng_list, console_handler_name):
    """
    Packaged function to handle creating Console Handlers for
    F-Engine loggers
    :param feng_list: List of Feng objects
                      - Assumed to already have logging entities
    :
    """

    


    raise NotImplementedError


def configure_console_log_xeng(xeng_list, console_handler_name):
    """
    Packaged function to handle creating Console Handlers for
    X-Engine loggers
    :param feng_list: List of Feng objects
                      - Assumed to already have logging entities
    :
    """

    


    raise NotImplementedError


def configure_console_log_beng(beng_list, console_handler_name):
    """
    Packaged function to handle creating Console Handlers for
    B-Engine loggers
    :param feng_list: List of Feng objects
                      - Assumed to already have logging entities
    :
    """

    


    raise NotImplementedError


def create_console_handler(handler_name, logger_entity=None):
    """
    'Wrapper method' to allow the user to create a ConsoleHandler (StreamHandler)
    to print debug messages to screen

    """


    raise NotImplementedError


def create_file_handler(handler_name, filename, file_dir):
    """
    Conveniently wrapped function for creating a file-handler for an intended logger(s)
    :param handler_name:
    """

    raise NotImplementedError


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
