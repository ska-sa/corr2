"""
corr2 - control and monitoring for casper-based instruments.
"""

# import the base corr2 modules
import fxcorrelator
import host_fpga
import host
import instrument
import utils
# corr2 requires casperfpga

# BEGIN VERSION CHECK
# Get package version when locally imported from repo or via -e develop install
try:
    import katversion as _katversion
except ImportError:
    import time as _time
    __version__ = "0.0+unknown.{}".format(_time.strftime('%Y%m%d%H%M'))
else:
    __version__ = _katversion.get_version(__path__[0])
# END VERSION CHECK

# end
