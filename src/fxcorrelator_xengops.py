import time
import numpy
from tornado.ioloop import IOLoop

from casperfpga import utils as fpgautils
from casperfpga import tengbe

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

use_xeng_sim = False


def _xeng_vacc_check_errcheck(corr, last_values):
    """

    :param corr:
    :return: True is there are errors, False if not
    """
    logstr = '_xeng_vacc_check_errcheck: '

    def get_check_data(fpga):
        rv = {}
        for _ctr in range(0, fpga.x_per_fpga):
            rv['etim%i' % _ctr] = fpga.registers['reorderr_timeout%i' % _ctr].read()['data']['reg']
        return rv
    new_data = THREADED_FPGA_OP(corr.xhosts, timeout=5, target_function=get_check_data)

    if last_values is None:
        corr.logger.debug(logstr + 'no last value')
        return False, new_data

    for fpga in new_data:
        for ctr in range(0, corr.xhosts[0].x_per_fpga):
            reg = 'etim%i' % ctr
            if new_data[fpga][reg] != last_values[fpga][reg]:
                corr.logger.error(logstr + '%s - %s error' % (fpga, reg))
                return True, new_data

    corr.logger.debug(logstr + 'all okay')
    return False, new_data


def _xeng_vacc_check_cb(corr, last_values, vacc_check_time):
    """
    Run the vacc sync if there are errors necessitating it.
    :param corr:
    :return:
    """
    corr.logger.debug('_xeng_vacc_check_cb: ran @ %.3f' % time.time())
    result, vals = _xeng_vacc_check_errcheck(corr, last_values)
    if result:
        xeng_vacc_sync(corr)
        _, vals = _xeng_vacc_check_errcheck(corr, last_values)
    IOLoop.current().call_later(vacc_check_time, _xeng_vacc_check_cb,
                                [corr, vals, vacc_check_time], {})


def xeng_setup_vacc_check_timer(corr, vacc_check_time=10):
    """

    :param corr: the correlator instance
    :param vacc_check_time: the interval, in seconds, at which to check
    :return:
    """
    corr.logger.info('xeng_setup_vacc_check_timer: setting up the vacc check timer')
    IOLoop.current().call_later(vacc_check_time, _xeng_vacc_check_cb,
                                [corr, None, vacc_check_time], {})


def xeng_initialise(corr):
    """
    Set up x-engines on this device.
    :return:
    """
    # simulator
    if use_xeng_sim:
        THREADED_FPGA_OP(corr.xhosts, timeout=10,
                         target_function=(
                             lambda fpga_: fpga_.registers.simulator.write(en=False, rst='pulse'),))

    # disable transmission, place cores in reset, and give control register a known state
    THREADED_FPGA_OP(corr.xhosts, timeout=10,
                     target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))
    THREADED_FPGA_OP(corr.xhosts, timeout=10,
                     target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=True),))
    xeng_clear_status_all(corr)

    # set up default destination ip and port
    corr.set_stream_destination()
    corr.set_meta_destination()

    # set up the 10gbe cores
    xeng_port = int(corr.configd['xengine']['10gbe_port'])
    mac_start = tengbe.Mac(corr.configd['xengine']['10gbe_start_mac'])

    boards_info = {}
    board_id = 0
    mac = int(mac_start)
    for f in corr.xhosts:
        macs = []
        for gbe in f.tengbes:
            macs.append(mac)
            mac += 1
        boards_info[f.host] = board_id, macs
        board_id += 1

    def setup_gbes(f):
        board_id, macs = boards_info[f.host]
        f.registers.board_id.write(reg=board_id)
        for gbe, this_mac in zip(f.tengbes, macs):
            gbe.setup(mac=this_mac, ipaddress='0.0.0.0', port=xeng_port)
            corr.logger.info('xhost(%s) gbe(%s) mac(%s) port(%i) board_id(%i)' %
                             (f.host, gbe.name, str(gbe.mac), xeng_port, board_id))
            # gbe.tap_start(restart=True)
            gbe.dhcp_start()
    THREADED_FPGA_OP(corr.xhosts, timeout=40, target_function=(setup_gbes,))

    # clear gbe status
    THREADED_FPGA_OP(corr.xhosts, timeout=10,
                     target_function=(lambda fpga_: fpga_.registers.control.write(gbe_debug_rst='pulse'),))

    # release cores from reset
    THREADED_FPGA_OP(corr.xhosts, timeout=10,
                     target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=False),))

    # simulator
    if use_xeng_sim:
        THREADED_FPGA_OP(corr.xhosts, timeout=10,
                         target_function=(lambda fpga_: fpga_.registers.simulator.write(en=True),))

    # set up accumulation length
    xeng_set_acc_len(corr,vacc_resync=False)

    # clear general status
    THREADED_FPGA_OP(corr.xhosts, timeout=10,
                     target_function=(lambda fpga_: fpga_.registers.control.write(status_clr='pulse'),))

    # check for errors
    # TODO - read status regs?


def xeng_clear_status_all(corr):
    """
    Clear the various status registers and counters on all the fengines
    :return:
    """
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function='clear_status')


def xeng_subscribe_to_multicast(corr):
    """
    Subscribe the x-engines to the f-engine output multicast groups - each one subscribes to
    only one group, with data meant only for it.
    :return:
    """
    if corr.fengine_output.is_multicast():
        corr.logger.info('F > X is multicast from base %s' % corr.fengine_output)
        source_address = str(corr.fengine_output.ip_address)
        source_bits = source_address.split('.')
        source_base = int(source_bits[3])
        source_prefix = '%s.%s.%s.' % (source_bits[0], source_bits[1], source_bits[2])
        source_ctr = 0
        for host_ctr, host in enumerate(corr.xhosts):
            for gbe in host.tengbes:
                rxaddress = '%s%d' % (source_prefix, source_base + source_ctr)
                gbe.multicast_receive(rxaddress, 0)
                source_ctr += 1
                corr.logger.info('\txhost %s %s subscribing to address %s' % (host.host, gbe.name, rxaddress))
    else:
        corr.logger.info('F > X is unicast from base %s' % corr.fengine_output)


def xeng_check_rx(corr, max_waittime=30):
    """
    Check that the x hosts are receiving data correctly
    :param max_waittime:
    :return:
    """
    corr.logger.info('Checking X hosts are receiving data...')
    results = THREADED_FPGA_FUNC(corr.xhosts, timeout=max_waittime+1,
                                 target_function=('check_rx', (max_waittime,),))
    all_okay = True
    for _v in results.values():
        all_okay = all_okay and _v
    if not all_okay:
        corr.logger.error('\tERROR in X-engine rx data.')
    corr.logger.info('\tdone.')
    return all_okay


def xeng_vacc_sync(corr, vacc_load_time=None):
    """
    Sync the vector accumulators on all the x-engines.
    Assumes that the x-engines are all receiving data.
    :return:
    """
    min_ld_time = 2
    # how long should we wait for the vacc load
    if vacc_load_time is None:
        corr.logger.info("Vacc sync time not specified. Syncing in %2.2f seconds' time."
                         % (2*min_ld_time))
        vacc_load_time = time.time()+2*min_ld_time

    t_now = time.time()
    if vacc_load_time < (t_now + min_ld_time):
        raise RuntimeError(
            'Cannot load at a time in the past. '
            'Need at least %2.2f seconds lead time. You asked for %s.%i, '
            'and it is now %s.%i.' % (
                               min_ld_time,
                               time.strftime('%H:%M:%S',time.gmtime(vacc_load_time)),
                               (vacc_load_time-int(vacc_load_time))*100,
                               time.strftime('%H:%M:%S',time.gmtime(t_now)),
                               (t_now-int(t_now))*100) )

    corr.logger.info('xeng vaccs syncing at %s (in %2.2fs)'
                     % (time.ctime(),vacc_load_time-time.time()) )

    # check if the vaccs need resetting
    vaccstat = THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                                  target_function='vacc_check_arm_load_counts')
    reset_required = False
    for xhost, result in vaccstat.items():
        if result:
            corr.logger.info('xeng_vacc_sync: %s has a vacc that '
                             'needs resetting' % xhost)
            reset_required = True

    if reset_required:
        THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                           target_function='vacc_reset')
        vaccstat = THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                                      target_function='vacc_check_reset_status')
        for xhost, result in vaccstat.items():
            if not result:
                errstr = 'xeng_vacc_sync: resetting vaccs on ' \
                         '%s failed.' % xhost
                corr.logger.error(errstr)
                raise RuntimeError(errstr)

    # set the vacc load time on the xengines
    ldmcnt = int(corr.mcnt_from_time(vacc_load_time))
    quantisation_bits = int(numpy.log2(int(corr.configd['fengine']['n_chans'])) + 1
                            + numpy.log2(int(corr.configd['xengine']['xeng_accumulation_len'])))
    ldmcnt = ((ldmcnt >> quantisation_bits)+1) << quantisation_bits

    if corr.time_from_mcnt(ldmcnt) < time.time():
        corr.logger.warn('Warning: the board timestamp has probably wrapped!')

    corr.logger.info('\tApplying load time: %i.' % ldmcnt)
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                       target_function=('vacc_set_loadtime', (ldmcnt,),))

    # read the current arm and load counts
    def print_vacc_statuses(vstatus):
        corr.logger.info('VACC statii:')
        for _host in corr.xhosts:
            corr.logger.info('\t%s:' % _host.host)
            for _ctr, _status in enumerate(vstatus[_host.host]):
                corr.logger.info('\t\t%i: %s' % (_ctr, _status))
    vacc_status = THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                                     target_function='vacc_get_status')
    for host in corr.xhosts:
        for status in vacc_status[host.host]:
            if ((status['loadcount'] != vacc_status[corr.xhosts[0].host][0]['loadcount']) or
                    (status['armcount'] != vacc_status[corr.xhosts[0].host][0]['armcount'])):
                corr.logger.error('All hosts do not have matching arm and load counts.')
                print_vacc_statuses(vacc_status)
                raise RuntimeError
    arm_count = vacc_status[corr.xhosts[0].host][0]['armcount']
    load_count = vacc_status[corr.xhosts[0].host][0]['loadcount']
    corr.logger.info('\tBefore arming: arm_count(%i) load_count(%i)' % (arm_count, load_count))

    # then arm them
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10, target_function='vacc_arm')

    # did the arm count increase?
    vacc_status = THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                                     target_function='vacc_get_status')
    for host in corr.xhosts:
        for status in vacc_status[host.host]:
            if ((status['armcount'] != vacc_status[corr.xhosts[0].host][0]['armcount']) or
                    (status['armcount'] != arm_count + 1)):
                errstr = 'xeng_vacc_sync: all hosts do not have matching arm ' \
                         'counts or arm count did not increase.'
                corr.logger.error(errstr)
                print_vacc_statuses(vacc_status)
                raise RuntimeError(errstr)
    corr.logger.info('\tDone arming')

    # check the the load time was stored correctly
    lsws = THREADED_FPGA_OP(corr.xhosts, timeout=10,
                            target_function=(lambda x: x.registers.vacc_time_lsw.read()['data']),)
    msws = THREADED_FPGA_OP(corr.xhosts, timeout=10,
                            target_function=(lambda x: x.registers.vacc_time_msw.read()['data']),)
    for host in corr.xhosts:
        if ((lsws[host.host]['lsw'] != lsws[corr.xhosts[0].host]['lsw']) or
                (msws[host.host]['msw'] != msws[corr.xhosts[0].host]['msw'])):
            errstr = 'xeng_vacc_sync: all hosts do not have matching VACC LSWs and MSWs'
            corr.logger.error(errstr)
            print 'lsws:', lsws
            print 'msws:', msws
            vacc_status = THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                                             target_function='vacc_get_status')
            print_vacc_statuses(vacc_status)
            raise RuntimeError(errstr)
    lsw = lsws[corr.xhosts[0].host]['lsw']
    msw = msws[corr.xhosts[0].host]['msw']
    xldtime = (msw << 32) | lsw
    corr.logger.info('\tx engines have vacc ld time %i' % xldtime)

    # wait for the vaccs to arm
    wait_time = corr.time_from_mcnt(ldmcnt) - time.time() + 0.2
    corr.logger.info('\tWaiting %2.2f seconds for arm to trigger.' % wait_time)
    time.sleep(wait_time)
    # check the status to see that the load count increased
    vacc_status = THREADED_FPGA_FUNC(corr.xhosts, timeout=5,
                                     target_function='vacc_get_status')
    for host in corr.xhosts:
        for status in vacc_status[host.host]:
            if ((status['loadcount'] != vacc_status[corr.xhosts[0].host][0]['loadcount']) or
                    (status['loadcount'] != load_count + 1)):
                corr.logger.error('VACC did not trigger!')
                print_vacc_statuses(vacc_status)
                raise RuntimeError('VACC did not trigger!')
    corr.logger.info('\tAll VACCs triggered correctly.')

    #allow vacc to flush and correctly populate parity bits:
    corr.logger.info('\tWaiting %2.2fs for an accumulation to flush, '
                     'to correctly populate parity bits.' %
                     xeng_get_acc_time(corr))
    time.sleep(xeng_get_acc_time(corr)+0.2)

    corr.logger.info('\tClearing status and reseting counters.')
    THREADED_FPGA_FUNC(corr.xhosts, timeout=10,
                       target_function='clear_status')

    #wait for a good accumulation to finish.
    corr.logger.info('\tWaiting %2.2fs for an accumulation to flush '
                     'before checking counters.'%xeng_get_acc_time(corr))
    time.sleep(xeng_get_acc_time(corr)+0.2)

    corr.logger.info('\tChecking for errors & accumulations...')
    vacc_status = THREADED_FPGA_FUNC(corr.xhosts, timeout=5,
                                     target_function='vacc_get_status')
    errors_found = False
    for host in corr.xhosts:
        for status in vacc_status[host.host]:
            if status['errors'] > 0:
                corr.logger.error('\tVACC errors > 0. Que pasa?')
                errors_found = True
            if status['count'] <= 0:
                corr.logger.error('\tVACC counts <= 0. Que pasa?')
                errors_found = True
    if errors_found:
        vacc_error_detail = THREADED_FPGA_FUNC(corr.xhosts,
                                               timeout=5,
                                               target_function='vacc_get_error_detail')
        corr.logger.error('xeng_vacc_sync: exited on VACC error')
        corr.logger.error('xeng_vacc_sync: vacc statii:')
        for host, item in vacc_status.items():
            corr.logger.error('\t%s: %s' % (host, str(item)))
        corr.logger.error('xeng_vacc_sync: vacc errors:')
        for host, item in vacc_error_detail.items():
            corr.logger.error('\t%s: %s' % (host, str(item)))
        raise RuntimeError('xeng_vacc_sync: exited on VACC error')
    corr.logger.info('\t...accumulations rolling in without error.')
    return corr.time_from_mcnt(ldmcnt)


def xeng_set_acc_time(corr, acc_time_s, vacc_resync=True):
    """
    Set the vacc accumulation length based on a required dump time, in seconds
    :param acc_time_s: new dump time, in seconds
    :return:
    """
    if use_xeng_sim:
        raise RuntimeError('That\'s not an option anymore.')
    else:
        new_acc_len = (corr.sample_rate_hz * acc_time_s) /
                       (corr.xeng_accumulation_len * corr.n_chans * 2.0)
        new_acc_len = round(new_acc_len)
        xeng_set_acc_len(corr, new_acc_len, vacc_resync)

def xeng_get_acc_time(corr):
    """
    Get the dump time currently being used.
    :return:
    """
    return (corr.xeng_accumulation_len * corr.accumulation_len * corr.n_chans * 2.0) / corr.sample_rate_hz

def xeng_set_acc_len(corr, acc_len=None, vacc_resync=True):
    """
    Set the QDR vector accumulation length.
    :param acc_len:
    :return:
    """
    if acc_len is not None:
        corr.accumulation_len = acc_len
    THREADED_FPGA_OP(corr.xhosts, timeout=10,
                     target_function=(lambda fpga_:
                                      fpga_.registers.acc_len.write_int(corr.accumulation_len),))
    corr.logger.info('Set VACC accumulation length %d system-wide (%.2f seconds)' %
                     (corr.accumulation_len, xeng_get_acc_time(corr)))
    if corr.spead_meta_ig is not None:
        corr.spead_meta_ig['n_accs'] = corr.accumulation_len * corr.xeng_accumulation_len
        corr.spead_meta_ig['int_time'] = xeng_get_acc_time(corr)
        corr.spead_tx.send_heap(corr.spead_meta_ig.get_heap())
    if vacc_resync:
        xeng_vacc_sync(corr)


def xeng_get_baseline_order(corr):
        """
        Return the order of baseline data output by a CASPER correlator X engine.
        :return:
        """
        # TODO - nants vs number of inputs?
        assert len(corr.fengine_sources)/2 == corr.n_antennas
        order1 = []
        order2 = []
        for ctr1 in range(corr.n_antennas):
            # print 'ctr1(%d)' % ctr1
            for ctr2 in range(int(corr.n_antennas/2), -1, -1):
                temp = (ctr1 - ctr2) % corr.n_antennas
                # print '\tctr2(%d) temp(%d)' % (ctr2, temp)
                if ctr1 >= temp:
                    order1.append((temp, ctr1))
                else:
                    order2.append((ctr1, temp))
        order2 = [order_ for order_ in order2 if order_ not in order1]
        baseline_order = order1 + order2
        source_names = []
        for source in corr.fengine_sources:
            source_names.append(source.name)
        rv = []
        for baseline in baseline_order:
            rv.append((source_names[baseline[0] * 2],       source_names[baseline[1] * 2]))
            rv.append((source_names[baseline[0] * 2 + 1],   source_names[baseline[1] * 2 + 1]))
            rv.append((source_names[baseline[0] * 2],       source_names[baseline[1] * 2 + 1]))
            rv.append((source_names[baseline[0] * 2 + 1],   source_names[baseline[1] * 2]))
        return rv
