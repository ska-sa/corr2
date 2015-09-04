__author__ = 'paulp'

"""
Test that baseline products are in the correct place directly
after the x-engine.

Zero all inputs bar one, then check for non-zero data in
the set of baseline products.

Assumes a running source and a CORR2INI environment variable
pointing at the correct config file.
"""

from corr2 import fxcorrelator_fengops
from corr2 import fxcorrelator_xengops
from corr2 import fxcorrelator
from corr2 import corr_rx
import time
import os
import logging

logging.basicConfig(level=eval('logging.INFO'))

USE_XENGINE = 0
NUM_BLS = 40
ZEROES_ALLOWED = int(4096*0.7)
CORR_INIT_LOOPS = 1
CORR_INIT_RETRIES = 5
DATA_TO_GET = 2
EXPECTED_TIMESTEP = 8192
EXPECTED_NACC = 816


def get_snap_data(correlator):
    """
    Get snap data from the chosen x-engine
    :return:
    """
    sd = correlator.x_hosts[USE_XENGINE].snapshots.snap_xeng0_ss.read()['data']
    snaplen = len(sd['pol0'])
    rd = []
    bls_ctr = 0
    this_freq = []
    freq_rx = 0
    for dctr in range(0, snaplen):
        dcplx = complex(sd['pol0'][dctr], sd['pol1'][dctr])
        this_freq.append(dcplx)
        bls_ctr += 1
        if bls_ctr == NUM_BLS:
            bls_ctr = 0
            rd.append(this_freq)
            this_freq = []
            freq_rx += 1
    print 'got', freq_rx, 'frequencies from a snapshot', snaplen, 'words long'
    return rd


def start_corr():
    print 'Creating correlator and issuing metadata',
    try:
        correlator = fxcorrelator.FxCorrelator('corr',
                                               config_source=os.environ['CORR2INI'],
                                               log_level=eval('logging.INFO'))
        correlator.initialise(program=True)
        correlator.spead_issue_meta()
        fxcorrelator_xengops.tx_enable(correlator)
    except:
        raise RuntimeError('Error trying to do that. Bailing.')
    print 'Done starting correlator'
    return correlator


def match_inputs_to_baselines(baselines, active_inputs):
    """
    Which baselines should be non-zero given these active inputs
    :param baselines:
    :param active_inputs:
    :return:
    """
    matched_baselines = []
    for blsctr, baseline in enumerate(baselines):
        if (baseline[0] in active_inputs) and (baseline[1] in active_inputs):
            matched_baselines.append(blsctr)

    print active_inputs
    for ctr, bls in enumerate(baselines):
        print ctr, bls, 'MATCHED' if ctr in matched_baselines else ''

    return matched_baselines

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
        corr_init_attempts = 0
        corr_obj = None
        while corr_init_attempts < CORR_INIT_RETRIES:
            try:
                corr_obj = start_corr()
                break
            except:
                corr_init_failed += 1
                corr_init_attempts += 1
        if corr_init_attempts >= CORR_INIT_RETRIES:
            print 'corr_init_failed: ', corr_init_failed
            print 'Failed too many times initialising the correlator'
            import IPython
            IPython.embed()
        baselines = fxcorrelator_xengops.xeng_get_baseline_order(corr_obj)
        active_inputs = []

        # set all the inputs to zero
        fxcorrelator_fengops.feng_eq_set(corr_obj, new_eq=0)

        for ant in ant_names:
            print 'Setting antenna %s to non-zero quantiser' % ant
            fxcorrelator_fengops.feng_eq_set(corr_obj, source_name=ant, new_eq=300)
            active_inputs.append(ant)
            expected_baselines = match_inputs_to_baselines(baselines, active_inputs)
            if len(expected_baselines) == 0:
                print 'corr_init_failed: ', corr_init_failed
                print baselines
                print active_inputs
                print expected_baselines
                raise RuntimeError('Active inputs not matched in baseline list?!')
            print 'Active inputs:', active_inputs
            print 'Matched baseline indices:', expected_baselines

            # # find the autocorrelation
            # auto_index = -1
            # for ctr, bls in enumerate(baselines):
            #     if bls[0] == ant and bls[1] == ant:
            #         auto_index = ctr
            #         break
            # if auto_index == -1:
            #     stop_rx()
            #     print 'corr_init_failed: ', corr_init_failed
            #     raise RuntimeError('Could not match %s to baseine auto' % ant)
            # print '\tMatched to baseline %i' % auto_index
            # expected_baselines = [auto_index]

            # get some data and check it's in the correct place
            print '\tGetting %i heaps' % DATA_TO_GET
            data_cnt = 0
            while data_cnt < DATA_TO_GET:
                snapdata = get_snap_data(corr_obj)
                zeroes = ZEROES_ALLOWED
                got_error = False
                for fcnt, fchan in enumerate(snapdata):
                    blscnt = 0
                    for bls_cplx in fchan:
                        if blscnt in expected_baselines:
                            if bls_cplx == 0:
                                # allow some zeroes, cos there will be some
                                if zeroes > 0:
                                    zeroes -= 1
                                else:
                                    print 'ERROR: expected non-zero data in baseline %i, got zero' % blscnt
                                    error_log.append('%.3f ants(%s) bls(%i) - expected non-zero, got zero' %
                                                     (time.time(), active_inputs, blscnt))
                                    got_error = True
                        else:
                            if bls_cplx != 0:
                                print 'ERROR: expected zero data in baseline %i, got non-zero' % blscnt
                                error_log.append('%.3f ants(%s) bls(%i) - expected zero, got non-zero' %
                                                 (time.time(), active_inputs, blscnt))
                                got_error = True
                        blscnt += 1
                if got_error:
                    print '\t', data_cnt, 'freq@%i' % fcnt, 'errors present, check log on completion'
                else:
                    print '\t', data_cnt, 'freq@%i' % fcnt, 'okay'
                data_cnt += 1
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
    import IPython
    IPython.embed()
else:
    print 'All okay.'
