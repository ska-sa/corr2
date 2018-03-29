#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
"""

import spead2
import spead2.recv as s2rx
import numpy as np
import time
import threading
import logging


class CorrRx(threading.Thread):
    def __init__(self,
                 log_level=logging.INFO,
                 spead_log_level=logging.INFO,
                 **kwargs):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        spead2._logger.setLevel(spead_log_level)
        self._target = self.rx_cont
        self._kwargs = kwargs
        self.quit_event = quit_event
        threading.Thread.__init__(self)

    def run(self):
        print('Starting target with kwargs ', self._kwargs
        self._target(**self._kwargs)

    def rx_cont(self, data_port, **kwargs):

        logger = self.logger
        logger.info('Data reception on port %i.' % data_port)

        strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0,
                           max_heaps=8, ring_heaps=8)
        strm.add_udp_reader(port=data_port, max_size=9200,
                            buffer_size=51200000)

        ig = spead2.ItemGroup()

        # manually add the metadata here
        print('Manually adding metadata...',
        ig.add_item(
            name='test_raw', id=0x2222,
            description='This is the ramp of test data, 64-bit integers by'
                        '32768.',
            dtype=np.dtype('>i8'),
            shape=[32768])

        ig.add_item(
            name='test_int', id=0x1234,
            description='This is just a test item included in the heap.'
                        'Should be 777777.',
            shape=[], format=[('u', 48)])
        print('done.'

        idx = 0
        last_cnt = -1
        for heap in strm:
            ig.update(heap)
            cnt_diff = heap.cnt - last_cnt
            last_cnt = heap.cnt
            logger.debug('PROCESSING HEAP idx(%i) cnt(%i) cnt_diff(%i) '
                         '@ %.4f' % (idx, heap.cnt, cnt_diff, time.time()))

            if 'test_raw' not in ig.keys():
                logger.error('test_raw was not in the item group?')
                self.quit_event.set()
                return
            if ig['test_raw'] is None:
                logger.error('test_raw item was None?')
                return
            test_raw = ig['test_raw'].value
            if test_raw is None:
                logger.error('test_raw Item value was None?')
                return

            # just check the ramp
            for ctr in range(32768):
                if test_raw[ctr] != ctr:
                    logger.error('test_raw[{}] != {}'.format(ctr, ctr))
                    self.quit_event.set()
                    break
            logger.info('Heap {} test ramp okay'.format(heap.cnt))
            if ig['test_int'].value != 777777:
                logger.error('test_int was wrong value!')
                self.quit_event.set()

            # should we quit?
            if self.quit_event.is_set():
                logger.info('Got a signal from main(), exiting rx loop...')
                break

            idx += 1

        strm.stop()
        logger.info("Files and sockets closed.")
        self.quit_event.clear()

if __name__ == '__main__':
    import argparse

    psr = argparse.ArgumentParser(
        description='Receive text data.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    psr.add_argument('--loglevel', dest='log_level', action='store',
                     default='INFO',
                     help='log level to use, default INFO, options INFO, '
                          'DEBUG, ERROR')
    psr.add_argument('--speadloglevel', dest='spead_log_level', action='store',
                     default='INFO',
                     help='log level to use in spead receiver, default INFO, '
                          'options INFO, DEBUG, ERROR')
    args = psr.parse_args()

    if args.log_level:
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
print('\tData reception on port', 9876

quit_event = threading.Event()
crx = CorrRx(quit_event=quit_event,
             data_port=9876,
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
