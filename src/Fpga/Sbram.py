import logging
logger = logging.getLogger(__name__)

import Memory.Memory

class Sbram(Memory.Memory):
    # General SBRAM memory on the FPGA.
    def __init__(self):
        raise NotImplementedError
