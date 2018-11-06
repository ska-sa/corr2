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
        self.hosts = self.instrument.fhosts + self.instrument.xhosts
        self.selected_host = None
        self.host_index = 0
        self.num_hosts = len(self.hosts)
        self.num_fhosts = len(self.instrument.fhosts)
        self.num_xhosts = len(self.instrument.xhosts)
        # self.num_bhosts = len(self.instrument.bhosts)

        # check config file if bhosts or xhosts

        if check_time == -1:
            self.check_time = float(self.instrument.configd['FxCorrelator']['monitor_loop_time'])
        else:
            self.check_time = check_time

        # set up periodic engine monitoring
        self.instrument_monitoring_loop_enabled = IOLoopEvent()
        self.instrument_monitoring_loop_enabled.clear()
        self.instrument_monitoring_loop_cb = None

        self.f_eng_board_monitoring_dict_prev = {}
        self.x_eng_board_monitoring_dict_prev = {}
        self.b_eng_board_monitoring_dict_prev = {}

        self.disabled_fhosts = []
        self.disabled_xhosts = []
        self.disabled_bhosts = []

        # some other useful bits of info
        self.n_chans = self.instrument.n_chans
        self.n_xengs_per_host = self.instrument.x_per_fpga
        self.n_per_xeng = self.n_chans/(self.n_xengs_per_host*self.num_xhosts)

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
                                    'of %.2f seconds' % (self.instrument.descriptor, self.check_time))

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
    def _instrument_monitoring_loop(self, check_fhosts=True, check_xhosts=True, check_bhosts=False):
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

        # TODO: refactor this to handle checking of all host types
        # TODO: run all tests on everything?
        # TODO: figure out how to selectively test pieces
        # select a new host
        host = self.hosts[self.host_index]
        board_monitoring_dict_current = {}

        # check host type
        if host.host_type == 'fhost':
            if check_fhosts:
                board_monitoring_dict_current[host] = self._get_fhost_status(host=host)

                # check error counters if all fhosts have status
                if len(self.f_eng_board_monitoring_dict_prev) == self.num_fhosts:
                    self._check_fhost_errors(board_monitoring_dict_current, host)

                self.f_eng_board_monitoring_dict_prev[host] = \
                    board_monitoring_dict_current[host]

        elif host.host_type == 'xhost' or host.host_type == 'bhost':
            if check_xhosts:
                board_monitoring_dict_current[host] = self._get_xhost_status(host=host)

                # check errs if all xhosts have status
                if len(self.x_eng_board_monitoring_dict_prev) == self.num_xhosts:
                    self._check_xhost_errors(board_monitoring_dict_current, host)

                self.x_eng_board_monitoring_dict_prev[host] = \
                    board_monitoring_dict_current[host]

        # TODO: how to handle bhosts and xhosts?
        elif host.host_type == 'bhost':
            if check_bhosts:
                pass

        # increment board counter, move to the next board the next time
        # loop runs

        if self.host_index == self.num_hosts - 1:
            if not self.disabled_fhosts and not self.disabled_xhosts and not self.disabled_bhosts:
                self.instrument.logger.info('Monitoring loop run ok. All hosts checked - no hosts disabled')
            else:
                self.instrument.logger.warning(
                    'Monitoring loop run ok. All hosts checked - some hosts disabled')
            self.host_index = 0
        else:
            self.host_index += 1

        if self.disabled_fhosts:
            self.instrument.logger.warning('corr2 monitor loop: disabled f-hosts: %s' % [
                'fhost%d:%s:%s' % (disabled_fhost.fhost_index, disabled_fhost.host, [feng.input.name for feng in disabled_fhost.fengines]) for disabled_fhost in self.disabled_fhosts])

        if self.disabled_xhosts:
            self.instrument.logger.warning('corr2 monitor loop: disabled x-hosts: %s'
                                           % ['xhost%d:%s:%d-%d' % (disabled_xhost.index, disabled_xhost.host, self.instrument.xops.board_ids[disabled_xhost.host]*self.n_per_xeng,
                                                                             (self.instrument.xops.board_ids[disabled_xhost.host]+1)*self.n_per_xeng-1)
                                                                             for disabled_xhost in self.disabled_xhosts])

        #if self.disabled_bhosts:
        #    self.instrument.logger.warning('corr2 monitor loop: disabled b-hosts: %s' % [
        #        '%d:%s' % (disabled_bhost.index, disabled_bhost.host) for disabled_bhost in self.disabled_bhosts])

        return True

    def _get_fhost_status(self, host, corner_turner_check=True,
                          coarse_delay_check=True, rx_reorder_check=True):
        """
        Checks the f-hosts for errors

        :return:
        """
        status = {}
        # check ct & cd
        if corner_turner_check:
            # perform corner-turner check
            ct_status = host.get_ct_status()
            status['corner_turner'] = ct_status
        if coarse_delay_check:
            # perform coarse delay check
            cd_status = host.get_cd_status()
            status['coarse_delay'] = cd_status

        # check feng rx reorder
        if rx_reorder_check:
            feng_rx_reorder_status = host.get_rx_reorder_status()
            status['feng_rx_reorder'] = feng_rx_reorder_status

        return status

    def _check_fhost_errors(self, board_monitoring_dict_current, host):
        """

        :param board_monitoring_dict_current:
        :param host:
        :return:
        """
        action = {'disable_output': 0,
                  'reenable_output': 0}

        coarse_delay_action = self._check_feng_coarse_delay_errs(
            board_monitoring_dict_current[host], host)

        corner_turner_action = self._check_feng_corner_turn_errs(
            board_monitoring_dict_current[host], host)

        rx_reorder_action = self._check_feng_rx_reorder_errs(
            board_monitoring_dict_current[host], host)

        # consolidate the action dictionary - only reenable if all
        # errors are cleared
        if coarse_delay_action['disable_output'] \
                or corner_turner_action['disable_output'] \
                or rx_reorder_action['disable_output']:
            action['disable_output'] = True
        elif coarse_delay_action['reenable_output'] \
                or corner_turner_action['reenable_output'] \
                or rx_reorder_action['reenable_output']:
            action['reenable_output'] = True
        else:
            # no action required
            pass

        # take appropriate action on board

        if action['disable_output']:
            # keep track of which boards have been disabled
            if host not in self.disabled_fhosts:
                self.disabled_fhosts.append(host)
                self._disable_feng_ouput(fhost=host)

        elif action['reenable_output']:
            # after checking, we already know that this board was
            # disabled prior
            self._renable_feng_output(fhost=host)
            # remove the board from the list of disabled boards
            self.disabled_fhosts.remove(host)
        else:
            # no action taken
            pass

    def _get_xhost_status(self, host, xeng_rx_reorder_check=False, xeng_hmc_reorder_check=True, xeng_vacc_check=True):
        """

        :param host:
        :param xeng_rx_reorder_check:
        :param xeng_hmc_reorder_check:
        :param xeng_vacc_check:
        :return:
        """

        status = {}
        # check xeng rx reorder

        if xeng_rx_reorder_check:
            xeng_rx_reorder_status = host.get_rx_reorder_status()
            status['xeng_rx_reorder'] = xeng_rx_reorder_status

        # check xeng hmc reorder
        if xeng_hmc_reorder_check:
            xeng_hmc_reorder_status = host.get_hmc_reorder_status()
            status['xeng_hmc_reorder'] = xeng_hmc_reorder_status

        # check xeng vacc
        if xeng_vacc_check:
            xeng_vacc_status = host.get_vacc_status()
            status['xeng_vacc'] = xeng_vacc_status

        return status

    def _check_xhost_errors(self, board_monitoring_dict_current, host):
        """

        :param board_monitoring_dict_current:
        :param host:
        :return:
        """
        action = {'disable_output': 0,
                  'reenable_output': 0}

        hmc_reorder_action = self._check_xeng_hmc_reorder_errs(
            board_monitoring_dict_current[host], host)

        vacc_action = self._check_xeng_vacc_errs(
            board_monitoring_dict_current[host], host)

        # consolidate the action dictionary - only reenable if all
        # errors are cleared
        if hmc_reorder_action['disable_output'] \
                or vacc_action['disable_output']:
            action['disable_output'] = True
        elif hmc_reorder_action['reenable_output'] \
                or vacc_action['reenable_output']:
            action['reenable_output'] = True
        else:
            # no action required
            pass

        # take appropriate action on board

        if action['disable_output']:
            # keep track of which boards have been disabled
            if host not in self.disabled_xhosts:
                self.disabled_xhosts.append(host)
                self._disable_xeng_ouput(xhost=host)

        elif action['reenable_output']:
            # after checking, we already know that this board was
            # disabled prior
            self._renable_xeng_output(xhost=host)
            # remove the board from the list of disabled boards
            self.disabled_xhosts.remove(host)
        else:
            # no action taken
            pass

        self.x_eng_board_monitoring_dict_prev[host] = \
            board_monitoring_dict_current[host]

    def _check_xeng_rx_reorder_errs(self, x_eng_status_dict, xhost):
        """

        :param x_eng_status_dict:
        :param xhost:
        :return:
        """
        raise NotImplementedError

    def _check_xeng_hmc_reorder_errs(self, x_eng_status_dict, xhost):
        """

        :param x_eng_status_dict:
        :param xhost:
        :return:
        """
        action_dict = {'disable_output': False, 'reenable_output': False}

        if x_eng_status_dict.has_key('xeng_hmc_reorder'):

            hmc_reorder_dict = x_eng_status_dict['xeng_hmc_reorder']

            # counters
            # check error counters, first check if a previous status
            # dict exists
            # flags
            if not hmc_reorder_dict['init_done']:
                self.instrument.logger.warning(
                    'xhost %s hmc reorder has init errors' %
                     xhost.host)
                action_dict['disable_output'] = True

            if not hmc_reorder_dict['post_ok']:
                self.instrument.logger.warning('xhost %s hmc reorder '
                                               'has post errors' % xhost.host)
                action_dict['disable_output'] = True

            # check error counters
            if self.x_eng_board_monitoring_dict_prev:
                hmc_reorder_dict_prev = \
                    self.x_eng_board_monitoring_dict_prev[xhost][
                        'xeng_hmc_reorder']

                if hmc_reorder_dict['err_cnt_link2'] != hmc_reorder_dict_prev[
                    'err_cnt_link2']:

                    self.instrument.logger.warning(
                        'xhost %s hmc reorder has errors on link 2' %
                         xhost.host)
                    action_dict['disable_output'] = True
                if hmc_reorder_dict['err_cnt_link3'] != hmc_reorder_dict_prev[
                    'err_cnt_link3']:
                    self.instrument.logger.warning(
                        'xhost %s hmc reorder has errors on link 3' %
                        xhost.host)
                    action_dict['disable_output'] = True
                if hmc_reorder_dict['lnk2_nrdy_err_cnt'] != hmc_reorder_dict_prev[
                    'lnk2_nrdy_err_cnt']:
                    self.instrument.logger.warning(
                        'xhost %s hmc reorder has link 2 nrdy errors' %
                        xhost.host)
                    action_dict['disable_output'] = True
                if hmc_reorder_dict['lnk3_nrdy_err_cnt'] != hmc_reorder_dict_prev[
                    'lnk3_nrdy_err_cnt']:
                    self.instrument.logger.warning(
                        'xhost %s hmc reorder has link 3 nrdy errors' %
                        xhost.host)
                    action_dict['disable_output'] = True
                if hmc_reorder_dict['mcnt_timeout_cnt'] != hmc_reorder_dict_prev[
                    'mcnt_timeout_cnt']:
                    self.instrument.logger.warning(
                        'xhost %s hmc reorder has mcnt timeout errors' %
                        xhost.host)
                    action_dict['disable_output'] = True
                if hmc_reorder_dict['ts_err_cnt'] != hmc_reorder_dict_prev[
                    'ts_err_cnt']:
                    self.instrument.logger.warning(
                        'xhost %s hmc reorder has timestamp errors' %
                        xhost.host)
                    action_dict['disable_output'] = True

            # if no errors, check if board was disabled, then flag for reenable
        if not action_dict['disable_output']:
            # no errors detected, no need to disable any boards
            # but was the board previously disabled?
            if xhost in self.disabled_xhosts:
                # the errors on the board have been cleared
                action_dict['reenable_output'] = True

        return action_dict

    def _check_xeng_vacc_errs(self, x_eng_status_dict, xhost):
        """

        :param x_eng_status_dict:
        :param xhost:
        :return:
        """
        action_dict = {'disable_output': False, 'reenable_output': False}

        if x_eng_status_dict.has_key('xeng_vacc'):

            vacc_dict = x_eng_status_dict['xeng_vacc']

            # counters
            # check error counters, first check if a previous status
            # dict exists

            # check error counters
            if self.x_eng_board_monitoring_dict_prev:
                vacc_dict_prev = \
                    self.x_eng_board_monitoring_dict_prev[xhost][
                        'xeng_vacc']

                for vacc in range(len(vacc_dict)):
                    # there are four vaccs per xhost

                    if vacc_dict[vacc]['err_cnt'] != vacc_dict_prev[vacc]['err_cnt']:
                        self.instrument.logger.warning(
                            'xhost %s vacc has errors' %
                            xhost.host)
                        action_dict['disable_output'] = True

            # if no errors, check if board was disabled, then flag for reenable
        if not action_dict['disable_output']:
            # no errors detected, no need to disable any boards
            # but was the board previously disabled?
            if xhost in self.disabled_xhosts:
                # the errors on the board have been cleared
                action_dict['reenable_output'] = True

        return action_dict

    def _check_feng_rx_reorder_errs(self, f_eng_status_dict, fhost):
        """

        :param f_eng_status_dict:
        :param fhost:
        :return:
        """
        action_dict = {'disable_output': False, 'reenable_output': False}

        if f_eng_status_dict.has_key('feng_rx_reorder'):

            rx_reorder_dict = f_eng_status_dict['feng_rx_reorder']

            # counters
            # check error counters, first check if a previous status
            # dict exists

            if self.f_eng_board_monitoring_dict_prev:
                rx_reorder_dict_prev = \
                    self.f_eng_board_monitoring_dict_prev[fhost][
                        'feng_rx_reorder']
                # check error counters
                if rx_reorder_dict['overflow_err_cnt'] != rx_reorder_dict_prev[
                    'overflow_err_cnt']:
                    self.instrument.logger.warning(
                        'fhost %s rx reorder has overflow errors' %
                        fhost.host)
                    action_dict['disable_output'] = True
                if rx_reorder_dict['receive_err_cnt'] != rx_reorder_dict_prev[
                    'receive_err_cnt']:
                    self.instrument.logger.warning(
                        'fhost %s rx reorder has receive errors' %
                        fhost.host)
                    action_dict['disable_output'] = True
                if rx_reorder_dict['relock_err_cnt'] != rx_reorder_dict_prev[
                    'relock_err_cnt']:
                    self.instrument.logger.warning(
                        'fhost %s rx reorder has relock errors' %
                        fhost.host)
                    action_dict['disable_output'] = True
                if rx_reorder_dict['timestep_err_cnt'] != rx_reorder_dict_prev[
                                                            'timestep_err_cnt']:
                    self.instrument.logger.warning(
                        'fhost %s rx reorder has timestep errors' %
                        fhost.host)
                    action_dict['disable_output'] = True

            # if no errors, check if board was disabled, then flag for reenable
        if not action_dict['disable_output']:
            # no errors detected, no need to disable any boards
            # but was the board previously disabled?
            if fhost in self.disabled_fhosts:
                # the errors on the board have been cleared
                action_dict['reenable_output'] = True

        return action_dict

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
                    'reord_jitter_err_cnt_pol0'] or cd_dict[
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
            if fhost in self.disabled_fhosts:
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
            if fhost in self.disabled_fhosts:
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
        self.instrument.logger.warning('fhost%d %s %s output disabled!' %
                                       (fhost.fhost_index,
                                        fhost.host,
                                        [feng.input.name for feng in fhost.fengines]
                                        ))

    def _renable_feng_output(self, fhost):
        """
        Reenables the output from an f-engine
        :param fhost: the host board with f-engines to reenable
        :return:
        """

        fhost.tx_enable()
        self.instrument.logger.info('fhost%d %s %s output reenabled!' %
                                    (fhost.fhost_index,
                                     fhost.host,
                                     [feng.input.name for feng in
                                      fhost.fengines]
                                     ))

    def _disable_xeng_ouput(self, xhost):
        """
        Disables the output from an f-engine
        :param xhost: the host board with f-engines to disable
        :return:
        """

        xhost.registers.control.write(gbe_txen=False)
        self.instrument.logger.warning('xhost%d %s %s output disabled!' %
                                      (xhost.index, xhost.host,
                                      (self.instrument.xops.board_ids[xhost.host] * self.n_per_xeng,
                                      (self.instrument.xops.board_ids[xhost.host] + 1) * self.n_per_xeng - 1)
                                      ))

    def _renable_xeng_output(self, xhost):
        """
        Reenables the output from an f-engine
        :param xhost: the host board with f-engines to reenable
        :return:
        """

        xhost.registers.control.write(gbe_txen=True)
        self.instrument.logger.info('xhost%d %s %s output reenabled!' %
                                    (xhost.index, xhost.host,
                                     (self.instrument.xops.board_ids[
                                          xhost.host] * self.n_per_xeng,
                                      (self.instrument.xops.board_ids[
                                           xhost.host] + 1) * self.n_per_xeng - 1)
                                     ))

    def get_bad_fhosts(self):
        """
        Returns a list of bad known fhosts that are currently disables
        :return: list of bad fhosts (hostnames)
        """

        return self.disabled_fhosts

    def get_bad_xhosts(self):
        """
        Returns a list of bad known xhosts that are currently disables
        :return: list of bad xhosts (hostnames)
        """

        return self.disabled_xhosts

    def get_bad_bhosts(self):
        """
        Returns a list of bad known bhosts that are currently disables
        :return: list of bad bhosts (hostnames)
        """

        return self.disabled_bhosts

# end
