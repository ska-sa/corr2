#!/usr/bin/env python

import logging
import sys
import argparse
import katcp
from katcp.kattypes import request, return_reply, Float, Int, Str, Bool

from corr2 import fxcorrelator

USE_TORNADO = False
if USE_TORNADO:
    import tornado
    import signal
    from tornado import gen
else:
    import Queue


class KatcpLogFormatter(logging.Formatter):
    def format(self, record):
        translate_levels = {
            'WARNING': 'warn',
            'warning': 'warn'
        }
        if record.levelname in translate_levels:
            record.levelname = translate_levels[record.levelname]
        else:
            record.levelname = record.levelname.lower()
        record.msg = record.msg.replace(' ', '\_')
        return super(KatcpLogFormatter, self).format(record)


class KatcpLogEmitHandler(logging.StreamHandler):

    def __init__(self, katcp_server, stream=None):
        self.katcp_server = katcp_server
        super(KatcpLogEmitHandler, self).__init__(stream)

    def emit(self, record):
        """
        Replace a regular log emit with sending a katcp
        log message to all connected clients.
        :param record: the log record to process
        """
        try:
            if record.levelname == 'WARNING':
                record.levelname = 'WARN'
            inform_msg = self.katcp_server.create_log_inform(
                record.levelname.lower(),
                record.msg,
                record.filename)
            self.katcp_server.mass_inform(inform_msg)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


class Corr2Server(katcp.DeviceServer):

    # Interface version information.
    VERSION_INFO = ('corr2 instrument servlet', 0, 1)

    # Device server build / instance information.
    BUILD_INFO = ('corr2', 0, 1, 'alpha')

    def __init__(self, *args, **kwargs):
        super(Corr2Server, self).__init__(*args, **kwargs)
        if USE_TORNADO:
            self.set_concurrency_options(thread_safe=False,
                                         handler_thread=False)
        self.instrument = None

    @request()
    @return_reply()
    def request_ping(self, sock):
        """
        Just ping the server
        :param sock:
        :return: 'ok'
        """
        return 'ok',

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
        logging.info('got a create request with config file %s' % config_file)
        try:
            self.instrument = fxcorrelator.FxCorrelator(
                'a_correlator', config_source=config_file)
            self.instrument.standard_log_config()
            logging.info('made correlator okay')
            return 'ok',
        except Exception as e:
            localexc = e
            pass
        logging.error('create threw Exception: %s' % localexc.message)
        return 'fail', 'create threw Exception: %s' % localexc.message

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
            if monitor_vacc:
                self.instrument.xops.vacc_check_timer_start()
            return 'ok',
        except Exception as e:
            localexc = e
            pass
        logging.error('initialise threw Exception: %s' % localexc.message)
        return 'fail', 'initialise threw Exception: %s' % localexc.message

    @request(Str(multiple=True))
    @return_reply()
    def request_testfail(self, sock, *multiargs):
        """
        Just a command that fails. For testing.
        :param sock:
        :return: 'fail' and a test fail message
        """
        print multiargs
        return 'fail', 'a test failure, like it should'

    @request(Int(default=-1))
    @return_reply(Int())
    def request_digitiser_synch_epoch(self, sock, synch_time):
        """
        Set/Get the digitiser synch time, UNIX time.
        :param sock:
        :param synch_time:
        :return:
        """
        # if not self.instrument.initialised():
        #     logging.warn('request %s before initialised... refusing.' %
        #                  'request_digitiser_synch_epoch')
        #     return 'fail', 'request %s before initialised... refusing.' % \
        #            'request_digitiser_synch_epoch'
        if synch_time > -1:
            try:
                self.instrument.set_synch_time(synch_time)
            except RuntimeError as ve:
                return 'fail', 'request digitiser_synch_epoch did not ' \
                               'succeed, check the log - ' % ve.message
            except Exception as ve:
                return 'fail', 'request digitiser_synch_epoch failed for an ' \
                               'unknown reason, check the log - ' % ve.message
        return 'ok', self.instrument.get_synch_time()

    def _check_product_name(self, product_name):
        """
        Does a given product name exist on this instrument?
        :param product_name:
        :return:
        """
        return product_name in self.instrument.data_products

    @request(Str(), Str())
    @return_reply()
    def request_meta_destination(self, sock, stream, ipportstr):
        """

        :param sock:
        :return:
        """
        temp = ipportstr.split(':')
        txipstr = temp[0]
        txport = int(temp[1])
        try:
            self.instrument.product_set_meta_destination(
                stream, txip_str=txipstr, txport=txport)
        except Exception as e:
            return 'fail', 'setting meta destination for %s failed: %s' % \
                   (stream, e.message)
        return 'ok',

    @request(Str(), Str())
    @return_reply()
    def request_capture_destination(self, sock, stream, ipportstr):
        """
        Set/Get the capture destination for this instrument
        :param sock:
        :return:
        """
        try:
            temp = ipportstr.split(':')
            txipstr = temp[0]
            txport = int(temp[1])
            self.instrument.product_set_destination(
                stream, txipstr, txport)
        except Exception as e:
            return 'fail', 'setting capture destination for %s failed: %s' % \
                   (stream, e.message)
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_list(self, sock, product_name):
        """
        :param sock:
        :param product_name:
        :return:
        """
        product_names = []
        if product_name != '':
            product_names.append(product_name)
        else:
            product_names.extend(self.instrument.data_products.keys())
        for prod in product_names:
            if not self._check_product_name(prod):
                return 'fail', 'Product %s not in instrument data ' \
                               'products: %s' % (prod,
                                                 self.instrument.data_products)
            dprod = self.instrument.data_products[prod]
            sock.inform(prod, '%s:%d' % (
                dprod.destination.ip,
                dprod.destination.port))
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_start(self, sock, product_name):
        """
        :param sock:
        :return:
        """
        if not self._check_product_name(product_name):
            return 'fail', 'requested product name not found'
        self.instrument.product_issue_metadata(product_name)
        self.instrument.product_tx_enable(product_name)
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_stop(self, sock, product_name):
        """
        :param sock:
        :return:
        """
        if not self._check_product_name(product_name):
            return 'fail', 'requested product name not found'
        self.instrument.product_tx_disable(product_name)
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_meta(self, sock, product_name):
        """

        :param sock:
        :return:
        """
        if not self._check_product_name(product_name):
            return 'fail', 'requested product name not found'
        self.instrument.product_issue_metadata(product_name)
        return 'ok',

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
            except ValueError as ve:
                return 'fail', 'provided input labels were not ' \
                               'correct: %s' % ve.message
            except Exception as ve:
                return 'fail', 'provided input labels were not ' \
                               'correct: Unhandled exception - ' % ve.message
        else:
            return tuple(['ok'] + self.instrument.get_labels())

    @request(Str(default=''), Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_gain(self, sock, source_name, *eq_vals):
        """
        Apply and/or get the gain settings for an input
        :param sock:
        :param source_name: the source on which to act
        :param eq_vals: the equaliser values
        :return:
        """
        if source_name == '':
            return 'fail', 'no source name given'
        if len(eq_vals) > 0 and eq_vals[0] != '':
            try:
                self.instrument.fops.eq_set(True, source_name, list(eq_vals))
            except Exception as e:
                return 'fail', 'unknown exception: %s' % e.message
        _src = self.instrument.fops.eq_get(source_name)
        eqstring = str(_src[source_name]['eq'])
        eqstring = eqstring.replace('(', '').replace(')', '')
        eqstring = eqstring.replace('[', '').replace(']', '')
        eqstring = eqstring.replace(',', '')
        return tuple(['ok'] + eqstring.split(' '))

    @request(Str(), Int(), Int(), Int())
    @return_reply(Str(multiple=True))
    def request_gain_range(self, sock, source_name, value, fstart, fstop):
        """
        Apply and/or get the gain settings for an input
        :param sock:
        :param source_name: the source on which to act
        :param eq_vals: the equaliser values
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
                return 'fail', 'unknown exception: %s' % e.message
        _src = self.instrument.fops.eq_get(source_name)
        eqstring = str(_src[source_name]['eq'])
        eqstring = eqstring.replace('(', '').replace(')', '')
        eqstring = eqstring.replace('[', '').replace(']', '')
        eqstring = eqstring.replace(',', '')
        return tuple(['ok'] + eqstring.split(' '))

    @request(Float(), Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_delays(self, sock, loadtime, *delay_strings):
        """

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
            return 'fail', 'could not set delays - %s' % e.message

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
            except:
                return 'fail', 'could not set accumulation length'
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
            logging.info(e)
            return 'fail', 'failed to read quant snap data for ' \
                           'given source %s' % source_name
        quant_string = ''
        for complex_word in snapdata:
            quant_string += ' %s' % str(complex_word)
        quant_string = quant_string.replace('(', '').replace(')', '')
        quant_string = quant_string.replace('[', '').replace(']', '')
        quant_string = quant_string.replace(',', '')
        return tuple(['ok'] + quant_string.split(' '))

    @request(Str(), Str(), Float(multiple=True))
    @return_reply(Str(multiple=True))
    def request_beam_weights(self, sock, beam_name, input_name, *weight_list):
        """
        Set the weight for a input
        :param sock:
        :return:
        """
        if not self.instrument.found_beamformer:
            return 'fail', 'Cannot run beamformer commands with no beamformer'
        try:
            self.instrument.bops.set_beam_weights(beam_name,
                                                  input_name,
                                                  weight_list[0])
        except Exception as e:
            return 'fail', '%s' % e.message
        cur_weights = self.instrument.bops.get_beam_weights(
            beam_name, input_name)
        wght_str = str(cur_weights)
        wght_str = wght_str.replace('(', '').replace(')', '')
        wght_str = wght_str.replace('[', '').replace(']', '')
        wght_str = wght_str.replace(',', '')
        return tuple(['ok'] + wght_str.split(' '))

    @request(Str(), Float(), Float())
    @return_reply(Str(), Str(), Str())
    def request_beam_passband(self, sock, beam_name, bandwidth, centerfreq):
        """
        Set the beamformer bandwidth/partitions
        :param sock:
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
            return 'fail', '%s' % e.message
        return 'ok', beam_name, str(cur_bw), str(cur_cf)

    @request()
    @return_reply()
    def request_vacc_sync(self, sock):
        """

        :param sock:
        :return:
        """
        try:
            self.instrument.xops.vacc_sync()
        except Exception as e:
            return 'fail', 'Error syncing vaccs: %s' % e.message
        return 'ok',

    @request(Int(default=-1))
    @return_reply(Int())
    def request_fft_shift(self, sock, new_shift):
        """

        :param sock:
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
    @return_reply()
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
        return 'ok',

    # @request(Int(default=-1), Int(default=-1))
    # @return_reply(Int(), Int())
    # def request_eq(self, sock, new_real, new_imag):
    #     """
    #
    #     :param sock:
    #     :return:
    #     """
    #     if new_shift >= 0:
    #         current_shift_value = fengops.feng_set_eq_all(self.instrument, new_real, new_imag)
    #     else:
    #         current_shift_value = fengops.feng_get_fft_shift_all(self.instrument)
    #         current_shift_value = current_shift_value[current_shift_value.keys()[0]]
    #     return 'ok', current_shift_value

    @request(Str(default='a string woohoo'), Int(default=777))
    @return_reply()
    def request_pang(self, sock, astring, anint):
        """
        ping-pong
        :return:
        """
        print 'pong', astring, anint
        return 'ok'

if USE_TORNADO:
    @gen.coroutine
    def on_shutdown(ioloop, server):
        print('Shutting down')
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
    # parser.add_argument('-c', '--config', dest='configfile', action='store',
    #                     default='', type=str,
    #                     help='config file location')
    args = parser.parse_args()

    try:
        log_level = getattr(logging, args.loglevel)
    except:
        raise RuntimeError('Received nonsensical log level %s' % args.loglevel)

    # set up the logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if args.lfm or (not sys.stdout.isatty()):
        use_katcp_logging = True
    else:
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                      '%(filename)s:%(lineno)s - '
                                      '%(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        use_katcp_logging = False

    if USE_TORNADO:
        ioloop = tornado.ioloop.IOLoop.current()
        server = Corr2Server('127.0.0.1', args.port)
        signal.signal(
            signal.SIGINT,
            lambda sig, frame: ioloop.add_callback_from_signal(
                on_shutdown, ioloop, server))
        print 'Server listening on port %d, ' % args.port
        server.set_ioloop(ioloop)
        ioloop.add_callback(server.start)
        ioloop.start()
    else:
        print 'Server listening on port %d, ' % args.port,
        queue = Queue.Queue()
        server = Corr2Server('127.0.0.1', args.port)
        if use_katcp_logging:
            katcp_emit_handler = KatcpLogEmitHandler(server, stream=sys.stdout)
            katcp_emit_handler.setLevel(log_level)
            root_logger.addHandler(katcp_emit_handler)
        server.set_restart_queue(queue)
        server.start()
        print 'started. Running somewhere in the ether... exit however ' \
              'you see fit.'
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
