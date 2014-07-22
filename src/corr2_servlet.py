__author__ = 'paulp'

import logging
import sys
import argparse
import Queue
import katcp
from katcp.kattypes import request, return_reply, Float, Int, Str, Bool
from fxcorrelator import FxCorrelator

logging.basicConfig(level=logging.WARN,
                    stream=sys.stderr,
                    format='%(asctime)s - %(name)s - %(filename)s:%(lineno)s - %(levelname)s - %(message)s')


class Corr2Server(katcp.DeviceServer):

    ## Interface version information.
    VERSION_INFO = ('corr2 instrument servlet', 0, 1)

    ## Device server build / instance information.
    BUILD_INFO = ('corr2', 0, 1, 'alpha')

    def setup_sensors(self):
        """
        Must be implemented in interface.
        :return: nothing
        """
        pass

    def __init__(self, *args, **kwargs):
        super(Corr2Server, self).__init__(*args, **kwargs)
        self.instrument = None

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
        self.instrument = FxCorrelator('RTS correlator', config_source=config_file)
        return 'ok',

    @request()
    @return_reply()
    def request_testfail(self, sock):
        """

        :param sock:
        :return: 'fail' and a test fail message
        """
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

    @request()
    @return_reply()
    def request_capture_list(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

    @request(Str(), Int())
    @return_reply()
    def request_capture_destination(self, sock, ipstr, port):
        """

        :param sock:
        :return:
        """
        self.instrument.set_destination(self, txip_str=ipstr, txport=port)
        return 'ok',

    @request()
    @return_reply()
    def request_capture_start(self, sock):
        """

        :param sock:
        :return:
        """
        self.instrument.start_tx()
        return 'ok',

    @request()
    @return_reply()
    def request_capture_stop(self, sock):
        """

        :param sock:
        :return:
        """
        self.instrument.stop_tx()
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

    @request()
    @return_reply()
    def request_input_labels(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

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
    @return_reply()
    def request_accumulation_length(self, sock):
        """

        :param sock:
        :return:
        """
        return 'ok',

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