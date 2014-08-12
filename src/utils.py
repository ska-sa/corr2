__author__ = 'paulp'

import time
from ConfigParser import SafeConfigParser
import logging

LOGGER = logging.getLogger(__name__)


def parse_ini_file(ini_file, required_sections=None):
    """
    Parse an ini file into a dictionary. No checking done at all.
    :return: a dictionary containing the configuration
    """
    if required_sections is None:
        required_sections = []
    parser = SafeConfigParser()
    files = parser.read(ini_file)
    if len(files) == 0:
        raise IOError('Could not read the config file, %s' % ini_file)
    for check_section in required_sections:
        if not parser.has_section(check_section):
            raise ValueError('The config file does not seem to have the required %s section?' % check_section)
    config = {}
    for section in parser.sections():
        config[section] = {}
        for items in parser.items(section):
            config[section][items[0]] = items[1]
    return config


def program_fpgas(progfile, fpgas, timeout=10):
    """Program more than one FPGA at the same time.
    :param progfile: string, the filename of the file to use to program the FPGAs
    :param fpgas: a list of objects for the FPGAs to be programmed
    :return: <nothing>
    """
    stime = time.time()
    chilltime = 0.1
    waiting = []
    for fpga in fpgas:
        try:
            len(fpga)
        except TypeError:
            fpga.upload_to_ram_and_program(progfile, wait_complete=False)
            waiting.append(fpga)
        else:
            fpga[0].upload_to_ram_and_program(fpga[1], wait_complete=False)
            waiting.append(fpga[0])
    starttime = time.time()
    while time.time() - starttime < timeout:
        donelist = []
        for fpga in waiting:
            if fpga.is_running():
                donelist.append(fpga)
        for done in donelist:
            waiting.pop(waiting.index(done))
        if len(waiting) > 0:
            time.sleep(chilltime)
        else:
            break
    etime = time.time()
    if len(waiting) > 0:
        raise RuntimeError('Timed out waiting for FPGA programming to complete.')
    LOGGER.info('Programming %d FPGAs took %.3f seconds.' % (len(fpgas), etime - stime))


def hosts_from_config_file(config_file):
    """
    Make lists of hosts from a given correlator config file.
    :return: a dictionary of hosts, by type
    """
    config = parse_ini_file(config_file)
    rv = {}
    for sectionkey in config.keys():
        if 'hosts' in config[sectionkey].keys():
            hosts = config[sectionkey]['hosts'].split(',')
            for ctr, host_ in enumerate(hosts):
                hosts[ctr] = host_.strip()
            rv[sectionkey] = hosts
    return rv


def non_blocking_request(fpgas, timeout, request, request_args):
    """Make a non-blocking request to one or more FPGAs, using the Asynchronous FPGA client.
    """
    import Queue
    import threading

    reply_queue = Queue.Queue(maxsize=len(fpgas))
    requests = {}
    replies = {}

    # reply callback
    def reply_cb(host, req_id):
        LOGGER.debug('Reply(%s) from host(%s)' % (req_id, host))
        reply_queue.put_nowait([host, req_id])

    # start the requests
    LOGGER.debug('Send request(%s) to %i hosts.' % (request, len(fpgas)))
    lock = threading.Lock()
    for fpga_ in fpgas:
        lock.acquire()
        req = fpga_.nb_request(request, None, reply_cb, *request_args)
        requests[req['host']] = [req['request'], req['id']]
        lock.release()
        LOGGER.debug('Request \'%s\' id(%s) to host(%s)' % (req['request'], req['id'], req['host']))

    # wait for replies from the requests
    timedout = False
    done = False
    while (not timedout) and (not done):
        try:
            it = reply_queue.get(block=True, timeout=timeout)
        except:
            timedout = True
            break
        replies[it[0]] = it[1]
        if len(replies) == len(fpgas):
            done = True
    if timedout:
        LOGGER.error('non_blocking_request timeout after %is.' % timeout)
        LOGGER.error(replies)
        raise RuntimeError('non_blocking_request timeout after %is.' % timeout)

    # process the replies
    rv = {}
    for fpga_ in fpgas:
        try:
            request_id = replies[fpga_.host]
        except KeyError:
            LOGGER.error(replies)
            raise KeyError('Didn\'t get a reply for FPGA \'%s\' so the '
                           'request \'%s\' probably didn\'t complete.' % (fpga_.host, request))
        reply, informs = fpga_.nb_get_request_result(request_id)
        frv = {'request': requests[fpga_.host][0],
               'reply': reply.arguments[0],
               'reply_args': reply.arguments}
        informlist = []
        for inf in informs:
            informlist.append(inf.arguments)
        frv['informs'] = informlist
        rv[fpga_.host] = frv
        fpga_.nb_pop_request_by_id(request_id)
    return rv
