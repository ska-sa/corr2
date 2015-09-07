__author__ = 'paulp'

"""
Test the incoming data from the f-engines. If we set the EQs,
are the correct f-engines zeroed?

Assumes a running source and a CORR2INI environment variable
pointing at the correct config file.
"""

from corr2 import fxcorrelator_fengops
from corr2 import fxcorrelator
import time
import os
import logging
import IPython
import sys

logging.basicConfig(level=eval('logging.INFO'))

USE_XENGINE = 0
CORR_INIT_LOOPS = 1
CORR_INIT_RETRIES = 5
FREQ_TO_CHECK = 128
SNAP_LEN_BYTES = 8192
EXPECTED_FREQ = 123


def get_snap_data(correlator, byte_offset=0):
    """
    Get snap data from the chosen x-engine
    :return:
    """
    sd = correlator.xhosts[USE_XENGINE].snapshots.snap_quant0_ss.read(offset=byte_offset)['data']
    return sd


def start_corr():
    print 'Creating correlator and issuing metadata',
    try:
        correlator = fxcorrelator.FxCorrelator('corr',
                                               config_source=os.environ['CORR2INI'],
                                               log_level=eval('logging.INFO'))
        correlator.initialise(program=False)
    except:
        raise RuntimeError('Error trying to do that. Bailing.')
    print 'Done starting correlator'
    return correlator


def init_correlator():
    corr_init_attempts = 0
    failcount = 0
    _corr_obj = None
    while corr_init_attempts < CORR_INIT_RETRIES:
        try:
            _corr_obj = start_corr()
            break
        except:
            failcount += 1
            corr_init_attempts += 1
    if corr_init_attempts >= CORR_INIT_RETRIES:
        print 'failcount: ', failcount
        print 'Failed too many times initialising the correlator'
        IPython.embed()
    return _corr_obj, failcount


ant_names = []
for ctr in range(0, 4):
    ant_names.append('ant%i_x' % ctr)
    ant_names.append('ant%i_y' % ctr)

try:
    corr_init_failed = 0
    main_loop_ctr = 0
    error_log = []
    while main_loop_ctr < CORR_INIT_LOOPS:
        tic = time.time()
        corr_obj, failcount = init_correlator()
        corr_init_failed += failcount

        # set all the inputs to zero and check all received data is zero
        fxcorrelator_fengops.feng_eq_set(corr_obj, new_eq=0)
        print 'Running for %i freqs:' % FREQ_TO_CHECK,
        for freq in range(0, FREQ_TO_CHECK):
            print freq,
            sys.stdout.flush()
            offset = freq * SNAP_LEN_BYTES
            snapdata = get_snap_data(corr_obj, byte_offset=offset)
            first_time = snapdata['mcnt27'][0]
            error = False
            for ctr in range(0, len(snapdata['r0'])):
                if first_time != snapdata['mcnt27'][ctr]:
                    print 'The time varied INSIDE a window, not right'
                    error = True
                if snapdata['r0'][ctr] != 0:
                    print 'p0 data not zero?'
                    error = True
                if snapdata['r1'][ctr] != 0:
                    print 'p1 data not zero?'
                    error = True
            if error:
                print 'Error when EQ set to zero.'
                IPython.embed()
                raise RuntimeError('Error when EQ set to zero.')
        print 'All inputs zero for zero EQ - okay'

        eq_array = [0] * 4096
        eq_array[EXPECTED_FREQ] = 300

        for scheme in [1, 2]:
            active_inputs = []
            for ant in ant_names:
                print 'Setting antenna %s to non-zero quantiser' % ant
                if scheme == 1:
                    fxcorrelator_fengops.feng_eq_set(corr_obj, source_name=ant, new_eq=eq_array)
                    active_inputs.append(ant)
                else:
                    fxcorrelator_fengops.feng_eq_set(corr_obj, new_eq=0)
                    fxcorrelator_fengops.feng_eq_set(corr_obj, source_name=ant, new_eq=eq_array)
                    active_inputs = [ant]
                print 'Active inputs:', active_inputs

                print 'Running for %i freqs:' % FREQ_TO_CHECK,
                for freq in range(0, FREQ_TO_CHECK):
                    print freq,
                    sys.stdout.flush()
                    offset = freq * SNAP_LEN_BYTES
                    snapdata = get_snap_data(corr_obj, byte_offset=offset)
                    inputs_data = []
                    for ants in range(0, 4):
                        start_index = ants * 256
                        inputs_data.append(snapdata['r0'][start_index:start_index+256])
                        inputs_data.append(snapdata['r1'][start_index:start_index+256])
                    first_time = snapdata['mcnt27'][0]
                    for ctr in range(0, len(snapdata['mcnt27'])):
                        if snapdata['mcnt27'][ctr] != first_time:
                            print 'The time varied INSIDE a window, not right'
                            IPython.embed()
                            raise RuntimeError
                    error = False
                    for ctr, input_data in enumerate(inputs_data):
                        if ant_names[ctr] in active_inputs:
                            if sum(input_data) == 0:
                                print 'Data for input', ctr, '(%s) should not be zero - but it is' % ant_names[ctr]
                                error = True
                        else:
                            if sum(input_data) != 0:
                                print 'Data for input', ctr, '(%s) should be zero - but it is not' % ant_names[ctr]
                                error = True
                    if error:
                        print 'Error when EQ set to zero.'
                        IPython.embed()
                        raise RuntimeError('Error when EQ set to zero.')
                print ''

        main_loop_ctr += 1
        runtime_last = time.time() - tic
        runtime_remain = (CORR_INIT_LOOPS - main_loop_ctr) * runtime_last
        print 'Last loop took %.3f seconds. Test has about %.3f seconds to run.' \
              % (runtime_last, runtime_remain)
except KeyboardInterrupt:
    pass

print 'corr_init_failed: ', corr_init_failed
if len(error_log) > 0:
    print 'Got some errors, check them out.'
    IPython.embed()
else:
    print 'All okay.'
