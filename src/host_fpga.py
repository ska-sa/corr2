__author__ = 'paulp'

from casperfpga.katcp_fpga import KatcpFpga
from host import Host


class FpgaHost(Host, KatcpFpga):
    """
    A Host that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, boffile=None, connect=False):
        Host.__init__(self, host, katcp_port)
        KatcpFpga.__init__(self, host, katcp_port, connect=connect)
        self.boffile = boffile

    def _no_implement_connect(self, program=True, program_port=-1):
        """
        Initialise this host node to its normal running state.
        :param program: Should the FPGA be reprogrammed?
        :param program_port: Which port should be used for programming. -1 means random.
        :return: True if the FPGA client is running and connected.
        """
        if not self.is_connected():
            KatcpFpga.connect(self)
        if program:
            self.upload_to_ram_and_program(self.boffile, port=program_port)
        self.test_connection()
        self.get_system_information()
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
        return KatcpFpga.is_running(self)
