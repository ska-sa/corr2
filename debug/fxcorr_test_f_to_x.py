#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
 Capture utility for a relatively generic packetised correlator data output stream.

 The script performs two primary roles:

 Storage of stream data on disk in hdf5 format. This includes placing meta data into the file as attributes.

 Regeneration of a SPEAD stream suitable for us in the online signal displays. At the moment this is basically
 just an aggregate of the incoming streams from the multiple x engines scaled with n_accumulations (if set)

Author: Simon Ratcliffe
Revs:
2010-11-26  JRM Added command-line option for autoscaling.
"""

import spead2
import spead2.recv as s2rx
import numpy as np
import time
import threading
import os
import logging
import sys

FREQS_UNDER_TEST = []
ANTS_UNDER_TEST = []
BLS_UNDER_TEST = []
BASELINES = []
NUM_HEAPS = -1
N_CHANS = 0

def ants_to_baselines(ants):
    bls = []
    for ant in ants:
        for other_ant in ants:
            for bls_ctr, baseline in enumerate(BASELINES):
                if baseline[0] == ant and baseline[1] == other_ant:
                    bls.append(bls_ctr)
    baselines = []
    for baseline in bls:
        if baseline not in baselines:
            baselines.append(baseline)
    return baselines


def do_things_first(ig, logger):
    if items is None:
        return
    for name in ig.keys():
        if name not in items:
            continue
        item = ig.get_item(name)
        if not item.has_changed():
            continue
        logger.info('(%s) %s => %s' % (time.ctime(), name, str(ig[name])))


def check_data_things(ig, heap_ctr):
    if 'xeng_raw' not in ig.keys():
        return 0
    if ig['xeng_raw'] is None:
        return 0
    xeng_raw = ig['xeng_raw'].value
    if xeng_raw is None:
        return 0

    print(heap_ctr, 'rx\'d heap:', np.shape(xeng_raw)

    err_bls = []
    okay_bls = []

    for baseline in range(0, len(BASELINES)):
        bdata = xeng_raw[:, baseline]

        err = False

        if VERBOSE: print('\ttesting baseline:', baseline, BASELINES[baseline]
        if baseline in BLS_UNDER_TEST:
            non_zero_range = FREQS_UNDER_TEST
            zero_range = range(0, min(FREQS_UNDER_TEST))
            zero_range.extend(range(max(FREQS_UNDER_TEST)+1, N_CHANS))
        else:
            non_zero_range = []
            zero_range = range(N_CHANS)

        if VERBOSE: print('\t\ttesting should-be-zero fchans:'
        for ctr in zero_range:
            complex_tuple = bdata[ctr]
            pwr = (complex_tuple[0] ** 2) + (complex_tuple[1] ** 2)
            if pwr != 0.0:
                if VERBOSE:
                    print('\t\t\tfchan(%i) != 0: 2^%.5f + 2^%.5f = %.5f' % (ctr, complex_tuple[0], complex_tuple[1], pwr)
                err = True
            # assert pwr == 0.0

        if VERBOSE: print('\t\ttesting should-be-non-zero fchans:'
        for ctr in non_zero_range:
            complex_tuple = bdata[ctr]
            pwr = (complex_tuple[0] ** 2) + (complex_tuple[1] ** 2)
            if VERBOSE:
                print('\t\t\tfchan(%i): 2^%.5f + 2^%.5f = %.5f' % (ctr, complex_tuple[0], complex_tuple[1], pwr)
            #if pwr == 0.0:
            #    cplx_bef = bdata[ctr - 1]
            #    pwr_bef = (complex_tuple[0] ** 2) + (complex_tuple[1] ** 2)
            #    pwr_aft = (complex_tuple[0] ** 2) + (complex_tuple[1] ** 2)
            #assert pwr != 0.0

        if err:
            err_bls.append(baseline)
        else:
            okay_bls.append(baseline)

    print('\tbaselines in error:', err_bls
    print('\tbaselines okay:', okay_bls
    print(''
    sys.stdout.flush()
    return 1


class CorrRx(threading.Thread):
    def __init__(self, port=7148,
                 log_handler=None,
                 log_level=logging.INFO,
                 spead_log_level=logging.INFO,
                 **kwargs):
        # if log_handler == None:
        #     log_handler = log_handlers.DebugLogHandler(100)
        # self.log_handler = log_handler
        # self.logger = logging.getLogger('rx')
        # self.logger.addHandler(self.log_handler)
        # self.logger.setLevel(log_level)
        self.logger = logging.getLogger(__name__)
        spead2._logger.setLevel(logging.DEBUG)
        self._target = self.rx_cont
        self._kwargs = kwargs
        self.quit_event = quit_event
        threading.Thread.__init__(self)

    def run(self):
        print('starting target with kwargs ', self._kwargs
        self._target(**self._kwargs)

    def rx_cont(self, data_port=7148, acc_scale=True,
                filename=None, items=None, **kwargs):

        logger = self.logger
        logger.info('Data reception on port %i.' % data_port)

        strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0,
                           max_heaps=8, ring_heaps=8)
        strm.add_udp_reader(port=data_port, max_size=9200,
                            buffer_size=5120000)

        ig = spead2.ItemGroup()
        idx = 0

        last_cnt = -1
        heap_ctr = 0

        for heap in strm:
            ig.update(heap)

            cnt_diff = heap.cnt - last_cnt
            last_cnt = heap.cnt

            logger.debug('PROCESSING HEAP idx(%i) cnt(%i) cnt_diff(%i) '
                         '@ %.4f' % (idx, heap.cnt, cnt_diff, time.time()))

            do_things_first(ig, logger)

            ctradd = check_data_things(ig, heap_ctr)

            heap_ctr += ctradd

            if NUM_HEAPS > -1:
                if heap_ctr >= NUM_HEAPS:
                    self.quit_event.set()

            if self.quit_event.is_set():
                logger.info('Got a quit signal from somewhere, exiting rx loop...')
                break

            idx += 1

        strm.stop()
        logger.info("Files and sockets closed.")
        self.quit_event.clear()

# some defaults
filename = None
plotbaseline = None
items = None

if __name__ == '__main__':
    import argparse

    from corr2 import utils

    parser = argparse.ArgumentParser(description='test data from a correlator.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config', dest='config', action='store', default='',
                        help='corr2 config file')
    parser.add_argument('--inputs', dest='inputlist', action='store', default='', type=str,
                        help='Comma-seperated list of inputs to check.')
    parser.add_argument('--freqs', dest='freqlist', action='store', default='', type=str,
                        help='Comma-seperated tuple for start and stop freq chans to check.')
    parser.add_argument('--numheaps', dest='numheaps', action='store', default=-1, type=int,
                        help='How many heaps should be checked?')
    parser.add_argument('--verbose', dest='verbose', action='store_true', default=False,
                        help='Print each incorrect frequency in each incorrect baseline')
    parser.add_argument('--log', dest='log', action='store_true', default=False,
                        help='Logarithmic y axis.')
    parser.add_argument('--loglevel', dest='log_level', action='store', default='INFO',
                        help='log level to use, default INFO, options INFO, DEBUG, ERROR')
    parser.add_argument('--speadloglevel', dest='spead_log_level', action='store', default='INFO',
                        help='log level to use in spead receiver, default INFO, options INFO, DEBUG, ERROR')
    args = parser.parse_args()

    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']

    VERBOSE = args.verbose

    # load the rx port and sd info from the config file
    config = utils.parse_ini_file(args.config)
    data_port = int(config['xengine']['output_destination_port'])
    n_chans = int(config['fengine']['n_chans'])

    N_CHANS = n_chans

    NUM_HEAPS = args.numheaps
    HEAP_CTR = 0

    BASELINES = utils.baselines_from_config(config=config)

    ANTS_UNDER_TEST = args.inputlist.split(',')
    freqs = args.freqlist.split(',')
    fstart = int(freqs[0])
    fstop = int(freqs[1])
    FREQS_UNDER_TEST = range(fstart, fstop)

    BLS_UNDER_TEST = ants_to_baselines(ANTS_UNDER_TEST)
    print('testing frequencies:', min(FREQS_UNDER_TEST), '-', max(FREQS_UNDER_TEST)
    print('testing ants:', ANTS_UNDER_TEST
    print('testing baselines:', BLS_UNDER_TEST
    print('checking %i heaps' % NUM_HEAPS

    fhosts = config['fengine']['hosts'].split(',')

    n_ants = len(fhosts)

    n_bls = n_ants * (n_ants+1) / 2 * 4

    print('Loaded instrument info from config file:\n\t%s' % args.config


    if args.log_level:
        import logging
        log_level = args.log_level.strip()
        try:
            logging.basicConfig(level=getattr(logging, log_level))
        except AttributeError:
            raise RuntimeError('No such log level: %s' % log_level)

    if args.spead_log_level:
        import logging
        spead_log_level = args.spead_log_level.strip()
        try:
            logging.basicConfig(level=getattr(logging, spead_log_level))
        except AttributeError:
            raise RuntimeError('No such log level: %s' % spead_log_level)


print('Initialising SPEAD transports for data:'
print('\tData reception on port', data_port
if filename is not None:
    print('\tStoring to file %s' % filename
else:
    print('\tNot saving to disk.'

quit_event = threading.Event()
crx = CorrRx(quit_event=quit_event,
             data_port=data_port,
             log_level=eval('logging.%s' % log_level),
             spead_log_level=eval('logging.%s' % spead_log_level),)
try:
    crx.daemon = True
    crx.start()
    while crx.isAlive():
        time.sleep(0.1)
    print('RX process ended.'
    crx.join()
except KeyboardInterrupt:
    import sys
    quit_event.set()
    print('Stopping, waiting for thread to exit...',
    sys.stdout.flush()
    while quit_event.is_set():
        time.sleep(0.1)
    print('all done.'

# end
