#!/usr/bin/env python

__author__ = 'paulp'

import logging
import sys
import argparse
import Queue

import katcp
from katcp.kattypes import request, return_reply, Float, Int, Str, Bool
from corr2 import fxcorrelator
from corr2 import fxcorrelator_xengops as xengops
from corr2 import fxcorrelator_fengops as fengops


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
        """
        try:
            if record.levelname == 'WARNING':
                record.levelname = 'WARN'
            inform_msg = self.katcp_server.create_log_inform(record.levelname.lower(),
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
            self.instrument = fxcorrelator.FxCorrelator('RTS correlator', config_source=config_file)
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

    @request(Bool(default=True))
    @return_reply()
    def request_initialise(self, sock, program):
        """
        Initialise self.instrument
        :param sock:
        :return:
        """
        try:
            self.instrument.initialise(program=program)
            return 'ok',
        except Exception as e:
            localexc = e
            pass
        logging.error('create threw Exception: %s' % localexc.message)
        return 'fail', 'create threw Exception: %s' % localexc.message

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
        if synch_time > -1:
            try:
                self.instrument.set_synch_time(synch_time)
            except RuntimeError:
                return 'fail', 'request digitiser_synch_epoch did not succeed, check the log'
            except Exception:
                return 'fail', 'request digitiser_synch_epoch failed for an unknown reason, check the log'
        return 'ok', self.instrument.get_synch_time()

    @request(Str(), Str())
    @return_reply()
    def request_capture_destination(self, sock, stream, ipportstr):
        """
        Set/Get the capture destination for this instrument
        :param sock:
        :return:
        """
        if stream not in self.instrument.configd['xengine']['output_products']:
            return 'fail', 'stream %s is not in product list: %s' % (stream, self.instrument.configd['xengine']['output_products'])
        temp = ipportstr.split(':')
        txipstr = temp[0]
        txport = int(temp[1])
        self.instrument.set_meta_destination(txip_str=txipstr, txport=txport)
        self.instrument.set_stream_destination(txip_str=txipstr, txport=txport)
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_list(self, sock, product_name):
        """
        :param sock:
        :return:
        """
        if product_name == '':
            product_list = self.instrument.configd['xengine']['output_products']
            product_string = str(product_list).replace('[', '').replace(']', '')
        else:
            product_string = product_name
            if product_name not in self.instrument.configd['xengine']['output_products']:
                return 'fail', 'requested product name not found'
        sock.inform(product_string, '%s:%d' % (self.instrument.xeng_tx_destination[0],
                                               self.instrument.xeng_tx_destination[1]))
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_start(self, sock, product_name):
        """
        :param sock:
        :return:
        """
        if product_name not in self.instrument.configd['xengine']['output_products']:
            return 'fail', 'requested product name not found'
        self.instrument.tx_start()
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_stop(self, sock, product_name):
        """
        :param sock:
        :return:
        """
        if product_name not in self.instrument.configd['xengine']['output_products']:
            return 'fail', 'requested product name not found'
        self.instrument.tx_stop()
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_meta(self, sock, product_name):
        """

        :param sock:
        :return:
        """
        if product_name not in self.instrument.configd['xengine']['output_products']:
            return 'fail', 'requested product name not found'
        self.instrument.spead_issue_meta()
        return 'ok',

    @request(Str(default='', multiple=True))
    @return_reply(Str(multiple=True))
    def request_input_labels(self, sock, *newlist):
        """

        :param sock:
        :return:
        """
        if len(newlist) == 1:
            if newlist[0] == '':
                newlist = []
        if len(newlist) > 0:
            try:
                self.instrument.set_labels(newlist)
            except:
                return 'fail', 'provided input labels were not correct'
        return 'ok', self.instrument.get_labels()

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
                fengops.feng_eq_set(self.instrument, True, source_name, list(eq_vals))
            except Exception as e:
                return 'fail', 'unknown exception: %s' % e.message
        eqstring = str(fengops.feng_eq_get(self.instrument, source_name)[source_name]['eq'])
        eqstring = eqstring.replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace(',', '')
        return 'ok', eqstring

    @request()
    @return_reply()
    def request_delays(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

    @request(Float(default=-1.0))
    @return_reply(Float())
    def request_accumulation_length(self, sock, new_acc_time):
        """
        Set & get the accumulation time
        :param sock:
        :param new_acc_time: if this is -1.0, the current acc len will be returned, but nothing set
        :return:
        """
        if new_acc_time != -1.0:
            try:
                xengops.xeng_set_acc_time(self.instrument, new_acc_time)
            except:
                return 'fail', 'could not set accumulation length'
        return 'ok', xengops.xeng_get_acc_time(self.instrument)

    @request(Str(default=''))
    @return_reply(Str(multiple=True))
    def request_quantiser_snapshot(self, sock, source_name):
        """
        Get a list of values representing the quantised spectrum for the given source
        :param sock:
        :param source_name: the source to query
        :return:
        """
        try:
            snapdata = fengops.feng_get_quant_snap(self.instrument, source_name)
        except Exception as e:
            logging.info(e)
            return 'fail', 'failed to read quant snap data for given source %s' % source_name
        quant_string = ''
        for complex_word in snapdata:
            quant_string += ' %s' % str(complex_word)
        quant_string = quant_string.replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace(',', '')
        return 'ok', quant_string

    @request()
    @return_reply()
    def request_beam_weights(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

    @request()
    @return_reply()
    def request_beam_passband(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

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
        self.instrument.set_meta_destination(txip_str=txipstr, txport=txport)
        return 'ok',

    @request()
    @return_reply()
    def request_vacc_sync(self, sock):
        """

        :param sock:
        :return:
        """
        xengops.xeng_vacc_sync(self.instrument)
        return 'ok',

    @request(Int(default=-1))
    @return_reply(Int())
    def request_fft_shift(self, sock, new_shift):
        """

        :param sock:
        :return:
        """
        if new_shift >= 0:
            current_shift_value = fengops.feng_set_fft_shift_all(self.instrument, new_shift)
        else:
            current_shift_value = fengops.feng_get_fft_shift_all(self.instrument)
            current_shift_value = current_shift_value[current_shift_value.keys()[0]]
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
        return 'ok',

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Start a corr2 instrument server.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-p', '--port', dest='port', action='store', default=1235, type=int,
                        help='bind to this port to receive KATCP messages')
    parser.add_argument('--log_level', dest='loglevel', action='store', default='INFO',
                        help='log level to set')
    parser.add_argument('--log_format_katcp', dest='lfm', action='store_true', default=False,
                        help='format log messsages for katcp')
    # parser.add_argument('-c', '--config', dest='configfile', action='store',
    #                     default='', type=str,
    #                     help='config file location')
    args = parser.parse_args()

    try:
        log_level = eval('logging.%s' % args.loglevel)
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

    print 'Server listening on port %d, ' % args.port,
    queue = Queue.Queue()
    server = Corr2Server('127.0.0.1', args.port)
    if use_katcp_logging:
        katcp_emit_handler = KatcpLogEmitHandler(server, stream=sys.stdout)
        katcp_emit_handler.setLevel(log_level)
        root_logger.addHandler(katcp_emit_handler)
    server.set_restart_queue(queue)
    server.start()
    print 'started. Running somewhere in the ether... exit however you see fit.'

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
