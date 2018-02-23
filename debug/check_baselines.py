#!/usr/bin/env python

import IPython
from corr2 import fxcorrelator
from corr2 import corr_rx
import time
import os
import logging

logging.basicConfig(level=eval('logging.INFO'))

rxer = corr_rx.CorrRx()
time.sleep(0.5)
rxer.start()


def stop_rx():
    print('Stopping receiver'
    rxer.stop()
    rxer.join()


def start_corr():
    print('Creating correlator and issuing metadata',
    try:
        correlator = fxcorrelator.FxCorrelator('corr',
                                               config_source=os.environ['CORR2INI'],
                                               log_level=eval('logging.INFO'))
        correlator.initialise(program=True)
        correlator.spead_issue_meta()
        correlator.xops.tx_enable()
    except:
        raise RuntimeError('Error trying to do that. Bailing.')
    print('Done starting correlator'
    return correlator

ant_names = []
for ctr in range(0, 4):
    ant_names.append('ant%i_x' % ctr)
    ant_names.append('ant%i_y' % ctr)

ZEROES_ALLOWED = int(4096*0.7)
CORR_INIT_LOOPS = 1
CORR_INIT_RETRIES = 5
DATA_TO_GET = 100
EXPECTED_TIMESTEP = 8192
EXPECTED_NACC = 816

try:

    corr_init_failed = 0
    main_loop_ctr = 0
    error_log = []
    while main_loop_ctr < CORR_INIT_LOOPS:

        tic = time.time()

        corr_init_attempts = 0
        c = None
        while corr_init_attempts < CORR_INIT_RETRIES:
            try:
                c = start_corr()
                break
            except:
                corr_init_failed += 1
                corr_init_attempts += 1
        if corr_init_attempts == CORR_INIT_RETRIES:
            stop_rx()
            print('corr_init_failed: ', corr_init_failed
            print('Failed too many times initialising the correlator'
            IPython.embed()
        baselines = c.xops.get_baseline_order()
        for ant in ant_names:
            print('Setting antenna %s to non-zero quantiser' % ant
            c.fops.eq_set(new_eq=0)
            c.fops.eq_set(source_name=ant, new_eq=300)
            # print(fxcorrelator_fengops.feng_eq_get(c)
            # find the autocorrelation
            auto_index = -1
            for ctr, bls in enumerate(baselines):
                if bls[0] == ant and bls[1] == ant:
                    auto_index = ctr
                    break
            if auto_index == -1:
                stop_rx()
                print('corr_init_failed: ', corr_init_failed
                raise RuntimeError('Could not match %s to baseine auto' % ant)
            print('\tMatched to baseline %i' % auto_index
            expected_baselines = [auto_index]

            print('\tWaiting for clean dumps'
            rxer.get_clean_dump(5, discard=4)

            # ig = rxer.data_queue.get()
            # stop_rx()
            # IPython.embed()

            # get some data and check it's in the correct place
            print('\tGetting %i heaps' % DATA_TO_GET
            cnt = 0
            lasttime = None
            got_error = False
            while cnt < DATA_TO_GET:
                ig = rxer.data_queue.get()
                if lasttime is not None:
                    timediff = ig['timestamp'] - lasttime
                    if timediff != (256 * EXPECTED_NACC * EXPECTED_TIMESTEP):
                        print('ERROR: timestamp not increasing correctly, diff was %i' % timediff
                        error_log.append('%.3f ant(%s) timestamp increment wrong - %i' %
                                         (time.time(), ant, timediff))
                        got_error = True
                lasttime = ig['timestamp']
                zeroes = ZEROES_ALLOWED
                for fchan in ig['xeng_raw']:
                    blscnt = 0
                    for bls in fchan:
                        bls_cplx = complex(bls[0], bls[1])
                        if blscnt in expected_baselines:
                            if bls_cplx == 0:
                                # allow some zeroes, cos there will be some
                                if zeroes > 0:
                                    zeroes -= 1
                                else:
                                    print('ERROR: expected non-zero data in baseline %i, got zero' % blscnt
                                    error_log.append('%.3f ant(%s) bls(%i) - expected non-zero, got zero' %
                                                     (time.time(), ant, blscnt))
                                    got_error = True
                        else:
                            if bls_cplx != 0:
                                print('ERROR: expected zero data in baseline %i, got non-zero' % blscnt
                                error_log.append('%.3f ant(%s) bls(%i) - expected zero, got non-zero' %
                                                 (time.time(), ant, blscnt))
                                got_error = True
                        blscnt += 1
                    # if got_error:
                    #     print('corr_init_failed: ', corr_init_failed
                    #     stop_rx()
                    #     IPython.embed()
                    #     raise RuntimeError('BAILING ON ERROR - see above')
                print('\t', cnt, 'ig@%i' % lasttime, 'okay'
                cnt += 1
        main_loop_ctr += 1
    stop_rx()
except KeyboardInterrupt:
    stop_rx()

print('corr_init_failed: ', corr_init_failed
if len(error_log) > 0:
    print('got some errors, check them out'
    IPython.embed()
else:
    print('All okay'
