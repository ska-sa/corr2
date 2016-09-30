import logging
import time
import tornado.gen

from tornado.ioloop import IOLoop
from concurrent import futures

from casperfpga.katcp_fpga import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid

from sensors import Corr2Sensor

LOGGER = logging.getLogger(__name__)

FHOST_REGS = ['spead_ctrs', 'reorder_ctrs', 'sync_ctrs', 'pfb_ctrs', 'ct_ctrs',
              'cd_ctrs']
FHOST_REGS.extend(['gbe%i_txctr' % ctr for ctr in range(4)])
FHOST_REGS.extend(['gbe%i_txerrctr' % ctr for ctr in range(4)])
FHOST_REGS.extend(['gbe%i_rxctr' % ctr for ctr in range(4)])
FHOST_REGS.extend(['gbe%i_rxerrctr' % ctr for ctr in range(4)])

XHOST_REGS = ['rx_cnt%i' % ctr for ctr in range(4)]
XHOST_REGS.extend(['rx_err_cnt%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['dest_err_cnt%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reordcnt_spec%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reord_missant%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reordcnt_recv%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reorderr_recv%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reorderr_timeout%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reorderr_disc%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['bf%i_out_count' % ctr for ctr in range(2)])
XHOST_REGS.extend(['bf%i_of_count' % ctr for ctr in range(2)])
XHOST_REGS.extend(['vacccnt%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vaccout%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vaccerr%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vacc_ld_status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vacc_errors%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['packcnt_out%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['packerr_%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['gbe%i_txctr' % ctr for ctr in range(4)])
XHOST_REGS.extend(['gbe%i_rxctr' % ctr for ctr in range(4)])
XHOST_REGS.extend(['gbe%i_rxerrctr' % ctr for ctr in range(4)])

TX_PPS_SUFFIX = '-tx-pkt-per-s'
RX_PPS_SUFFIX = '-rx-pkt-per-s'
LINK_STATUS_SUFFIX = '-link-status'


def read_all_counters(fpga_host):
    """

    :param fpga_host:
    :return: a dictionary of all the counters in this host
    """
    if 'fft_shift' in fpga_host.registers.names():
        reglist = FHOST_REGS
    else:
        reglist = XHOST_REGS
    rs = {}
    for reg in reglist:
        if reg in fpga_host.registers.names():
            d = fpga_host.registers[reg].read()['data']
            rs[reg] = d
    rvdict = {}
    for reg in rs:
        for key in rs[reg]:
            _regrepr = reg.replace('_', '-')
            _keyrepr = key.replace('_', '-')
            sensname = '%s-%s-%s-change' % (fpga_host.host, _regrepr, _keyrepr)
            rvdict[sensname] = rs[reg][key]
    return rvdict


@tornado.gen.coroutine
def _sensor_cb_feng_rxtime(sensor_ok, sensor_values):
    """
    Sensor call back to check received F-engine times
    :param sensor_ok: the combined times-are-okay sensor
    :param sensor_values: per-host sensors for time and unix-time
    :return:
    """
    executor = sensor_ok.executor
    instrument = sensor_ok.manager.instrument
    try:
        result, counts, times = yield executor.submit(
            instrument.fops.check_rx_timestamps)
        sensor_ok.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                      result)
        for host in counts:
            sensor, sensor_u = sensor_values[host]
            sensor.set_value(counts[host])
            sensor_u.set_value(times[host])
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor_ok.set(time.time(), Corr2Sensor.UNKNOWN, False)
        for sensor, sensor_u in sensor_values.values():
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            sensor_u.set(time.time(), Corr2Sensor.UNKNOWN, -1)
    except Exception as e:
        LOGGER.exception('Error updating feng rxtime sensor '
                         '- {}'.format(e.message))
        sensor_ok.set(time.time(), Corr2Sensor.UNKNOWN, False)
        for sensor, sensor_u in sensor_values.values():
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            sensor_u.set(time.time(), Corr2Sensor.UNKNOWN, -1)
    LOGGER.debug('_sensor_cb_feng_rxtime ran')
    IOLoop.current().call_later(10, _sensor_cb_feng_rxtime,
                                sensor_ok, sensor_values)


@tornado.gen.coroutine
def _sensor_cb_fdelays(sensor, f_host):
    """
    Sensor call back function for F-engine delay functionality
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.delay_check_loadcounts)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating delay functionality sensor '
                         'for {} - {}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_cb_fdelays ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_cb_fdelays, sensor, f_host)


@tornado.gen.coroutine
def _sensor_cb_flru(sensor, f_host):
    """
    Sensor call back function for F-engine LRU
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.host_okay)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating flru sensor for {} - '
                         '{}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_cb_flru ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_cb_flru, sensor, f_host)


@tornado.gen.coroutine
def _sensor_cb_xlru(sensor, x_host):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.host_okay)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating xlru sensor for {} - '
                         '{}'.format(x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_cb_xlru ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_cb_xlru, sensor, x_host)


@tornado.gen.coroutine
def _sensor_feng_phy(sensor, f_host):
    """
    F-engine PHY counters
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_phy_counter)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating feng_phy sensor for {} - '
                         '{}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_feng_phy ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_phy, sensor, f_host)


@tornado.gen.coroutine
def _sensor_xeng_phy(sensor, x_host):
    """
    x-engine PHY counters
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.check_phy_counter)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating xeng_phy sensor for {} - '
                         '{}'.format(x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_xeng_phy ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_phy, sensor, x_host)


@tornado.gen.coroutine
def _xeng_qdr_okay(sensor, x_host):
    """
    x-engine QDR check
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.qdr_okay)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating xeng qdr sensor for {} - '
                         '{}'.format(x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_xeng_qdr_okay ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _xeng_qdr_okay, sensor, x_host)


@tornado.gen.coroutine
def _feng_qdr_okay(sensor, f_host):
    """
    F-engine QDR check
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.qdr_okay)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating feng qdr sensor for {} - '
                         '{}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_feng_qdr_okay ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _feng_qdr_okay, sensor, f_host)


@tornado.gen.coroutine
def _feng_pfb_okay(sensor, f_host):
    """
    F-engine PFB check
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_fft_overflow)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating feng pfb sensor for {} - '
                         '{}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_feng_pfb_okay ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _feng_pfb_okay, sensor, f_host)


@tornado.gen.coroutine
def _fhost_check_10gbe_rx(sensor, f_host):
    """
    Check that the f-hosts are receiving data correctly
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_rx_raw, 0.2, 5)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating {} for {} - '
                         '{}'.format(sensor.name, f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_fhost_check_10gbe_rx ran')
    IOLoop.current().call_later(10, _fhost_check_10gbe_rx, sensor, f_host)


@tornado.gen.coroutine
def _fhost_check_10gbe_tx(sensor, f_host):
    """
    Check that the f-hosts are sending data correctly
    :param sensor:
    :param f_host:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_tx_raw, 0.2, 5)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating {} for {} - '
                         '{}'.format(sensor.name, f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_fhost_check_10gbe_tx ran')
    IOLoop.current().call_later(10, _fhost_check_10gbe_tx, sensor, f_host)


@tornado.gen.coroutine
def _xhost_check_10gbe_rx(sensor, x_host):
    """
    Check that the x-hosts are receiving data correctly
    :param sensor:
    :param x_host:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.check_rx_raw, 0.2, 5)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating {} for {} - '
                         '{}'.format(sensor.name, x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_xhost_check_10gbe_rx ran')
    IOLoop.current().call_later(10, _xhost_check_10gbe_rx, sensor, x_host)


@tornado.gen.coroutine
def _xhost_report_10gbe_tx(sensor, x_host, gbe):
    """
    Check that the x-hosts are sending data correctly
    :param sensor:
    :param x_host:
    :param gbe:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(
            x_host.registers['%s_txctr' % gbe.name].read)
        result = result['data']['reg']
        sensor.set_value(result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
    except Exception as e:
        LOGGER.exception('Error updating {} for {} - '
                         '{}'.format(sensor.name, x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
    LOGGER.debug('_xhost_report_10gbe_tx ran')
    IOLoop.current().call_later(10, _xhost_report_10gbe_tx, sensor, x_host, gbe)


@tornado.gen.coroutine
def _sensor_feng_rx_reorder(sensor, f_host):
    """
    F-engine RX counters
    :param sensor:
    :return: true/false
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_rx_reorder)
        sensor.set(time.time(), Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating feng_rx sensor for {} - '
                         '{}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_feng_rx ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_rx_reorder, sensor, f_host)


@tornado.gen.coroutine
def _sensor_xeng_rx_reorder(sensor, x_host):
    """
    X-engine RX counters
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.check_rx_reorder)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating xeng_rx sensor for {} - '
                         '{}'.format(x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_xeng_rx ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_rx_reorder, sensor, x_host)


@tornado.gen.coroutine
def _sensor_xeng_vacc_ctrs(host, host_executor, manager):
    """

    :param host:
    :param host_executor:
    :param manager:
    :return:
    """
    results = [-1] * host.x_per_fpga
    try:
        results = yield host_executor.submit(host.vacc_counters_get)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        LOGGER.exception('Katcp error updating vacc counter sensors for {}'
                         ''.format(host.host))
    except Exception as e:
        LOGGER.exception('Error updating vacc counter sensors for {} - '
                         '{}'.format(host.host, e.message))
    for xctr in range(host.x_per_fpga):
        sensor = manager.sensor_get(
            '%s-xeng%i-vacc-ctr' % (host.host, xctr))
        sensor.set(time.time(), Corr2Sensor.NOMINAL, results[xctr])
    LOGGER.debug('_sensor_xeng_vacc_ctrs ran on {}'.format(host))
    IOLoop.current().call_later(10, _sensor_xeng_vacc_ctrs, host,
                                host_executor, manager)


@tornado.gen.coroutine
def _sensor_xeng_vacc_accs_ps(host, host_executor, manager):
    """

    :param host:
    :param host_executor:
    :param manager:
    :return:
    """
    results = [-1] * host.x_per_fpga
    try:
        results = yield host_executor.submit(host.vacc_accumulations_per_second)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        LOGGER.exception('Katcp error updating vacc rate sensors for {}'
                         ''.format(host.host))
    except Exception as e:
        LOGGER.exception('Error updating vacc rate sensors for {} - '
                         '{}'.format(host.host, e.message))
    for xctr in range(host.x_per_fpga):
        sensor = manager.sensor_get(
            '%s-xeng%i-accs-per-sec' % (host.host, xctr))
        sensor.set(time.time(), Corr2Sensor.NOMINAL, results[xctr])
    LOGGER.debug('_sensor_xeng_vacc_accs_ps ran on {}'.format(host))
    IOLoop.current().call_later(10, _sensor_xeng_vacc_accs_ps, host,
                                host_executor, manager)


@tornado.gen.coroutine
def _sensor_cb_system_counters(host, host_executor, manager):
    """
    Read all specified counters on this host.
    :param host:
    :return:
    """
    try:
        result = yield host_executor.submit(read_all_counters, host)
        for sens_name in result:
            sensor = manager.sensor_get(sens_name)
            oldval = sensor.previous_value
            sens_value = result[sens_name] != oldval
            sensor.set_value(sens_value)
            sensor.previous_value = result[sens_name]
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        for sensor in manager._sensors.values():
            if ((sensor.name.endswith('-change')) and
                    (sensor.name.startswith(host.host))):
                sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
                sensor.previous_value = 0
    except Exception as e:
        LOGGER.exception('Error updating counter sensors for {} - '
                         '{}'.format(host, e.message))
        for sensor in manager._sensors.values():
            if ((sensor.name.endswith('-change')) and
                    (sensor.name.startswith(host.host))):
                sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
                sensor.previous_value = 0
    IOLoop.current().call_later(10, _sensor_cb_system_counters,
                                host, host_executor, manager)


@tornado.gen.coroutine
def _sensor_cb_pps(host, host_executor, manager):
    """
    Host PPS counters
    :return:
    """
    def read_tengbe_tx_rx(fpga):
        rv = {}
        for tengbe in fpga.tengbes:
            ctrs = tengbe.read_counters()
            link_info = tengbe.get_10gbe_core_details()['xaui_status']
            rv[tengbe.name] = (ctrs['%s_txctr' % tengbe.name],
                               ctrs['%s_rxctr' % tengbe.name],
                               str(link_info))
        return rv
    try:
        new_values = yield host_executor.submit(read_tengbe_tx_rx, host)
        for tengbe in host.tengbes:
            hpref = '%s-%s' % (host.host, tengbe.name)
            # TX
            sensor_name = '%s%s' % (hpref, TX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            previous_value = sensor.previous_value
            pps = (new_values[tengbe.name][0] - previous_value) / 10.0
            sensor.previous_value = new_values[tengbe.name][0]
            sensor.set_value(pps)
            # RX
            sensor_name = '%s%s' % (hpref, RX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            previous_value = sensor.previous_value
            pps = (new_values[tengbe.name][1] - previous_value) / 10.0
            sensor.previous_value = new_values[tengbe.name][1]
            sensor.set_value(pps)
            # link-status
            sensor_name = '%s%s' % (hpref, LINK_STATUS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set_value(new_values[tengbe.name][2])
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        for tengbe in host.tengbes:
            hpref = '%s-%s' % (host.host, tengbe.name)
            # TX
            sensor_name = '%s%s' % (hpref, TX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # RX
            sensor_name = '%s%s' % (hpref, RX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # link-status
            sensor_name = '%s%s' % (hpref, LINK_STATUS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, '')
    except Exception as e:
        LOGGER.exception('Error updating PPS sensors for {} - '
                         '{}'.format(host.host, e.message))
        for tengbe in host.tengbes:
            hpref = '%s-%s' % (host.host, tengbe.name)
            # TX
            sensor_name = '%s%s' % (hpref, TX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # RX
            sensor_name = '%s%s' % (hpref, RX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # link-status
            sensor_name = '%s%s' % (hpref, LINK_STATUS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, '')
    LOGGER.debug('_sensor_cb_pps ran on {}'.format(host.host))
    IOLoop.current().call_later(10, _sensor_cb_pps,
                                host, host_executor, manager)


def setup_sensors(sensor_manager):
    """
    INSTRUMENT-STATE-INDEPENDENT sensors to be reported to CAM
    :param sensor_manager: A SensorManager instance
    :return:
    """
    sens_man = sensor_manager
    
    # Set up a one-worker pool per host to serialise interactions with each host
    host_executors = {
        host.host: futures.ThreadPoolExecutor(max_workers=1)
        for host in sens_man.instrument.fhosts +
        sens_man.instrument.xhosts
    }
    general_executor = futures.ThreadPoolExecutor(max_workers=1)

    if not sensor_manager.instrument.initialised():
        raise RuntimeError('Cannot set up sensors until instrument is '
                           'initialised.')

    ioloop = getattr(sens_man.instrument, 'ioloop', None)
    if not ioloop:
        ioloop = getattr(sens_man.katcp_server, 'ioloop', None)
    if not ioloop:
        raise RuntimeError('IOLoop-containing katcp version required. Can go '
                           'no further.')

    sens_man.sensors_clear()

    # F-engine received timestamps okay and per-host received timestamps
    sensor_ok = sens_man.do_sensor(
        Corr2Sensor.boolean, 'feng-rxtime-ok',
        'Are the times received by F-engines in the system okay?',
        Corr2Sensor.UNKNOWN, '', general_executor)
    sensor_values = {}
    for _f in sens_man.instrument.fhosts:
        sensor = sens_man.do_sensor(
            Corr2Sensor.integer, '%s-feng-rxtime48' % _f.host,
            'F-engine %s - 48-bit timestamps received from '
            'the digitisers' % _f.host,
            Corr2Sensor.UNKNOWN)
        sensor_u = sens_man.do_sensor(
            Corr2Sensor.float, '%s-feng-rxtime-unix' % _f.host,
            'F-engine %s - UNIX timestamps received from '
            'the digitisers' % _f.host,
            Corr2Sensor.UNKNOWN)
        sensor_values[_f.host] = (sensor, sensor_u)
    ioloop.add_callback(_sensor_cb_feng_rxtime, sensor_ok, sensor_values)

    # F-engine host sensors
    for _f in sens_man.instrument.fhosts:
        executor = host_executors[_f.host]

        # LRU okay
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-feng-lru-ok' % _f.host,
            'F-engine %s LRU okay' % _f.host, Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_cb_flru, sensor, _f)

        # QDR errors
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-feng-qdr-ok' % _f.host,
            'F-engine QDR okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_feng_qdr_okay, sensor, _f)

        # PHY counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-feng-phy-ok' % _f.host,
            'F-engine PHY okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_feng_phy, sensor, _f)

        # PFB counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-feng-pfb-ok' % _f.host,
            'F-engine PFB okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_feng_pfb_okay, sensor, _f)

        # Raw RX - tengbe counters must increment
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-feng-10gbe-rx-ok' % _f.host,
            'F-engine 10gbe RX okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_fhost_check_10gbe_rx, sensor, _f)

        # Raw TX - tengbe counters must increment
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-feng-10gbe-tx-ok' % _f.host,
            'F-engine 10gbe TX okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_fhost_check_10gbe_tx, sensor, _f)

        # Rx reorder counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-feng-reorder-ok' % _f.host,
            'F-engine RX okay - reorder counters incrementing correctly',
            Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_feng_rx_reorder, sensor, _f)

        # Delay functionality
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-feng-delays-ok' % _f.host,
            'F-engine %s delay functionality' % _f.host,
            Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_cb_fdelays, sensor, _f)

    # X-engine host sensors
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]

        # LRU okay
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-xeng-lru-ok' % _x.host,
            'X-engine %s LRU okay' % _x.host, Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_cb_xlru, sensor, _x)

        # QDR errors
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-xeng-qdr-ok' % _x.host,
            'X-engine QDR okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_xeng_qdr_okay, sensor, _x)

        # PHY counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-xeng-phy-ok' % _x.host,
            'X-engine PHY okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_xeng_phy, sensor, _x)

        # Raw RX - tengbe counters must increment
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-xeng-10gbe-rx-ok' % _x.host,
            'X-engine 10gbe RX okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_xhost_check_10gbe_rx, sensor, _x)

        # Raw TX - report tengbe counters
        for gbe in _x.tengbes:
            sensor = sens_man.do_sensor(
                Corr2Sensor.integer,
                '%s-xeng-10gbe-%s-tx-ctr' % (_x.host, gbe.name),
                'X-engine 10gbe TX counter', Corr2Sensor.UNKNOWN, '', executor)
            ioloop.add_callback(_xhost_report_10gbe_tx, sensor, _x, gbe)

        # Rx reorder counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '%s-xeng-reorder-ok' % _x.host,
            'X-engine RX okay - reorder counters incrementing correctly',
            Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_xeng_rx_reorder, sensor, _x)

        # VACC counters
        for xctr in range(_x.x_per_fpga):
            sensor = sens_man.do_sensor(
                Corr2Sensor.integer, '%s-xeng%i-vacc-ctr' % (_x.host, xctr),
                'Number of accumulations this VACC has performed.',
                Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_xeng_vacc_ctrs, _x, executor,
                            sensor_manager)

        # VACC accumulations per second
        for xctr in range(_x.x_per_fpga):
            sensor = sens_man.do_sensor(
                Corr2Sensor.float, '%s-xeng%i-accs-per-sec' % (_x.host, xctr),
                'Number of accumulations per second for this X-engine on '
                'this host.',
                Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_xeng_vacc_accs_ps, _x, executor,
                            sensor_manager)

    all_hosts = sens_man.instrument.fhosts + sens_man.instrument.xhosts

    # tengbe packet-per-second counters
    for _h in all_hosts:
        executor = host_executors[_h.host]
        for tengbe in _h.tengbes:
            hpref = '%s-%s' % (_h.host, tengbe.name)
            sensor = sens_man.do_sensor(
                Corr2Sensor.integer,
                '%s%s' % (hpref, TX_PPS_SUFFIX),
                '%s %s TX packet-per-second counter' % (_h.host, tengbe.name),
                Corr2Sensor.UNKNOWN, '', executor)
            sensor.previous_value = 0
            sensor = sens_man.do_sensor(
                Corr2Sensor.integer,
                '%s%s' % (hpref, RX_PPS_SUFFIX),
                '%s %s RX packet-per-second counter' % (_h.host, tengbe.name),
                Corr2Sensor.UNKNOWN, '', executor)
            sensor.previous_value = 0
            sensor = sens_man.do_sensor(
                Corr2Sensor.string,
                '%s%s' % (hpref, LINK_STATUS_SUFFIX),
                '%s %s link status' % (_h.host, tengbe.name),
                Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_cb_pps, _h, executor, sens_man)

    # # read all relevant counters
    # for _h in all_hosts:
    #     executor = host_executors[_h.host]
    #     host_ctrs = read_all_counters(_h)
    #     for ctr in host_ctrs:
    #         sensor = sens_man.do_sensor(
    #             Corr2Sensor.boolean, '%s' % ctr,
    #             'Counter on %s, True is changed since last read' % _h.host,
    #             Corr2Sensor.UNKNOWN, '', executor)
    #         sensor.previous_value = 0
    #     ioloop.add_callback(_sensor_cb_system_counters,
    #                         _h, executor, sens_man)

# end
