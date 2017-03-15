import time
import logging
import threading
import copy
import Queue

import spead2
import spead2.recv as s2rx
import numpy as np

LOGGER = logging.getLogger(__name__)


class CorrRx(threading.Thread):
    """Run a spead receiver in a thread; provide a Queue.Queue interface

    Places each received valid data dump (i.e. contains xeng_raw values) as a pyspead
    ItemGroup into the `data_queue` attribute. If the Queue is full, the newer dumps will
    be discarded.

    Paramaters:
        port: Spead2 stream port (default = 8888)
        queue_size: Size of spead2 heap queue. Note that spead2 heaps can be very large 
                    (100's of megabytes) and available RAM should be taken into account 
                    when assigning queue size. (default = 3)
        ring_heaps: Number of heaps to keep in the spead2 ring buffer. (default = 4)
        active_frames: Number of frames that may be in flight at one time. (default = 3)
        buffer_size: Spead2 receiver udp_reader buffer size. Default is None which will
                     use the spead2 default.

    """
    def __init__(self, port=8888, queue_size=3, ring_heaps=4, active_frames=3, buffer_size=None):
        self.ring_heaps = ring_heaps
        self.active_frames = active_frames
        self.buffer_size = buffer_size
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
            return self.running_event.wait(timeout)

    def run(self):
        logger = self.logger
        logger.info('Data reception on port %i.' % self.data_port)

        try:
            # We can't tell how big to make the memory pool or how many heaps
            # we will be receiving in parallel until we have the metadata, but
            # we need this to set up the stream. To handle this, we'll make a
            # temporary stream for reading the metadata, then replace it once
            # we have the metadata
            self.strm = s2rx.Stream(spead2.ThreadPool(), 
                                    max_heaps=2, ring_heaps=8)
            self.strm.add_udp_reader(port=self.data_port)
            ig = spead2.ItemGroup()
            meta_required = set(['n_chans', 'bandwidth', 'n_bls', 'n_xengs',
                                 'center_freq', 'bls_ordering', 'n_accs'])
            meta = set()
            meta_found = False
            try:
                for heap in self.strm:
                    updated = ig.update(heap)
                    meta = set(ig.keys())
                    if meta_required.issubset(meta):
                        meta_found = True
                        break
                    if 'timestamp' in updated:
                        logger.warning('Dropping heap with timestamp %d because metadata not ready',
                                       updated['timestamp'].value)
            except spead2.Stopped:
                raise
            self.strm.stop()

            if meta_found:
                # Code from SP ingest process. This should be updated when multiple capture machines
                # are required to process data
                heap_data_size = np.product(ig['xeng_raw'].shape) * ig['xeng_raw'].dtype.itemsize
                heap_channels = ig['xeng_raw'].shape[0]
                logger.info('Creating spead2 stream with max_heaps=%i, ring_heaps=%i' % (
                    self.active_frames, self.ring_heaps))
                self.strm = s2rx.Stream(spead2.ThreadPool(),
                    max_heaps=self.active_frames, ring_heaps=self.ring_heaps)
                memory_pool_heaps = (self.active_frames + 2) + self.ring_heaps 
                logger.info('Updating spead2 stream memory pool with heap_data_size=%i '
                             'and memory_pool_heaps=%i' % (heap_data_size, memory_pool_heaps))
                memory_pool = spead2.MemoryPool(heap_data_size, heap_data_size + 512,
                                                memory_pool_heaps, memory_pool_heaps)
                self.strm.set_memory_allocator(memory_pool)
                if self.buffer_size:
                    self.strm.add_udp_reader(port=self.data_port, buffer_size=self.buffer_size)
                else:
                    self.strm.add_udp_reader(port=self.data_port)

                self.running_event.set()

                idx = -1
                for heap in self.strm:
                    # should we quit?
                    if self.quit_event.is_set():
                        logger.debug('Got a signal from main(), exiting rx loop...')
                        break

                    idx += 1
                    updated = ig.update(heap)
                    logger.debug('PROCESSING HEAP idx(%i) cnt(%i) @ %.4f' % (
                        idx, heap.cnt, time.time()))
                    # output item values specified

                    if 'xeng_raw' not in updated:
                        logger.debug('Skipping non data heap {}.'.format(idx))
                        continue

                    ig_copy = copy.deepcopy(ig)
                    try:
                        self.data_queue.put_nowait(ig_copy)
                    except Queue.Full:
                        logger.debug('Data Queue full, disposing of heap {}.'.format(idx))
                    try:
                        self.data_callback(ig_copy)
                    except Exception:
                        logger.exception(
                            'Unhandled exception while calling data_callback()')
        finally:
            try:
                self.strm.stop()
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
                self.logger.debug('Discarding dump from data queue.')
        except Queue.Empty:
            pass

        # discard next dump too, in case
        self.logger.debug('Discarding {discard} initial dump(s):'.format(discard=discard))
        for i in range(discard):
            try:
                dump = self.data_queue.get(timeout=dump_timeout)
            except Exception as ex:
                template = "An exception of type {0} occured. Arguments: {1!r}"
                message = template.format(type(ex), ex.args)
                self.logger.error(message)
                raise ex
        self.logger.debug('Waiting for a clean dump:')
        try:
            dump = self.data_queue.get(timeout=dump_timeout)
        except Exception as ex:
            template = "An exception of type {0} occured. Arguments: {1!r}"
            message = template.format(type(ex), ex.args)
            self.logger.error(message)
            raise ex
        else:
            return dump

