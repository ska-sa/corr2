#!/usr/bin/env python

import logging
import sys
import argparse
import katcp
from katcp.kattypes import request, return_reply, Float, Int, Str, Bool
import signal
from tornado import gen
from tornado.ioloop import IOLoop
import Queue
import time
from concurrent import futures

from corr2 import fxcorrelator, sensors


class KatcpStreamHandler(logging.StreamHandler):

    def format(self, record):
        """
        Convert the record message contents to a katcp #log format
        :param record: a logging.LogRecord
        :return:
        """
        level = 'WARN' if record.levelname == 'WARNING' else record.levelname
        level = level.lower()
        msg = record.msg.replace(' ', '\_')
        msg = msg.replace('\t', '\_' * 4)
        return '#log ' + level + ' ' + '%.6f' % time.time() + ' ' + \
               record.filename + ' ' + msg


class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to
    a logger instance.
    From: http://www.electricmonk.nl/log/2011/08/14/redirect-stdout-and-stderr-to-a-logger-in-python/
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())


class Corr2Server(katcp.DeviceServer):

    # Interface version information.
    VERSION_INFO = ('corr2 instrument servlet', 0, 1)

    # Device server build / instance information.
    BUILD_INFO = ('corr2', 0, 1, 'alpha')

    def __init__(self, *args, **kwargs):
        use_tornado = kwargs.pop('tornado')
        super(Corr2Server, self).__init__(*args, **kwargs)
        if use_tornado:
            self.set_concurrency_options(thread_safe=False,
                                         handler_thread=False)
        self.instrument = None
        self.metadata_cadence = 5
        self.executor = futures.ThreadPoolExecutor(max_workers=1)

    @request()
    @return_reply()
    def request_ping(self, sock):
        """
        Just ping the server
        :param sock:
        :return: 'ok'
        """
        return 'ok',

    @staticmethod
    def rv_to_liststr(rv):
        rv = str(rv)
        rv = rv.replace('(', '').replace(')', '')
        rv = rv.replace('[', '').replace(']', '')
        rv = rv.replace(',', '')
        return rv.split(' ')

    @request(Str(), Int(default=1000))
    @return_reply()
    def request_create(self, sock, config_file, log_len):
        """
        Create the instrument using the detail in config_file
        :param sock:
        :param config_file: The instrument config file to use
        :param log_len:
        :return:
        """
        try:
            self.instrument = fxcorrelator.FxCorrelator(
                'corr_%s' % str(time.time()), config_source=config_file)
            return 'ok',
        except Exception as e:
            return 'fail', 'Failed to create instrument: %s' % e.message

    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        pass

    @request(Bool(default=True), Bool(default=True), Bool(default=True),
             Bool(default=True))
    @return_reply()
    def request_initialise(self, sock, program, qdr_cal, require_epoch,
                           monitor_vacc):
        """
        Initialise self.instrument
        :param sock:
        :param program: program the FPGA boards if True
        :param qdr_cal: perform QDR cal if True
        :param require_epoch: the synch epoch MUST be set before init if True
        :param monitor_vacc: start the VACC monitoring ioloop
        :return:
        """
        try:
            self.instrument.initialise(program=program,
                                       qdr_cal=qdr_cal,
                                       require_epoch=require_epoch)
            sensor_manager = sensors.SensorManager(self, self.instrument)
            self.instrument.sensor_manager = sensor_manager
            sensor_manager.sensors_clear()
            sensors.setup_mainloop_sensors(sensor_manager)
            IOLoop.current().add_callback(self.periodic_send_metadata)
            if monitor_vacc:
                self.instrument.xops.vacc_check_timer_start()
            return 'ok',
        except Exception as e:
            return 'fail', 'Failed to initialise %s: %s' % (
                self.instrument.descriptor, e.message)

    @request(Str(multiple=True))
    @return_reply()
    def request_testfail(self, sock, *multiargs):
        """
        Just a command that fails. For testing.
        :param sock:
        :return: 'fail' and a test fail message
        """
        print multiargs
        return 'fail', 'A test failure, like it should'

    @request(Float(default=-1.0))
    @return_reply(Float())
    def request_digitiser_synch_epoch(self, sock, synch_time):
        """
        Set/Get the digitiser synch time, UNIX time.
        :param sock:
        :param synch_time: unix time float
        :return: the currently set synch time
        """
        # if not self.instrument.initialised():
        #     logging.warn('request %s before initialised... refusing.' %
        #                  'request_digitiser_synch_epoch')
        #     return 'fail', 'request %s before initialised... refusing.' % \
        #            'request_digitiser_synch_epoch'
        if synch_time > -1.0:
            try:
                self.instrument.set_synch_time(synch_time)
            except Exception as e:
                return 'fail', 'Failed to set digitiser synch epoch: ' \
                               '%s' % e.message
        return 'ok', self.instrument.get_synch_time()

    def _check_product_name(self, product_name):
        """
        Does a given product name exist on this instrument?
        :param product_name: an instrument data product name
        :return:
        """
        return product_name in self.instrument.data_products

    @request(Str(), Str())
    @return_reply()
    def request_meta_destination(self, sock, product_name, ipportstr):
        """
        Set/Get the capture AND meta destination for this instrument
        :param sock:
        :param product_name: an instrument data product name
        :param ipportstr: ip and port, in the form 1.2.3.4:7890
        :return:
        """
        return 'fail', 'This has been deprecated. Use capture-destination to ' \
                       'set both capture and meta destinations at the same time'

    @request(Str(), Str(default=''))
    @return_reply(Str(multiple=True))
    def request_capture_destination(self, sock, product_name, ipportstr):
        """
        Set/Get the capture AND meta destination for this instrument
        :param sock:
        :param product_name: an instrument data product name
        :param ipportstr: ip and port, in the form 1.2.3.4:7890
        :return:
        """
        if ipportstr != '':
            try:
                temp = ipportstr.split(':')
                txipstr = temp[0]
                txport = int(temp[1])
                self.instrument.product_set_destination(
                    product_name, txipstr, txport)
            except Exception as e:
                return 'fail', 'Failed to set capture AND meta destination ' \
                               'for %s: %s' % (product_name, e.message)
        else:
            dprod = self.instrument.data_products[product_name]
            ipportstr = '%s:%d' % (dprod.destination.ip, dprod.destination.port)
        return 'ok', product_name, ipportstr

    @request(Str(default=''))
    @return_reply()
    def request_capture_list(self, sock, product_name):
        """
        List available products and their destination IP:port
        :param sock:
        :param product_name: an instrument data product name
        :return:
        """
        product_names = []
        if product_name != '':
            product_names.append(product_name)
        else:
            product_names.extend(self.instrument.data_products.keys())
        for prod in product_names:
            if not self._check_product_name(prod):
                return 'fail', 'Failed: product %s not in instrument data ' \
                               'products: %s' % (prod,
                                                 self.instrument.data_products)
            dprod = self.instrument.data_products[prod]
            sock.inform(prod, '%s:%d' % (
                dprod.destination.ip,
                dprod.destination.port))
        return 'ok',

    @request(Str(default=''))
    @return_reply(Str())
    def request_capture_start(self, sock, product_name):
        """
        Start transmission of a data product.
        :param sock:
        :param product_name: an instrument data product name
        :return:
        """
        if not self._check_product_name(product_name):
            return 'fail', 'Failed: product %s not in instrument data ' \
                           'products: %s' % (product_name,
                                             self.instrument.data_products)
        self.instrument.product_issue_metadata(product_name)
        self.instrument.product_tx_enable(product_name)
        return 'ok', product_name

    @request(Str(default=''))
    @return_reply(Str())
    def request_capture_stop(self, sock, product_name):
        """
        Stop transmission of a data product.
        :param sock:
        :param product_name: an instrument data product name
        :return:
        """
        if not self._check_product_name(product_name):
            return 'fail', 'Failed: product %s not in instrument data ' \
                           'products: %s' % (product_name,
                                             self.instrument.data_products)
        self.instrument.product_tx_disable(product_name)
        return 'ok', product_name

    @request(Str(default=''))
    @return_reply(Str())
    def request_capture_meta(self, sock, product_name):
        """
        Issue metadata for a data product
        :param sock:
        :param product_name: an instrument data product name
        :return:
        """
        if not self._check_product_name(product_name):
            return 'fail', 'Failed: product %s not in instrument data ' \
                           'products: %s' % (product_name,
                                             self.instrument.data_products)
        self.instrument.product_issue_metadata(product_name)
        return 'ok', product_name

    @request(Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_input_labels(self, sock, *newlist):
        """
        Set and get the input labels on the instrument
        :param sock:
        :return:
        """
        if len(newlist) == 1:
            if newlist[0] == '':
                newlist = []
        if len(newlist) > 0:
            try:
                self.instrument.set_labels(newlist)
                return tuple(['ok'] + self.instrument.get_labels())
            except Exception as e:
                return 'fail', 'Failed to set input labels: %s' % e.message
        else:
            return tuple(['ok'] + self.instrument.get_labels())

    @request(Str(), Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_gain(self, sock, source_name, *eq_vals):
        """
        Apply and/or get the gain settings for an input
        :param sock:
        :param source_name: the source on which to act
        :param eq_vals: the equaliser values
        :return:
        """
        if source_name.strip() == '':
            return 'fail', 'No source name given'
        if len(eq_vals) > 0 and eq_vals[0] != '':
            try:
                self.instrument.fops.eq_set(True, source_name, list(eq_vals))
            except Exception as e:
                return 'fail', 'Failed setting eq for source %s: ' \
                               '%s' % (source_name, e.message)
        _src = self.instrument.fops.eq_get(source_name)
        return tuple(['ok'] +
                     Corr2Server.rv_to_liststr(_src[source_name]))

    @request(Float(), Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_delays(self, sock, loadtime, *delay_strings):
        """
        Set delays for the instrument.
        :param sock:
        :param loadtime: the load time, in seconds
        :param sock: the coefficient set, as a list of strings, described in
        ICD.
        :return:
        """
        try:
            actual = self.instrument.fops.delays_process_parallel(
                loadtime, delay_strings)
            return tuple(['ok'] + actual)
        except Exception as e:
            return 'fail', 'Failed setting delays: %s' % e.message

    @request(Float(default=-1.0))
    @return_reply(Float())
    def request_accumulation_length(self, sock, new_acc_time):
        """
        Set & get the accumulation time
        :param sock:
        :param new_acc_time: if this is -1.0, the current acc len will be
        returned, but nothing set
        :return:
        """
        if new_acc_time != -1.0:
            try:
                self.instrument.xops.set_acc_time(new_acc_time)
            except Exception as e:
                return 'fail', 'Failed to set accumulation ' \
                               'length: %s' % e.message
        return 'ok', self.instrument.xops.get_acc_time()

    @request(Str(default=''))
    @return_reply(Str(multiple=True))
    def request_quantiser_snapshot(self, sock, source_name):
        """
        Get a list of values representing the quantised spectrum for
        the given source
        :param sock:
        :param source_name: the source to query
        :return:
        """
        try:
            snapdata = self.instrument.fops.get_quant_snap(source_name)
        except ValueError as e:
            return 'fail', 'Failed reading quant snap data for ' \
                           'source %s: %s' % (source_name, e.message)
        quant_string = ''
        for complex_word in snapdata:
            quant_string += ' %s' % str(complex_word)
        return tuple(['ok'] + Corr2Server.rv_to_liststr(quant_string))

    @request(Str(), Float(default=-1))
    @return_reply(Int())
    def request_adc_snapshot(self, sock, source_name, capture_time):
        """
        Request a snapshot of ADC data for a specific source, at a
        specific time.
        :param sock:
        :param source_name: the source to query
        :param capture_time: the UNIX time from which to capture data
        :return:
        """
        try:
            data = self.instrument.fops.get_adc_snapshot(
                source_name, capture_time)
            snaptime = data[source_name].timestamp
            rstr = str(data[source_name].data)
            sock.inform(source_name, rstr)
            return 'ok', snaptime
        except ValueError as e:
            return 'fail', 'Failed reading ADC voltage data for ' \
                           'source %s: %s' % (source_name, e.message)

    @request()
    @return_reply(Int())
    def request_transient_buffer_trigger(self, sock):
        """
        Get ADC snapshots for all data sources, hopefully triggered at the
        same time.
        :param sock:
        :return:
        """
        try:
            data = self.instrument.fops.get_adc_snapshot()
            for source in data:
                rstr = str(data[source].data)
                sock.inform(source, rstr)
            snaptime = data[data.keys()[0]].timestamp
            return 'ok', snaptime
        except ValueError as e:
            return 'fail', 'Failed to read ADC voltage data from transient' \
                           'buffers: %s' % e.message

    @request(Str(), Str(), Float(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_beam_weights(self, sock, beam_name, input_name, *weight_list):
        """
        Set the weight for an input
        :param sock:
        :param beam_name: required beam product
        :param input_name: required input
        :param weight_list: list of weights to set, one per input
        :return:
        """
        if not self.instrument.found_beamformer:
            return 'fail', 'Cannot run beamformer commands with no beamformer'
        if weight_list[0] != '':
            try:
                self.instrument.bops.set_beam_weights(
                    weight_list[0], beam_name, input_name)
            except Exception as e:
                return 'fail', 'Failed setting beamweights for beam %s, ' \
                               'input %s: %s' % (beam_name, input_name,
                                                 e.message)
        try:
            cur_weights = self.instrument.bops.get_beam_weights(
                beam_name, input_name)
        except Exception as e:
            return 'fail', 'Failed reading beamweights for beam %s, input ' \
                           '%s: %s' % (beam_name, input_name, e.message)
        return tuple(['ok'] + Corr2Server.rv_to_liststr(cur_weights))

    @request(Str(), Float(default=''))
    @return_reply(Str(multiple=True))
    def request_beam_quant_gains(self, sock, beam_name, new_gain):
        """
        Set the quantiser gain for an input
        :param sock:
        :param beam_name: required beam product
        :param new_gain: the new gain to apply - a real float
        :return:
        """
        if not self.instrument.found_beamformer:
            return 'fail', 'Cannot run beamformer commands with no beamformer'
        if new_gain != '':
            try:
                self.instrument.bops.set_beam_quant_gains(new_gain, beam_name)
            except Exception as e:
                return 'fail', 'Failed setting beam gain for beam %s: %s' % (
                    beam_name, e.message)
        try:
            cur_gains = self.instrument.bops.get_beam_quant_gains(beam_name)
        except Exception as e:
            return 'fail', 'Failed reading beam gain for beam %s: %s' % (
                beam_name, e.message)
        return tuple(['ok'] + Corr2Server.rv_to_liststr(cur_gains))

    @request(Str(), Float(), Float())
    @return_reply(Str(), Str(), Str())
    def request_beam_passband(self, sock, beam_name, bandwidth, centerfreq):
        """
        Set the beamformer bandwidth/partitions
        :param sock:
        :param beam_name: required beam product
        :param bandwidth: required spectrum, in hz
        :param centerfreq: required cf of spectrum bandwidth chunk
        :return:
        """
        if not self.instrument.found_beamformer:
            return 'fail', 'Cannot run beamformer commands with no beamformer'
        try:
            (cur_bw, cur_cf) = self.instrument.bops.set_beam_bandwidth(
                beam_name,
                bandwidth,
                centerfreq)
        except Exception as e:
            return 'fail', 'Failed setting beam passband for beam %s: %s' % (
                beam_name, e.message)
        return 'ok', beam_name, str(cur_bw), str(cur_cf)

    @request()
    @return_reply()
    def request_vacc_sync(self, sock):
        """
        Initiate a new vacc sync operation on the instrument.
        :param sock:
        :return:
        """
        try:
            self.instrument.xops.vacc_sync()
        except Exception as e:
            return 'fail', 'Failed syncing vaccs: %s' % e.message
        return 'ok',

    @request(Int(default=-1))
    @return_reply(Int())
    def request_fft_shift(self, sock, new_shift):
        """
        Set a new FFT shift schedule.
        :param sock:
        :param new_shift: an integer representation of the new FFT shift
        :return:
        """
        if new_shift >= 0:
            current_shift_value = self.instrument.fops.set_fft_shift_all(
                new_shift)
        else:
            current_shift_value = self.instrument.fops.get_fft_shift_all()
            current_shift_value = current_shift_value[
                current_shift_value.keys()[0]]
        return 'ok', current_shift_value

    @request()
    @return_reply(Int(min=0))
    def request_get_log(self, sock):
        """
        Fetch and print the instrument log.
        :param sock:
        :return:
        """
        if self.instrument is None:
            return 'fail', '... you have not connected yet!'
        print '\nlog:'
        self.instrument.loghandler.print_messages()
        logstrings = self.instrument.loghandler.get_log_strings()
        for logstring in logstrings:
            sock.inform('log', logstring)
        return 'ok', len(logstrings)

    @request(Str(default=''), Int(default=-1))
    @return_reply(Str())
    def request_set_loglevel_logger(self, logger_name, log_level_int, sock):
        """
        Set the log level of one of the internal loggers.
        :param logger_name: the name of the logger to configure
        :param log_level_int: the integer level to set (eg. INFO=20, DEBUG=10)
        :param sock: not sure...
        """
        if logger_name != '':
            logger = logging.getLogger(logger_name)
        else:
            logger = logging.getLogger()
        logger.setLevel(log_level_int)
        return 'ok', '%s' % str(log_level_int)

    @request()
    @return_reply()
    def request_debug_deprogram_all(self, sock):
        """
        Deprogram all the f and x roaches
        :param sock:
        :return:
        """
        try:
            from casperfpga import utils as fpgautils
            fhosts = self.instrument.fhosts
            xhosts = self.instrument.xhosts
            fpgautils.threaded_fpga_function(fhosts, 10, 'deprogram')
            fpgautils.threaded_fpga_function(xhosts, 10, 'deprogram')
        except Exception as e:
            return 'fail', 'unknown exception: %s' % e.message
        return 'ok',

    @request(Str(), Int(), Int(), Int())
    @return_reply(Str(multiple=True))
    def request_debug_gain_range(self, sock, source_name, value, fstart, fstop):
        """
        Apply and/or get the gain settings for an input
        :param sock:
        :param source_name: the source on which to act
        :param value: the equaliser values
        :param fstart: the channel on which to start applying this gain
        :param fstop: the channel at which to stop
        :return:
        """
        if source_name == '':
            return 'fail', 'no source name given'
        n_chans = self.instrument.n_chans
        eq_vals = [0] * fstart
        eq_vals.extend([value] * (fstop - fstart))
        eq_vals.extend([0] * (n_chans - fstop))
        assert len(eq_vals) == n_chans
        if len(eq_vals) > 0 and eq_vals[0] != '':
            try:
                self.instrument.fops.eq_set(True, source_name, list(eq_vals))
            except Exception as e:
                return 'fail', 'Failed setting eq for input %s: %s' % (
                    source_name, e.message)
        _src = self.instrument.fops.eq_get(source_name)
        return tuple(['ok'] +
                     Corr2Server.rv_to_liststr(_src[source_name]))

    @request(Str(default='', multiple=True))
    @return_reply()
    def request_debug_gain_all(self, sock, *eq_vals):
        """
        Apply and/or get the gain settings for an input
        :param sock:
        :param eq_vals: the equaliser values
        :return:
        """
        if len(eq_vals) > 0 and eq_vals[0] != '':
            try:
                self.instrument.fops.eq_set(True, None, list(eq_vals))
            except Exception as e:
                return 'fail', 'Failed setting all eqs: %s' % e.message
        else:
            return 'fail', 'did not give new eq values?'
        return 'ok',

    @request(Str(default='INFO'), Str('CLOWNS EVERYWHERE!!!'))
    @return_reply()
    def request_debug_log(self, sock, level, msg):
        """
        Log a test message - to test the formatter and handler
        :param sock:
        :param level:
        :param msg:
        :return:
        """
        self.instrument.logger.log(eval('logging.%s' % level), msg)
        return 'ok',

    @request()
    @return_reply()
    def request_debug_stdouterr(self, sock):
        """
        Blargh.
        :param sock:
        :return:
        """
        # from __future__ import print_function
        import time
        ts = str(time.time())
        print 'This should go to standard out. ' + ts
        sys.stderr.write('This should go to standard error. %s\n' % ts)
        return 'ok',

    @gen.coroutine
    def periodic_send_metadata(self):
        """
        Periodically send all instrument metadata.

        :return:
        """
        _logger = self.instrument.logger
        try:
            yield self.executor.submit(self.instrument.product_issue_metadata)
        except Exception as e:
            _logger.exception('Error sending metadata - {}'.format(e.message))
        _logger.debug('self.periodic_send_metadata ran')
        IOLoop.current().call_later(self.metadata_cadence,
                                    self.periodic_send_metadata)

# @gen.coroutine
# def send_test_informs(server):
#     supdate_inform = katcp.Message.inform('test-mass-inform',
#                                           'arg0', 1.111, 'arg2',
#                                           time.time())
#     server.mass_inform(supdate_inform)
#     tornado.ioloop.IOLoop.current().call_later(5, send_test_informs, server)


@gen.coroutine
def on_shutdown(ioloop, server):
    """
    Shut down the ioloop sanely.
    :param ioloop: the current tornado.ioloop.IOLoop
    :param server: a katcp.DeviceServer instance
    :return:
    """
    print 'corr2 server shutting down'
    yield server.stop()
    ioloop.stop()


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Start a corr2 instrument server.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-p', '--port', dest='port', action='store', default=1235, type=int,
        help='bind to this port to receive KATCP messages')
    parser.add_argument(
        '--log_level', dest='loglevel', action='store', default='INFO',
        help='log level to set')
    parser.add_argument(
        '--log_format_katcp', dest='lfm', action='store_true', default=False,
        help='format log messsages for katcp')
    parser.add_argument(
        '--no_tornado', dest='no_tornado', action='store_true', default=False,
        help='do NOT use the tornado version of the Katcp server')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.loglevel)
    except:
        raise RuntimeError('Received nonsensical log level %s' % args.loglevel)

    # set up the logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if args.lfm or (not sys.stdout.isatty()):
        console_handler = KatcpStreamHandler(stream=sys.stdout)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)
    else:
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                      '%(filename)s:%(lineno)s - '
                                      '%(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    server = Corr2Server('127.0.0.1', args.port, tornado=(not args.no_tornado))
    print 'Server listening on port %d,' % args.port,

    if not args.no_tornado:
        ioloop = IOLoop.current()
        signal.signal(
            signal.SIGINT,
            lambda sig, frame: ioloop.add_callback_from_signal(
                on_shutdown, ioloop, server))
        server.set_ioloop(ioloop)
        ioloop.add_callback(server.start)
        # ioloop.add_callback(send_test_informs, server)
        print 'started with ioloop. Running somewhere in the ether... ' \
              'exit however you see fit.'
        ioloop.start()
    else:
        queue = Queue.Queue()
        server.set_restart_queue(queue)
        server.start()
        print 'started with no ioloop. Running somewhere in the ether... ' \
              'exit however you see fit.'
        try:
            while True:
                try:
                    device = queue.get(timeout=0.5)
                except Queue.Empty:
                    device = None
                if device is not None:
                    print 'Stopping...'
                    device.stop()
                    device.join()
                    print 'Restarting...'
                    device.start()
                    print 'Started.'
        except KeyboardInterrupt:
            print 'Shutting down...'
            server.stop()
            server.join()
# end
