__author__ = 'paulp'

import numpy
import struct


def float2str(self, coeffs, n_bits, bin_pt=0, signed=True):
    """ Convert floating point coeffs into a string with n_bits of resolution and a binary point at bin_pt
    @param coeffs: floating point coefficients
    @param n_bits: fixed point number of bits
    @param bin_pt: binary point
    @param signed: if data should be signed
    @return: string ready for writing to BRAM
    """

    if len(coeffs) == 0:
        raise RuntimeError('Passing empty coeffs list')
    if bin_pt < 0:
        raise RuntimeError('Binary point cannot be less than 0')

    step = 1/(2**bin_pt)  # coefficient resolution

    if signed:
        min_val = -(2**(n_bits-bin_pt-1))
        max_val = -(min_val)-step
    else:
        min_val = 0
        max_val = 2**(n_bits-bin_pt)-step

    if numpy.max(coeffs) > max_val or numpy.min(coeffs) < min_val:
        raise RuntimeError('Coeffs out of range')

    is_complex = numpy.iscomplexobj(coeffs)
    if is_complex:
        n_coeffs = len(coeffs)*2
        coeffs = numpy.array(coeffs, dtype = numpy.complex128)
    else:
        n_coeffs = len(coeffs)
        coeffs = numpy.array(coeffs, dtype = numpy.float64)

    # compensate for fractional bits
    coeffs = (coeffs * 2**bin_pt)

    byte_order = '>'  # big endian

    if n_bits == 16:
        if signed:
            pack_type = 'h'
        else:
            pack_type = 'H'
    else:
        raise RuntimeError('Don''t know how to pack data type with %i bits'  % n_bits)

    coeff_str = struct.pack('%s%i%s' %(byte_order, n_coeffs, pack_type), *coeffs.view(dtype=numpy.float64))
    return coeff_str


def _str2float(self, string, n_bits, bin_pt=0, iscomplex=True, signed=True):
    """ Unpack string according to format specified. Return array of floats
    @param string: string as read from BRAM
    @param n_bits: resolution
    @param iscomplex: whether the data is complex
    @param bin_pt: binary point
    @param signed: whether the data is signed
    """

    byte_order = '>'  # big endian for CASPER data

    n_vals = len(string)/(n_bits/8)

    if n_bits == 16:
        if signed:
            pack_type = 'h'
        else:
            pack_type = 'H'
    else:
        raise RuntimeError('Don''t know how to pack data type with %i bits'  % n_bits)

    coeffs = struct.unpack('%s%i%s'%(byte_order, n_vals, pack_type), string)
    coeffs_na = numpy.array(coeffs, dtype = numpy.float64)

    coeffs = coeffs_na/(2**bin_pt)  # scale by binary points

    if iscomplex:
        # change view to 64 bit floats packed as complex 128 bit values
        coeffs = coeffs.view(dtype = numpy.complex128)

    return coeffs
