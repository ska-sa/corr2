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


class CorrRx(threading.Thread):
    def __init__(self, port=7148, log_handler=None,
                 log_level=logging.INFO, spead_log_level=logging.INFO, **kwargs):
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
        self.quit_event = quit_event
        threading.Thread.__init__(self)

    def run(self):
        #print 'starting target with kwargs ',self._kwargs
        self._target(**self._kwargs)

    def rx_cont(self, data_port=7148, acc_scale=True, filename=None, items=None, **kwargs):
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

        h5_file = None
        if filename is not None:
            logger.info('Starting file %s.' % filename)
            h5_file = h5py.File(filename, mode='w')

        ig = spead.ItemGroup()
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
            # output item values specified
            if items is not None:
                for name in ig.keys():
                    if name in items:
                        item = ig.get_item(name)
                        if item.has_changed():
                            #decode flags
                            if name == 'flags_xeng_raw':
                                #application level debug flags
                                corrupt_flag = np.uint32((ig[name] / np.uint64(2**33))) & np.uint32(1);
                                logger.info('(%s) corrupt => %s'%(time.ctime(), 'true' if corrupt_flag == 1 else 'false'))
                                over_range_flag = np.uint32((ig[name] / np.uint64(2**32))) & np.uint32(1);
                                logger.info('(%s) over range => %s'%(time.ctime(), 'true' if over_range_flag == 1 else 'false'))
                                noise_diode_flag = np.uint32((ig[name] / np.uint64(2**31))) & np.uint32(1);
                                logger.info('(%s) noise diode => %s'%(time.ctime(), 'true' if noise_diode_flag == 1 else 'false'))
                                
                                #debug flags not exposed externally
                                
                                #digitiser flags
                                noise_diode0_flag = np.uint32((ig[name] / np.uint64(2**1))) & np.uint32(1);
                                logger.info('(%s) polarisation 0 noise diode => %s'%(time.ctime(), 'true' if noise_diode0_flag == 1 else 'false'))
                                noise_diode1_flag = np.uint32((ig[name] / np.uint64(2**0))) & np.uint32(1);
                                logger.info('(%s) polarisation 1 noise diode => %s'%(time.ctime(), 'true' if noise_diode1_flag == 1 else 'false'))
                                adc_or0_flag = np.uint32((ig[name] / np.uint64(2**3))) & np.uint32(1);
                                logger.info('(%s) polarisation 0 adc over-range => %s'%(time.ctime(), 'true' if adc_or0_flag == 1 else 'false'))
                                adc_or1_flag = np.uint32((ig[name] / np.uint64(2**2))) & np.uint32(1);
                                logger.info('(%s) polarisation 1 adc over-range => %s'%(time.ctime(), 'true' if adc_or1_flag == 1 else 'false'))
                                
                                #f-engine flags
                                f_spead_error_flag = np.uint32((ig[name] / np.uint64(2**8))) & np.uint32(1);
                                logger.info('(%s) f-engine spead reception error => %s'%(time.ctime(), 'true' if f_spead_error_flag == 1 else 'false'))
                                f_fifo_of_flag = np.uint32((ig[name] / np.uint64(2**9))) & np.uint32(1);
                                logger.info('(%s) f-engine reception FIFO overflow => %s'%(time.ctime(), 'true' if f_fifo_of_flag == 1 else 'false'))
                                f_pkt_of_flag = np.uint32((ig[name] / np.uint64(2**10))) & np.uint32(1);
                                logger.info('(%s) f-engine reception packet overflow => %s'%(time.ctime(), 'true' if f_pkt_of_flag == 1 else 'false'))
                                f_discarding_flag = np.uint32((ig[name] / np.uint64(2**11))) & np.uint32(1);
                                logger.info('(%s) f-engine packet discarded => %s'%(time.ctime(), 'true' if f_discarding_flag == 1 else 'false'))
                                f_timed_out_flag = np.uint32((ig[name] / np.uint64(2**12))) & np.uint32(1);
                                logger.info('(%s) f-engine timed out waiting for valid timestamp => %s'%(time.ctime(), 'true' if f_discarding_flag == 1 else 'false'))
                                f_rcv_error_flag = np.uint32((ig[name] / np.uint64(2**13))) & np.uint32(1);
                                logger.info('(%s) f-engine receive error => %s'%(time.ctime(), 'true' if f_rcv_error_flag == 1 else 'false'))
                                f_pfb_or1_flag = np.uint32((ig[name] / np.uint64(2**14))) & np.uint32(1);
                                logger.info('(%s) f-engine PFB 1 over-range => %s'%(time.ctime(), 'true' if f_pfb_or1_flag == 1 else 'false'))
                                f_pfb_or0_flag = np.uint32((ig[name] / np.uint64(2**15))) & np.uint32(1);
                                logger.info('(%s) f-engine PFB 0 over-range => %s'%(time.ctime(), 'true' if f_pfb_or0_flag == 1 else 'false'))
                                f_qdr1_flag = np.uint32((ig[name] / np.uint64(2**16))) & np.uint32(1);
                                logger.info('(%s) f-engine QDR SRAM 1 parity error => %s'%(time.ctime(), 'true' if f_qdr1_flag == 1 else 'false'))
                                f_qdr0_flag = np.uint32((ig[name] / np.uint64(2**17))) & np.uint32(1);
                                logger.info('(%s) f-engine QDR SRAM 0 parity error => %s'%(time.ctime(), 'true' if f_qdr0_flag == 1 else 'false'))
                                
                                #x-engine flags
                                x_spead_error_flag = np.uint32((ig[name] / np.uint64(2**24))) & np.uint32(1);
                                logger.info('(%s) x-engine spead reception error => %s'%(time.ctime(), 'true' if x_spead_error_flag == 1 else 'false'))

                            #convert timestamp
                            elif name == 'timestamp':
                                sd_timestamp = ig['sync_time'] + (ig['timestamp'] / float(ig['scale_factor_timestamp']))
                                logger.info('(%s) timestamp => %s'%(time.ctime(), time.ctime(sd_timestamp)))
                            # generic output of item covnerted to string
                            else:
                                logger.info('(%s) %s => %s'%(time.ctime(), name, str(ig[name]))) 

            if h5_file is not None:
                for name in ig.keys():
                    logger.debug('\tkey name %s' % name)
                    item = ig.get_item(name)
                    if (not item.has_changed()) and (name in datasets.keys()):
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
                        datasets[name] = ig[name]
                        datasets_index[name] = 0
                    
                    # check to see if we have stored this type before
                    if name not in h5_file.keys():
                        shape = ig[name].shape if item.shape == -1 else item.shape
                        dtype = np.dtype(type(ig[name])) if shape == [] else item.dtype
                        if dtype is None:
                            dtype = ig[name].dtype
                        # if we can't get a dtype from the descriptor try and get one from the value
                        if dtype != 'object':
                            logger.info('Creating dataset for %s (%s,%s).' % (str(name), str(shape), str(dtype)))
                            if h5_file is not None:
                                h5_file.create_dataset(name, [1] + ([] if list(shape) == [1] else list(shape)),
                                                maxshape=[None] + ([] if list(shape) == [1] else list(shape)), dtype=dtype)
                        if not item.has_changed():
                            continue
                            # if we built from an empty descriptor
                    else:
                        logger.info('Adding %s to dataset. New size is %i.' % (name, datasets_index[name]+1))
                        if h5_file is not None:
                            h5_file[name].resize(datasets_index[name]+1, axis=0)

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

                    if h5_file is not None:
                        h5_file[name][datasets_index[name]] = ig[name]
                    datasets_index[name] += 1
                    # we have dealt with this item so continue...
                    item.unset_changed()
                idx += 1
            #  /if h5_file is not None

            if len(plot_baselines) > 0:
                if 'xeng_raw' in ig.keys():
                    if ig['xeng_raw'] is not None:
                        # print np.shape(ig['xeng_raw'])
                        baseline_data = []
                        for baseline in range(0, 40):
                            # print 'baseline %i:' % baseline, ig['xeng_raw'][:, baseline]
                            FREQ_TO_PLOT = 0
                            print 'f_%i bls_%i:' % (FREQ_TO_PLOT, baseline), ig['xeng_raw'][FREQ_TO_PLOT, baseline]
                            # if baseline in [39, 9, 21, 33]:
                            if baseline in plot_baselines:
                                bdata = ig['xeng_raw'][:, baseline]
                                powerdata = []
                                for complex_tuple in bdata:
                                    pwr = np.sqrt(complex_tuple[0]**2 + complex_tuple[1]**2)
                                    powerdata.append(pwr)
                                baseline_data.append((baseline, powerdata[plot_startchan:plot_endchan]))
                                # break
                        if not got_data_event.is_set():
                            plotqueue.put(baseline_data)
                            got_data_event.set()
            # /if plotbaseline is not None:

#            if len(items) > 0
                

            # should we quit?
            if self.quit_event.is_set():
                logger.info('Got a signal from main(), exiting rx loop...')
                break

#        for (name,idx) in datasets_index.iteritems():
#            if idx == 1:
#                self.logger.info("Repacking dataset %s as an attribute as it is singular."%name)
#                h5_file['/'].attrs[name] = h5_file[name].value[0]
#                h5_file.__delitem__(name)
        if h5_file is not None:
            logger.info("Got a SPEAD end-of-stream marker. Closing File.")
            h5_file.flush()
            h5_file.close()
        rx.stop()
        logger.info("Files and sockets closed.")
        self.quit_event.clear()

# some defaults
filename = None
plotbaseline = None
items = None

if __name__ == '__main__':
    import argparse

    from corr2 import utils

    parser = argparse.ArgumentParser(description='Receive data from a correlator.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config', dest='config', action='store', default='',
                        help='corr2 config file')
    parser.add_argument('--file', dest='writefile', action='store_true', default=False,
                        help='Write an H5 file.')
    parser.add_argument('--filename', dest='filename', action='store', default='',
                        help='Use a specific filename, otherwise use UNIX time. Implies --file.')
    parser.add_argument('--plot_baselines', dest='plotbaselines', action='store', default='', type=str,
                        help='Plot one or more baselines, comma-seperated list of integers.')
    parser.add_argument('--plot_channels', dest='plotchannels', action='store', default='-1,-1', type=str,
                        help='a start,end tuple, -1 means 0,n_chans respectively')
    parser.add_argument('--item', dest='items', action='append', default=[],   
                        help='spead item to output value to log as we receive it')
    parser.add_argument('--ion', dest='ion', action='store_true', default=False,
                        help='Interactive mode plotting.')
    parser.add_argument('--log', dest='log', action='store_true', default=False,
                        help='Logarithmic y axis.')
    parser.add_argument('--no_auto', dest='noauto', action='store_true', default=False,
                        help='Do not scale the data by the number of accumulations.')
    parser.add_argument('--loglevel', dest='log_level', action='store', default='INFO',
                        help='log level to use, default INFO, options INFO, DEBUG, ERROR')
    parser.add_argument('--speadloglevel', dest='spead_log_level', action='store', default='INFO',
                        help='log level to use in spead receiver, default INFO, options INFO, DEBUG, ERROR')
    args = parser.parse_args()

    if args.items is not None:
        items = args.items
        print '\tTracking:'
        for item in items:
            print '\t  * %s' %item
    else:
        print '\tNot tracking any items'

    if args.log_level != '':
        import logging
        log_level = args.log_level.strip()
        try:
            logging.basicConfig(level=eval('logging.%s' % log_level))
        except AttributeError:
            raise RuntimeError('No such log level: %s' % log_level)
    
    if args.spead_log_level != '':
        import logging
        spead_log_level = args.spead_log_level.strip()
        try:
            logging.basicConfig(level=eval('logging.%s' % spead_log_level))
        except AttributeError:
            raise RuntimeError('No such log level: %s' % spead_log_level)

    if args.noauto:
        acc_scale = False
    else:
        acc_scale = True

    if 'CORR2INI' in os.environ.keys() and args.config == '':
        args.config = os.environ['CORR2INI']

    # load the rx port and sd info from the config file
    config = utils.parse_ini_file(args.config)
    data_port = int(config['xengine']['output_destination_port'])
    n_chans = int(config['fengine']['n_chans'])

    if args.writefile:
        filename = str(time.time()) + '.corr2.h5'

    if args.filename != '':
        filename = args.filename + '.corr2.h5'

    plot_baselines = []
    if args.plotbaselines != '':
        for bls in args.plotbaselines.split(','):
            plot_baselines.append(int(bls.strip()))
    if len(plot_baselines) == 1:
        if plot_baselines[0] == -1:
            plot_baselines = range(0, 40)

    temp = args.plotchannels.split(',')
    plot_startchan = int(temp[0].strip())
    plot_endchan = int(temp[1].strip())
    if plot_startchan == -1:
        plot_startchan = 0
    if plot_endchan == -1:
        plot_endchan = n_chans

print 'Initialising SPEAD transports for data:'
print '\tData reception on port', data_port
if filename is not None:
    print '\tStoring to file %s' % filename
else:
    print '\tNot saving to disk.'
if len(plot_baselines) > 0:
    import matplotlib.pyplot as pyplot
    import Queue
    print '\tPlotting baselines:', plot_baselines
    plotqueue = Queue.Queue()
    got_data_event = threading.Event()


    if args.ion:
        pyplot.ion()

    def plot():
        if got_data_event.is_set():
            try:
                powerdata = plotqueue.get_nowait()
                pyplot.cla()
                ymax = -1
                ymin = 2**32
                for pltctr, plot in enumerate(powerdata):
                    baseline = plot[0]
                    plotdata = plot[1]
                    if args.log:
                        pyplot.semilogy(plotdata, label='%i' % baseline)
                    else:
                        pyplot.plot(plotdata, label='%i' % baseline)
                    ymax = max(ymax, max(plotdata))
                    ymin = min(ymin, min(plotdata))
                pyplot.ylim([ymin*0.99, ymax*1.01])
                pyplot.legend(loc='upper left')
                pyplot.draw()
                pyplot.show()
            except Queue.Empty:
                pass
            got_data_event.clear()
else:
    plotqueue = None

quit_event = threading.Event()
crx = CorrRx(quit_event=quit_event,
             data_port=data_port,
             acc_scale=acc_scale,
             log_level=eval('logging.%s' % log_level),
             spead_log_level=eval('logging.%s' % spead_log_level),
             filename=filename,
             plotbaseline=plotbaseline,
             items=args.items,
             plotqueue=plotqueue, )
try:
    crx.daemon = True
    crx.start()
    while crx.isAlive():
        time.sleep(0.1)
        if plotqueue is not None:
            plot()
    print 'RX process ended.'
    crx.join()
except KeyboardInterrupt:
    import sys
    quit_event.set()
    print 'Stopping, waiting for thread to exit...',
    sys.stdout.flush()
    while quit_event.is_set():
        time.sleep(0.1)
    print 'all done.'

# end
