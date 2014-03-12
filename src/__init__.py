'''
corr2 - control and monitoring for casper-based instruments.
'''

# import modules into corr2 that fpgadevice modules will need
import bitfield, misc, types

# import all fpgadevice modules
import fpgadevice

# import the base corr2 modules
import async_requester, digitiser, engine, fengine, \
    fxcorrelator, hostdevice, instrument, katcp_client_fpga, xengine

# end
