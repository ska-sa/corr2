# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
@author: paulp
"""

import logging
LOGGER = logging.getLogger(__name__)

from engine import Engine


class Xengine(Engine):
    """
    A Cross-correlation (X) Engine.
    X-engines cross multiply a subset of channels from a number of fengines and accumulate the result
    """
    def __init__(self, host_device, engine_id):
        """
        """
        super(Xengine, self).__init__(host_device, engine_id)

        # check that we have all the required attributes for an f-engine
        assert hasattr(self, 'vacc_len'), 'x-engine must have a vector accumulator length'

    def set_accumulation_length(self, accumuluation_length, issue_meta=True):
        """ Set the accumulation time for the vector accumulator
        @param accumulation_length: the accumulation time in spectra
        @param issue_meta: issue SPEAD meta data indicating the change in time
        @returns: the actual accumulation time in spectra
        """
        raise NotImplementedError
    
    def get_accumulation_length(self):
        """ Get the current accumulation time of the vector accumulator
        @returns: the accumulation time in spectra
        """
        raise NotImplementedError

# end
