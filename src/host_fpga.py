__author__ = 'paulp'

from casperfpga import KatcpClientFpga
from host import Host


class FpgaHost(Host, KatcpClientFpga):
    """
    A Host that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, boffile=None, connect=False):
        Host.__init__(self, host, katcp_port)
        KatcpClientFpga.__init__(self, host, katcp_port, connect=connect)
        self.boffile = boffile

    def initialise(self, program=True, program_port=-1):
        """
        Initialise this host node to its normal running state.
        :param program: Should the FPGA be reprogrammed?
        :param program_port: Which port should be used for programming. -1 means random.
        :return: True if the FPGA client is running and connected.
        """
        if not self.is_connected():
            self.connect()
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
        return KatcpClientFpga.is_running(self)

    def tx_stop(self):
        """
        Stop the Gbe TX.
        :return:
        """
        self.registers.control.write('comms_en=False')