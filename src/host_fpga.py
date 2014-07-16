__author__ = 'paulp'

from casperfpga import KatcpClientFpga
from host import Host

FORCED_PORT = 3333


class FpgaHost(Host, KatcpClientFpga):
    """
    A Host that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, boffile=None, connect=False):
        Host.__init__(self, host, katcp_port)
        KatcpClientFpga.__init__(self, host, katcp_port, connect=connect)
        self.boffile = boffile

    def initialise(self, program=True):
        """
        Initialise this host node to its normal running state.
        """
        self.connect()
        if program:
            self.upload_to_ram_and_program(self.boffile, port=FORCED_PORT)
        return self.is_running()

    def ping(self):
        """
        All hosts must supply a ping method that returns true or false.
        @return: True or False
        """
        return self.is_running()

    def is_running(self):
        """All hosts must supply a is_running method that returns true or false.
        @return: True or False
        """
        return KatcpClientFpga.is_running(self)
