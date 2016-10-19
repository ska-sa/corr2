import time
import logging
import threading
import copy
import Queue

import spead2
import spead2.recv as s2rx

LOGGER = logging.getLogger(__name__)


class CorrRx(threading.Thread):
    """Run a spead receiver in a thread; provide a Queue.Queue interface

    Places each received valid data dump (i.e. contains xeng_raw values) as a pyspead
    ItemGroup into the `data_queue` attribute. If the Queue is full, the newer dumps will
    be discarded.

    """
    def __init__(self, port=8888, queue_size=3):
        self.logger = LOGGER
        self.quit_event = threading.Event()
        self.data_queue = Queue.Queue(maxsize=queue_size)
        "Queue for received ItemGroups"
        self.running_event = threading.Event()
        self.data_port = port
        """UDP port to listen at for UDP data. Cannot be changed after start()"""
        threading.Thread.__init__(self)

    def stop(self):
        self.quit_event.set()
        if hasattr(self, 'strm'):
            self.strm.stop()
            self.logger.info("SPEAD receiver stopped")

    def start(self, timeout=None):
        threading.Thread.start(self)
        if timeout is not None:
            self.running_event.wait(timeout)

    def run(self, acc_scale=True):
        logger = self.logger
        logger.info('Data reception on port %i.' % self.data_port)

        self.strm = strm = s2rx.Stream(spead2.ThreadPool(), bug_compat=0,
                           max_heaps=8, ring_heaps=8)
        strm.add_udp_reader(port=self.data_port, max_size=9200,
                            buffer_size=51200000)

        self.running_event.set()

        try:
            ig = spead2.ItemGroup()
            idx = -1
            dump_size = 0
            datasets = {}
            datasets_index = {}
            # we need these bits of meta data before being able to assemble and transmit
            # signal display data

            meta_required = ['n_chans', 'bandwidth', 'n_bls', 'n_xengs',
                             'center_freq', 'bls_ordering', 'n_accs']
            meta = {}
            for heap in self.strm:
                idx += 1
                updated = ig.update(heap)
                logger.debug('PROCESSING HEAP idx(%i) cnt(%i) @ %.4f' % (
                    idx, heap.cnt, time.time()))
                # output item values specified

                if 'xeng_raw' not in updated:
                    logger.info('Skipping heap {} since no xeng_raw was not updated'.format(idx))
                    continue

                ig_copy = copy.deepcopy(ig)
                try:
                    self.data_queue.put_nowait(ig_copy)
                except Queue.Full:
                    logger.info('Data Queue full, disposing of heap {}.'.format(idx))
                try:
                    self.data_callback(ig_copy)
                except Exception:
                    logger.exception(
                        'Unhandled exception while calling data_callback()')

                # should we quit?
                if self.quit_event.is_set():
                    logger.info('Got a signal from main(), exiting rx loop...')
                    break

        finally:
            try:
                strm.stop()
                logger.info("SPEAD receiver stopped")
            except Exception:
                logger.exception('Exception trying to stop self.rx')
            self.quit_event.clear()
            self.running_event.clear()

    def data_callback(self, ig):
        """User-settable callback that is called each time a new dump is received

        Default implementation is a NOP, but a user can set any function that takes a
        single item-group as a parameter.
        """

    def get_clean_dump(self, dump_timeout=None, discard=2):
        """Discard any queued dumps, discard one more, then return the next dump"""
        # discard any existing queued dumps -- they may be from another test
        try:
            while True:
                self.data_queue.get_nowait()
        except Queue.Empty:
            pass

        # discard next dump too, in case
        LOGGER.info('Discarding {discard} initial dump(s):'.format(discard=discard))
        for i in range(discard):
            self.data_queue.get(timeout=dump_timeout)
        LOGGER.info('Waiting for a clean dump:')
        return self.data_queue.get(timeout=dump_timeout)
