import numpy
import logging

LOGGER = logging.getLogger()

# import casperfpga
#
# ROACH_IP = '192.168.65.195'
# ROACH_FPG = 'roach.fpg'
#
# SKARAB_IP = '10.99.45.170'
# SKARAB_FPG = 'skarab.fpg'
#
# # roach program
# roach = casperfpga.CasperFpga(ROACH_IP)
# roach.upload_to_ram_and_program(ROACH_FPG)
# # already running
# roach = casperfpga.CasperFpga(ROACH_IP)
# roach.get_system_information()
#
# # skarab programming
# skarab = casperfpga.CasperFpga(SKARAB_IP)
# skarab.upload_to_ram_and_program(SKARAB_FPG)
# # already running
# skarab = casperfpga.CasperFpga(SKARAB_IP)
# # remember that skarabs will need the fpg given
# # to them, you can't retrieve it from the ublaze
# # like you can with roach
# skarab.get_system_information(SKARAB_FPG)
#
# # end
#


def bin2fp(raw_word, bitwidth, bin_pt, signed):
    """
    Convert a raw number based on supplied characteristics.
    :param raw_word: the number to convert
    :param bitwidth: its width in bits
    :param bin_pt: the location of the binary point
    :param signed: whether it is signed or not
    :return: the formatted number, long, float or int
    """
    word_masked = raw_word & ((2**bitwidth)-1)
    if signed and (word_masked >= 2**(bitwidth-1)):
        word_masked -= 2**bitwidth
    if bin_pt == 0:
        if bitwidth <= 63:
            return int(word_masked)
        else:
            return long(word_masked)
    else:
        quotient = word_masked / (2**bin_pt)
        rem = word_masked - (quotient * (2**bin_pt))
        return quotient + (float(rem) / (2**bin_pt))
    raise RuntimeError


def fp2fixed(num, bitwidth, bin_pt, signed):
    """
    Convert a floating point number to its fixed point equivalent.
    :param num:
    :param bitwidth:
    :param bin_pt:
    :param signed:
    :return:
    """
    _format = '%s%i.%i' % ('fix' if signed else 'ufix', bitwidth, bin_pt)
    LOGGER.debug('Converting %f to %s' % (num, _format))
    if bin_pt >= bitwidth:
        raise ValueError('Cannot have bin_pt >= bitwidth')
    if bin_pt < 0:
        raise ValueError('bin_pt < 0 makes no sense')
    if (not signed) and (num < 0):
        raise ValueError('Cannot represent negative number (%f) in %s' % (
            num, _format))
    if num == 0:
        return 0
    LOGGER.debug('iwl(%i) fwl(%i)' % (bitwidth - bin_pt, bin_pt))
    scaled = num * (2**bin_pt)
    LOGGER.debug('%.10f scaled to %.10f' % (num, scaled))
    scaled = round(scaled)
    LOGGER.debug('And rounded off to %i' % scaled)
    if signed:
        _nbits = bitwidth - 1
        limits = [-1 * (2**_nbits), (2**_nbits) - 1]
    else:
        limits = [0, (2**bitwidth) - 1]
    LOGGER.debug('limits are %s' % limits)
    scaled = min(limits[1], max(limits[0], scaled))
    LOGGER.debug('limited number = %f' % scaled)
    unscaled = scaled / ((2**bin_pt) * 1.0)
    LOGGER.debug('unscaled = %.15f' % unscaled)
    return unscaled


def cast_fixed(fpnum, bitwidth, bin_pt):
    """
    Represent a fixed point number as an unsigned number, like the Xilinx
    reinterpret block.
    :param fpnum:
    :param bitwidth:
    :param bin_pt:
    :return:
    """
    if fpnum == 0:
        return 0
    val = int(fpnum * (2**bin_pt))
    if fpnum < 0:
        val += 2**bitwidth
    return val


def cyclenum(num, bw, bp, sgn):
    a = fp2fixed(num, bw, bp, sgn)
    b = cast_fixed(a, bw, bp)
    c = bin2fp(b, bw, bp, sgn)
    # print(num, a, b, c
    # print(''

cyclenum(0.5, 8, 7, True)
cyclenum(0.5, 8, 7, False)
cyclenum(0.5, 8, 3, True)
cyclenum(0.5, 8, 3, False)
cyclenum(-0.777, 8, 3, True)
cyclenum(-0.777, 8, 7, True)


class Test(object):

    def __init__(self):
        self.center_freq = 1284000000
        self.bandwidth = 856000000

        self.partitions_active = []

        self.partitions_total = 32

    def bandwidth_to_partitions(self, bandwidth, centerfreq):
        """
        Given a bandwidth and center frequency, return the relevant
        partitions that should be activated.
        :param bandwidth: in hz
        :param centerfreq: in hz
        :return: a list of partition numbers
        """
        # configured freq range
        startbw = self.center_freq - (self.bandwidth / 2.0)
        endbw = self.center_freq + (self.bandwidth / 2.0)
        # given freq range
        startgiven = centerfreq - (bandwidth / 2.0)
        endgiven = centerfreq + (bandwidth / 2.0)
        # check
        if (startgiven < startbw) or (endgiven > endbw):
            raise ValueError('Given freq range (%.2f, %.2f) falls outside '
                             'beamformer range (%.2f, %.2f)' %
                             (startgiven, endgiven, startbw, endbw))
        # bb and partitions
        bbstart = startgiven - startbw
        bbend = endgiven - startbw
        hz_per_partition = self.bandwidth / self.partitions_total
        part_start = int(numpy.floor(bbstart / hz_per_partition))
        part_end = int(numpy.ceil(bbend / hz_per_partition))
        return range(part_start, part_end)

    def partitions_to_bandwidth(self, partitions=None):
        """
        Given a list of partitions, return the corresponding cf and bw
        :param partitions: a list of partitions
        :return: tuple, (bw, cf)
        """
        if not partitions:
            partitions = self.partitions_active
        if len(partitions) == 0:
            return 0, 0
        hz_per_partition = self.bandwidth / self.partitions_total
        rv_bw = hz_per_partition * len(partitions)
        first_part = partitions[0]
        part_start_hz = first_part * hz_per_partition
        actual_start_hz = self.center_freq - (self.bandwidth / 2.0)
        rv_cf = actual_start_hz + part_start_hz + (rv_bw / 2.0)
        return rv_bw, rv_cf

# t = Test()
#
# (bw, cf) = t.partitions_to_bandwidth([0])
#
# start = cf - (bw / 2.0)
# end = start + bw
#
# print(start, end, cf
