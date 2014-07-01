'''
corr2 - control and monitoring for casper-based instruments.
'''

# import modules into corr2 that fpgadevice modules will need
import bitfield, misc, types

# import all fpgadevice modules
import fpgadevice

# import the base corr2 modules
import engine, instrument, async_requester,\
    katcp_client_fpga, host, configuration_katcp_client, \
    engine_fpga, digitiser, fengine, xengine, fengine_fpga, xengine_fpga, \
    wb_rts_fengine, wb_rts_xengine, mock_rts, instrument, fxcorrelator, fxcorrelator_fpga, scroll \
# end
