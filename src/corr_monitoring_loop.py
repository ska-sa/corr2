"""
Created: April 2018

Author: tyronevb
"""

import time
from tornado.ioloop import IOLoop
from tornado.ioloop import PeriodicCallback
from tornado.locks import Event as IOLoopEvent


class MonitoringLoop(object):
    def __init__(self, check_time, fx_correlator_object):

        self.instrument = fx_correlator_object
        self.fhosts = self.instrument.fhosts
        self.fhost_index = 0
        self.num_fhosts = len(self.fhosts)

        if check_time == -1:
            self.check_time = float(self.instrument.configd['FxCorrelator']['monitor_loop_time'])
        else:
            self.check_time = check_time

        # set up periodic engine monitoring
        self.instrument_monitoring_loop_enabled = IOLoopEvent()
        self.instrument_monitoring_loop_enabled.clear()
        self.instrument_monitoring_loop_cb = None
        self.f_eng_board_monitoring_dict_prev = {}

        self.disabled_boards = []

    def start(self):
        """
        Start the monitoring loop
        :return: none
        """
        self._instrument_monitoring_loop_timer_start(check_time=self.check_time)

    def stop(self):
        """
        Stop the monitoring loop
        :return: none
        """
        self._instrument_monitoring_loop_timer_stop()

    def _instrument_monitoring_loop_timer_start(self, check_time=None):
        """
        Set up periodic check of various instrument elements
        :param check_time: the interval, in seconds, at which to check
        :return:
        """

        if not IOLoop.current()._running:
            raise RuntimeError('IOLoop not running, this will not work')

        self.instrument.logger.info('instrument_monitoring_loop for instrument %s '
                                    'set up with a period '
                                    'of %i seconds' % (self.instrument.descriptor, self.check_time))

        if self.instrument_monitoring_loop_cb is not None:
            self.instrument_monitoring_loop_cb.stop()
        self.instrument_monitoring_loop_cb = PeriodicCallback(
            self._instrument_monitoring_loop, check_time * 1000)

        self.instrument_monitoring_loop_enabled.set()
        self.instrument_monitoring_loop_cb.start()
        self.instrument.logger.info('Instrument Monitoring Loop Timer '
                                    'Started @ '
                         '%s' % time.ctime())

    def _instrument_monitoring_loop_timer_stop(self):
        """
        Disable the periodic instrument monitoring loop
        :return:
        """

        if self.instrument_monitoring_loop_cb is not None:
            self.instrument_monitoring_loop_cb.stop()
        self.instrument_monitoring_loop_cb = None
        self.instrument_monitoring_loop_enabled.clear()
        self.instrument.logger.info('Instrument Monitoring Loop Timer Halted @ '
                         '%s' % time.ctime())

    # TODO: use functools to pass this callback function with parameters
    def _instrument_monitoring_loop(self, corner_turner_check=True,
                                    coarse_delay_check=True,
                                    vacc_check=False):
        """
        Perform various checks periodically.
        :param corner_turner_check: enable periodic checking of the corner-
        turner; will disable F-engine output on overflow
        :param coarse_delay_check: enable periodic checking of the coarse
        delay
        :param vacc_check: enable periodic checking of the vacc
        turner
        :return:
        """

        # TODO: x-eng checks
        '''
        vacc out of sync but errors - stop xeng output
        vacc out of sync no errors - resync vacc
        '''

        # choose a new board
        fhost = self.fhosts[self.fhost_index]
        f_eng_board_monitoring_dict_current = {}
        status = {}

        # check ct & cd
        if corner_turner_check:
            # perform corner-turner check
            ct_status = fhost.get_ct_status()
            status['corner_turner'] = ct_status
        if coarse_delay_check:
            # perform coarse delay check
            cd_status = fhost.get_cd_status()
            status['coarse_delay'] = cd_status

        # perform vacc check
        if vacc_check:

            raise NotImplementedError("Periodic vacc check not yet "
                                      "implemented")

        # populate status dictionaries
        f_eng_board_monitoring_dict_current[fhost] = status
        action = {'disable_output': 0,
                  'reenable_output': 0}

        # check error counters
        if len(self.f_eng_board_monitoring_dict_prev) == self.num_fhosts:
            coarse_delay_action = self._check_feng_coarse_delay_errs(
                f_eng_board_monitoring_dict_current[fhost], fhost)

            corner_turner_action = self._check_feng_corner_turn_errs(
                f_eng_board_monitoring_dict_current[fhost], fhost)

            # consolidate the action dictionary - only reenable if all
            # errors are cleared
            if coarse_delay_action['disable_output'] or corner_turner_action[
                'disable_output']:
                action['disable_output'] = True
            elif coarse_delay_action['reenable_output'] or \
                    corner_turner_action['reenable_output']:
                action['reenable_output'] = True

            # take appropriate action on board
            if action['disable_output']:
                # keep track of which boards have been disabled
                if fhost not in self.disabled_boards:
                    self.disabled_boards.append(fhost)
                    self._disable_feng_ouput(fhost=fhost)

            if action['reenable_output']:
                # after checking, we already know that this board was
                # disabled prior
                self._renable_feng_output(fhost=fhost)
                # remove the board from the list of disabled boards
                self.disabled_boards.remove(fhost)
            else:
                if self.disabled_boards:
                    self.instrument.logger.warning('instrument monitor loop '
                                                   'run ok - no new errs, '
                                                   'some f-engines still '
                                                   'disabled: %s' % [
                                                    fhost.host for fhost in
                                                    self.disabled_boards])
                else:
                    self.instrument.logger.info(
                        'instrument monitor loop run ok - no errs')
                    # self.instrument.logger.info(
                    #    'checked board {}'.format(fhost.host))

        # increment board counter, move to the next board the next time loop runs
        if self.fhost_index == self.num_fhosts - 1:
            self.fhost_index = 0
        else:
            self.fhost_index += 1

        # store the previous board status, used to check next time the board status is queries
        self.f_eng_board_monitoring_dict_prev[fhost] = \
            f_eng_board_monitoring_dict_current[fhost]

    def _check_feng_coarse_delay_errs(self, f_eng_status_dict, fhost):
        """
        Check f-engines for any coarse delay errors
        :return:
        """
        action_dict = {'disable_output': False, 'reenable_output': False}

        if f_eng_status_dict.has_key('coarse_delay'):

            cd_dict = f_eng_status_dict['coarse_delay']
            # flags
            if not cd_dict['hmc_init']:
                self.instrument.logger.warning(
                    'fhost %s coarse delay has hmc init errors' %
                    fhost.host)
                action_dict['disable_output'] = True

            if not cd_dict['hmc_post']:
                self.instrument.logger.warning('fhost %s coarse delay '
                                               'has hmc post '
                                               'errors' %
                                               fhost.host)
                action_dict['disable_output'] = True

                # check error counters, first check if a previous status
                # dict exists

            if self.f_eng_board_monitoring_dict_prev:
                cd_dict_prev = \
                    self.f_eng_board_monitoring_dict_prev[fhost][
                        'coarse_delay']
                # check error counters
                if cd_dict['reord_jitter_err_cnt_pol0'] != cd_dict_prev[
                    'reord_jitter_err_cnt_pol0'] or cd_dict[ \
                        'reord_jitter_err_cnt_pol1'] != cd_dict_prev[
                    'reord_jitter_err_cnt_pol1']:
                    self.instrument.logger.warning(
                        'fhost %s coarse delay has reorder jitter errors' %
                        fhost.host)
                    action_dict['disable_output'] = True
                if cd_dict['hmc_overflow_err_cnt_pol0'] != cd_dict_prev[
                    'hmc_overflow_err_cnt_pol0'] or cd_dict[
                    'hmc_overflow_err_cnt_pol1'] != cd_dict_prev[
                    'hmc_overflow_err_cnt_pol1']:
                    self.instrument.logger.warning('fhost %s coarse '
                                                   'delay has '
                                                   'overflow errors' %
                                                   fhost.host)
                    action_dict['disable_output'] = True

        # if no errors, check if board was disabled, then flag for reenable
        if not action_dict['disable_output']:
            # no errors detected, no need to disable any boards
            # but was the board previously disabled?
            if fhost in self.disabled_boards:
                # the errors on the board have been cleared
                action_dict['reenable_output'] = True

        return action_dict

    def _check_feng_corner_turn_errs(self, f_eng_status_dict, fhost):
        """
        Check f-engines for any corner-turner errors

        :return:
        """

        action_dict = {'disable_output': False, 'reenable_output': False}

        if f_eng_status_dict.has_key('corner_turner'):

            ct_dict = f_eng_status_dict['corner_turner']
            # flags
            if not ct_dict['hmc_init_pol0'] or not ct_dict['hmc_init_pol1']:
                self.instrument.logger.warning('fhost %s corner-turner '
                                               'has hmc '
                                               'init errors' %
                                               fhost.host)
                action_dict['disable_output'] = True
            if not ct_dict['hmc_post_pol0'] or not ct_dict['hmc_post_pol1']:
                self.instrument.logger.warning('fhost %s corner-turner '
                                               'has hmc post '
                                               'errors' %
                                               fhost.host)
                action_dict['disable_output'] = True

            # check error counters, first check if a previous status
            # dict exists
            if self.f_eng_board_monitoring_dict_prev:
                ct_dict_prev = self.f_eng_board_monitoring_dict_prev[fhost][
                    'corner_turner']
                # check error counters
                if ct_dict['bank_err_cnt_pol0'] != ct_dict_prev[
                    'bank_err_cnt_pol0'] or ct_dict[ \
                        'bank_err_cnt_pol1'] != ct_dict_prev[
                    'bank_err_cnt_pol1']:
                    self.instrument.logger.warning('fhost %s '
                                                   'corner-turner has bank errors' %
                                                   fhost.host)
                    action_dict['disable_output'] = True
                if ct_dict['fifo_full_err_cnt'] != ct_dict_prev[
                    'fifo_full_err_cnt']:
                    self.instrument.logger.warning('fhost %s '
                                                   'corner-turner has fifo full '
                                                   'errors' % fhost.host)
                    action_dict['disable_output'] = True
                if ct_dict['rd_go_err_cnt'] != ct_dict_prev['rd_go_err_cnt']:
                    self.instrument.logger.warning('fhost %s '
                                                   'corner-turner has read go '
                                                   'errors' % fhost.host)
                    action_dict['disable_output'] = True
                if ct_dict['obuff_bank_err_cnt'] != ct_dict_prev[
                    'obuff_bank_err_cnt']:
                    self.instrument.logger.warning('fhost %s '
                                                   'corner-turner has '
                                                   'obuff errors' % fhost.host)
                    action_dict['disable_output'] = True
                if ct_dict['hmc_overflow_err_cnt_pol0'] != ct_dict_prev[
                    'hmc_overflow_err_cnt_pol0'] or ct_dict[
                    'hmc_overflow_err_cnt_pol1'] != ct_dict_prev[
                    'hmc_overflow_err_cnt_pol1']:
                    self.instrument.logger.warning('fhost %s '
                                                   'corner-turner has '
                                                   'overflow errors' %
                                                   fhost.host)
                    action_dict['disable_output'] = True

        # if no errors, check if board was disabled, then flag for reenable
        if not action_dict['disable_output']:
            # no errors detected, no need to disable any boards
            # but was the board previously disabled?
            if fhost in self.disabled_boards:
                # the errors on the board have been cleared
                action_dict['reenable_output'] = True

        return action_dict

    def _disable_feng_ouput(self, fhost):
        """
        Disables the output from an f-engine
        :param fhost: the host board with f-engines to disable
        :return:
        """

        fhost.tx_disable()
        self.instrument.logger.warning('feng %s output disabled!' %
                                       fhost.host)

    def _renable_feng_output(self, fhost):
        """
        Reenables the output from an f-engine
        :param fhost: the host board with f-engines to reenable
        :return:
        """

        fhost.tx_enable()
        self.instrument.logger.info('feng %s output reenabled!' %
                                    fhost.host)

# end
