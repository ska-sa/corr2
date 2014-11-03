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

import numpy as np
import spead64_48 as spead
import time
import h5py
import threading
import os
import logging
import struct
import socket
import matplotlib.pyplot as pyplot

class CorrRx(threading.Thread):
    def __init__(self, port=7148, log_handler=None, log_level=logging.INFO, spead_log_level=logging.DEBUG, **kwargs):
        # if log_handler == None:
        #     log_handler = log_handlers.DebugLogHandler(100)
        # self.log_handler = log_handler
        # self.logger = logging.getLogger('rx')
        # self.logger.addHandler(self.log_handler)
        # self.logger.setLevel(log_level)
        self.logger = logging.getLogger(__name__)
        spead.logging.getLogger().setLevel(spead_log_level)
        self._target = self.rx_cont
        self._kwargs = kwargs
        threading.Thread.__init__(self)

    def run(self):
        #print 'starting target with kwargs ',self._kwargs
        self._target(**self._kwargs)

    def rx_cont(self, data_port=7148, acc_scale=True, filename=None, **kwargs):
        logger = self.logger
        logger.info('Data reception on port %i.' % data_port)
        rx = spead.TransportUDPrx(data_port, pkt_count=1024, buffer_size=51200000)

        # group = '239.2.0.100'
        # addrinfo = socket.getaddrinfo(group, None)[0]
        # group_bin = socket.inet_pton(addrinfo[0], addrinfo[4][0])
        # mreq = group_bin + struct.pack('=I', socket.INADDR_ANY)
        #
        # s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        #
        #
        #
        # print "Subscribing to %s." % group

        ig = spead.ItemGroup()
        if filename is None:
            filename = str(int(time.time())) + '.synth.h5'
        logger.info('Starting file %s.' % filename)
        h5_f = h5py.File(filename, mode='w')
        idx = 0
        dump_size = 0
        datasets = {}
        datasets_index = {}
        # we need these bits of meta data before being able to assemble and transmit signal display data
        meta_required = ['n_chans', 'bandwidth', 'n_bls', 'n_xengs',
                         'center_freq', 'bls_ordering', 'n_accs']
        meta = {}
        for heap in spead.iterheaps(rx):
            ig.update(heap)
            logger.debug('PROCESSING HEAP idx(%i) cnt(%i) @ %.4f' % (idx, heap.heap_cnt, time.time()))
            for name in ig.keys():
                logger.debug('\tkey name %s' % name)
                item = ig.get_item(name)
                if (not item._changed) and (name in datasets.keys()):
                    # the item is not marked as changed, and we have a record for it, skip ahead
                    continue
                if name in meta_required:
                    meta[name] = ig[name]
                    meta_required.pop(meta_required.index(name))
                    if len(meta_required) == 0:
                        logger.info('Got all required metadata. Expecting data frame shape of %i %i %i' %
                                    (meta['n_chans'], meta['n_bls'], 2))
                        meta_required = ['n_chans', 'bandwidth', 'n_bls', 'n_xengs',
                                         'center_freq', 'bls_ordering', 'n_accs']

                # check to see if we have encountered this type before
                if name not in datasets.keys():
                    shape = ig[name].shape if item.shape == -1 else item.shape
                    dtype = np.dtype(type(ig[name])) if shape == [] else item.dtype
                    if dtype is None:
                        dtype = ig[name].dtype
                    # if we can't get a dtype from the descriptor try and get one from the value
                    logger.info('Creating dataset for %s (%s,%s).' % (str(name), str(shape), str(dtype)))
                    h5_f.create_dataset(name, [1] + ([] if list(shape) == [1] else list(shape)),
                                     maxshape=[None] + ([] if list(shape) == [1] else list(shape)), dtype=dtype)
                    dump_size += np.multiply.reduce(shape) * dtype.itemsize
                    datasets[name] = h5_f[name]
                    datasets_index[name] = 0
                    if not item._changed:
                        continue
                        # if we built from an empty descriptor
                else:
                    logger.info('Adding %s to dataset. New size is %i.' % (name, datasets_index[name]+1))
                    h5_f[name].resize(datasets_index[name]+1, axis=0)

                if name.startswith('xeng_raw'):
                    sd_timestamp = ig['sync_time'] + (ig['timestamp'] / float(ig['scale_factor_timestamp']))
                    logger.info("SD Timestamp: %f (%s)." % (sd_timestamp, time.ctime(sd_timestamp)))

                    scale_factor = float(meta['n_accs'] if ('n_accs' in meta.keys() and acc_scale) else 1)
                    scaled_data = (ig[name] / scale_factor).astype(np.float32)

                    logger.info("Sending signal display frame with timestamp %i (%s). %s. Max: %i, Mean: %i" % (
                        sd_timestamp,
                        time.ctime(sd_timestamp),
                        "Unscaled" if not acc_scale else "Scaled by %i" % scale_factor,
                        np.max(scaled_data),
                        np.mean(scaled_data)))

                h5_f[name][datasets_index[name]] = ig[name]
                datasets_index[name] += 1
                # we have dealt with this item so continue...
                item._changed = False
            if 'xeng_raw' in ig.keys():
                if ig['xeng_raw'] is not None:
                    print np.shape(ig['xeng_raw'])
                    for baseline in range(0, 40):
                        # print 'baseline %i:' % baseline, ig['xeng_raw'][:, baseline]
                        if baseline == 0:  # 0, 1, 2, 20
                            bdata = ig['xeng_raw'][:, baseline]
                            powerdata = []
                            for complex_tuple in bdata:
                                pwr = np.sqrt(complex_tuple[0]**2 + complex_tuple[1]**2)
                                powerdata.append(pwr)
                            pyplot.interactive(True)
                            pyplot.cla()
                            pyplot.semilogy(powerdata)
                            pyplot.draw()
            idx += 1

#        for (name,idx) in datasets_index.iteritems():
#            if idx == 1:
#                self.logger.info("Repacking dataset %s as an attribute as it is singular."%name)
#                h5_f['/'].attrs[name] = h5_f[name].value[0]
#                h5_f.__delitem__(name)
        logger.info("Got a SPEAD end-of-stream marker. Closing File.")
        h5_f.flush()
        h5_f.close()
        rx.stop()
        logger.info("Files and sockets closed.")

if __name__ == '__main__':
    import argparse

    from corr2 import utils

    parser = argparse.ArgumentParser(description='Receive data from a corremelator.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config', dest='config', action='store', default='',
                        help='corr2 config file')
    parser.add_argument('--no_auto', dest='noauto', action='store_true', default=False,
                        help='Do not scale the data by the number of accumulations.')
    parser.add_argument('--loglevel', dest='log_level', action='store', default='INFO',
                        help='log level to use, default None, options INFO, DEBUG, ERROR')
    args = parser.parse_args()

    if args.log_level != '':
        import logging
        log_level = args.log_level.strip()
        try:
            logging.basicConfig(level=eval('logging.%s' % log_level))
        except AttributeError:
            raise RuntimeError('No such log level: %s' % log_level)

    if args.noauto:
        acc_scale = False
    else:
        acc_scale = True

    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']

    if args.config != '':
        # load the rx port and sd info from the config file
        config = utils.parse_ini_file(args.config)
        data_port = int(config['xengine']['output_destination_port'])
    else:
        data_port = 7148        # config['rx_udp_port']

filename = str(time.time()) + '.corr.h5'

print 'Initalising SPEAD transports for data:'
print '\tData reception on port', data_port
print '\tStoring to file %s' % filename

crx = CorrRx(data_port=data_port,
             acc_scale=acc_scale,
             filename=filename,
             log_level=eval('logging.%s' % log_level),)
try:
    crx.daemon = True
    crx.start()
    while crx.isAlive():
        time.sleep(0.1)
    print 'RX process ended.'
    crx.join()
except KeyboardInterrupt:
    print 'Stopping...'

# end