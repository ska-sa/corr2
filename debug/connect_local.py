__author__ = 'paulp'

import logging
import time
import argparse
import katcp

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class KatcpClient(katcp.CallbackClient):

    def __init__(self, host_device, katcp_port=7147, timeout=2.0, connect=True):
        """Constructor.
        """
        if (not isinstance(host_device, str)) or (not isinstance(katcp_port, int)):
            raise TypeError('host must be a string, katcp_port must be an int')
        self.host = host_device
        self.katcp_port = katcp_port
        katcp.CallbackClient.__init__(self, host_device, katcp_port, tb_limit=20, timeout=timeout, logger=LOGGER,
                                      auto_reconnect=True)
        self._timeout = timeout
        if connect:
            self.connect(self._timeout)
            if not self.is_connected():
                raise RuntimeError('Could not connect.')
        LOGGER.info('KatcpClient %s:%s created%s.', host_device, katcp_port, ' & daemon started' if connect else '')

    def connect(self, timeout=1):
        """Start the KATCP daemon on the device.
        """
        stime = time.time()
        while (not self.is_connected()) and (time.time()-stime < timeout):
            try:
                self.start(daemon=True)
            except RuntimeError:
                pass
            time.sleep(0.1)
        if self.is_connected():
            LOGGER.info('%s: daemon started', self.host)
        else:
            LOGGER.error('%s: COULD NOT CONNECT', self.host)

    def disconnect(self):
        """Stop the KATCP daemon on the device.
        """
        self.stop()
        LOGGER.info('%s: daemon stopped', self.host)

    def katcprequest(self, name, request_timeout=-1.0, require_ok=True, request_args=()):
        """Make a blocking request and check the result.
           Raise an error if the reply indicates a request failure.

           @param self  This object.
           @param name  String: name of the request message to send.
           @param request_timeout  Int: number of seconds after which the request must time out
           @param args  List of strings: request arguments.
           @return  Tuple: containing the reply and a list of inform messages.
           """
        # TODO raise sensible errors
        if request_timeout == -1:
            request_timeout = self._timeout
        request = katcp.Message.request(name, *request_args)
        reply, informs = self.blocking_request(request, timeout=request_timeout)
        if (reply.arguments[0] != katcp.Message.OK) and require_ok:
            raise RuntimeError('Request %s on host %s failed.\n\tRequest: %s\n\tReply: %s'
                                      % (request.name, self.host, request, reply))
        return reply, informs

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Start a corr2 instrument client.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-p', '--port', dest='port', action='store',
                        default=1235, type=int,
                        help='bind to this port to send KATCP messages')
    args = parser.parse_args()

    client = KatcpClient('127.0.0.1', args.port)

    reply_msg, informs = client.katcprequest('ping', request_timeout=-1.0, require_ok=True)

    reply_msg, informs = client.katcprequest('testfail', request_timeout=-1.0, require_ok=False, request_args=['lots', 'of', 'arguments', 'go', 'here'])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('create', request_timeout=-1.0, require_ok=True, request_args=['/home/paulp/code/corr2.ska.github/src/fxcorr.ini'])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    #reply_msg, informs = client.katcprequest('initialise', request_timeout=240.0, require_ok=True, request_args=[1])
    reply_msg, informs = client.katcprequest('initialise', request_timeout=40.0, require_ok=True)
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('accumulation-length', request_timeout=-1.0, require_ok=True)
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('accumulation-length', request_timeout=-1.0, require_ok=True, request_args=[200])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('capture-start', request_timeout=-1.0, require_ok=True,
                                             request_args=['cross_products'])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('capture-destination', request_timeout=-1.0, require_ok=True, request_args=['cross_products', '10.1.0.1:8888'])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    """
    reply_msg, informs = client.katcprequest('capture-list', request_timeout=-1.0, require_ok=True)
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('capture-list', request_timeout=-1.0, require_ok=False, request_args=['boobs!'])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('capture-destination', request_timeout=-1.0, require_ok=True, request_args=['bob', '12.13.14.15:6666'])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('input-labels', request_timeout=-1.0, require_ok=True)
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('input-labels', request_timeout=-1.0, require_ok=True, request_args=['bob', 'sally', 'margaret', 'steve', 'arthur', 'kevin', 'jane', 'jim'])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs

    reply_msg, informs = client.katcprequest('input-labels', request_timeout=-1.0, require_ok=True, request_args=['bob', 'sally', 'margaret', 'steve', 'arthur', 'kevin', 'jane'])
    print reply_msg.arguments
    print reply_msg.mid
    print reply_msg.mtype
    print informs


    # reply_msg, informs = client.katcprequest('capture-start', request_timeout=-1.0, require_ok=True, request_args=['asdasdasd'])
    # print reply_msg.arguments
    # print reply_msg.mid
    # print reply_msg.mtype
    # print informs

    client.katcprequest('digitiser-synch-epoch', request_timeout=-1.0, require_ok=True, request_args=(23,))
    """

    time.sleep(1)

    client.disconnect()

# end