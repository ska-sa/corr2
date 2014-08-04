#!/usr/bin/env python

__author__ = 'paulp'

import logging
import sys
import argparse
import Queue
import katcp
from katcp.kattypes import request, return_reply, Float, Int, Str, Discrete
from corr2 import fxcorrelator

logging.basicConfig(level=logging.WARN, stream=sys.stderr, format='%(asctime)s - %(name)s - %(filename)s:%(lineno)s - %(levelname)s - %(message)s')


class Corr2Server(katcp.DeviceServer):

    ## Interface version information.
    VERSION_INFO = ('corr2 instrument servlet', 0, 1)

    ## Device server build / instance information.
    BUILD_INFO = ('corr2', 0, 1, 'alpha')

    def __init__(self, *args, **kwargs):
        super(Corr2Server, self).__init__(*args, **kwargs)
        self.instrument = None

    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        pass

    @request()
    @return_reply()
    def request_ping(self, sock):
        """

        :param sock:
        :return: 'ok'
        """
        return 'ok',

    @request(Str(), Int(default=100))
    @return_reply()
    def request_create(self, sock, config_file, log_len):
        """

        :param sock:
        :param config_file:
        :param log_len:
        :return:
        """
        try:
            self.instrument = fxcorrelator.FxCorrelator('RTS correlator', config_source=config_file)
            return 'ok',
        except:
            pass
        return 'fail',


    @request(Int(default=-1))
    @return_reply()
    def request_initialise(self, sock, skip):
        """

        :param sock:
        :return:
        """
        try:
            self.instrument.initialise(program=True, tvg=False, skip_arp_wait=True if skip == 1 else False)
            return 'ok',
        except:
            pass
        return 'fail',

    @request(Str(multiple=True))
    @return_reply()
    def request_testfail(self, sock, *multiargs):
        """

        :param sock:
        :return: 'fail' and a test fail message
        """
        print multiargs
        return 'fail', 'a test failure, like it should'

    @request(Int())
    @return_reply()
    def request_digitiser_synch_epoch(self, sock, synch_time):
        """
        Set the digitiser synch time, UNIX time.
        :param sock:
        :param synch_time:
        :return:
        """
        try:
            self.instrument.set_synch_time(synch_time)
        except:
            return 'fail', 'request %s did not succeed, check the log' % 'digitiser_synch_epoch'
        return 'ok',

    @request(Str(), Str())
    @return_reply()
    def request_capture_destination(self, sock, stream, ipportstr):
        """

        :param sock:
        :return:
        """
        temp = ipportstr.split(':')
        txipstr = temp[0]
        txport = int(temp[1])
        self.instrument.set_destination(txip_str=txipstr, txport=txport)
        return 'ok',

    @request(Str(default=''))
    @return_reply()
    def request_capture_list(self, sock, product_name):
        """
        :param sock:
        :return:
        """
        if product_name == '':
            product_string = str(self.instrument.configd['xengine']['output_products']).replace('[', '').replace(']', '')
        else:
            product_string = product_name
            if product_name not in self.instrument.configd['xengine']['output_products']:
                return 'fail', 'requested product name not found'
        sock.inform(product_string, '%s:%d' % (self.instrument.txip_str, self.instrument.txport))
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

    @request()
    @return_reply()
    def request_issue_spead_metadata(self, sock):
        """

        :param sock:
        :return:
        """
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
            if not self.instrument.set_labels(newlist):
                return 'fail', 'provided input labels were not correct'
        return 'ok', self.instrument.get_labels()

    @request()
    @return_reply()
    def request_gain(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

    @request()
    @return_reply()
    def request_delays(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

    @request()
    @return_reply(Float())
    def request_accumulation_length(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok', (self.instrument.accumulation_len * 1.0)

    @request()
    @return_reply()
    def request_quantiser_snapshot(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

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

    @request(Str(default='a string woohoo'), Int(default=777))  # arguments to this request, # create the message with these args
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
    parser.add_argument('-p', '--port', dest='port', action='store',
                        default=1235, type=int,
                        help='bind to this port to receive KATCP messages')
    # parser.add_argument('-c', '--config', dest='configfile', action='store',
    #                     default='', type=str,
    #                     help='config file location')
    args = parser.parse_args()

    print 'Server listening on port %d, ' % args.port,
    queue = Queue.Queue()
    server = Corr2Server('127.0.0.1', args.port)
    server.set_restart_queue(queue)
    server.start()
    print 'started. Ctrl-C to exit.'

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