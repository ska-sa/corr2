import logging
import time
import tornado.gen

from tornado.ioloop import IOLoop
from concurrent import futures

from casperfpga.katcp_fpga import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid

from sensors import Corr2Sensor


LOGGER = logging.getLogger(__name__)

FHOST_REGS = ['spead_ctrs', 'reorder_ctrs', 'sync_ctrs', 'pfb_ctrs', 'ct_ctrs']
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
    Sensor call back to check received f-engine times
    :param sensor_ok: the combined times-are-okay sensor
    :param sensor_values: per-host sensors for time and unix-time
    :return:
    """
    executor = sensor_ok.executor
    instrument = sensor_ok.manager.instrument
    try:
        result, counts, times = yield executor.submit(
            instrument.fops.check_rx_timestamps)
        sensor_ok.set(time.time(),
                      Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                      result)
        for host in counts:
            sensor, sensor_u = sensor_values[host]
            sensor.set(time.time(), Corr2Sensor.NOMINAL, counts[host])
            sensor_u.set(time.time(), Corr2Sensor.NOMINAL, times[host])
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
    Sensor call back function for f-engine delay functionality
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.delay_check_loadcounts)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
    Sensor call back function for f-engine LRU
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.host_okay)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
    f-engine PHY counters
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_phy_counter)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
    f-engine QDR check
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.qdr_okay)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
    f-engine PFB check
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_fft_overflow)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
        sensor.set(time.time(), Corr2Sensor.NOMINAL, result)
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
    f-engine rx counters
    :param sensor:
    :return: true/false
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_rx_reorder)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
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
    x-engine rx counters
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.check_rx_reorder)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                   result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.exception('Error updating xeng_rx sensor for {} - '
                         '{}'.format(x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_xeng_rx ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_rx_reorder, sensor, x_host)


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
            sensor.set(time.time(), Corr2Sensor.NOMINAL, sens_value)
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
            # tx
            sensor_name = '%s-%s-tx-pps-ctr' % (host.host, tengbe.name)
            sensor = manager.sensor_get(sensor_name)
            previous_value = sensor.previous_value
            pps = (new_values[tengbe.name][0] - previous_value) / 10.0
            sensor.previous_value = new_values[tengbe.name][0]
            sensor.set(time.time(), Corr2Sensor.NOMINAL, pps)
            # rx
            sensor_name = '%s-%s-rx-pps-ctr' % (host.host, tengbe.name)
            sensor = manager.sensor_get(sensor_name)
            previous_value = sensor.previous_value
            pps = (new_values[tengbe.name][1] - previous_value) / 10.0
            sensor.previous_value = new_values[tengbe.name][1]
            sensor.set(time.time(), Corr2Sensor.NOMINAL, pps)
            # link-status
            sensor_name = '%s-%s-link-status' % (host.host, tengbe.name)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.NOMINAL,
                       new_values[tengbe.name][2])
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        for tengbe in host.tengbes:
            # tx
            sensor_name = '%s-%s-tx-pps-ctr' % (host.host, tengbe.name)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # rx
            sensor_name = '%s-%s-rx-pps-ctr' % (host.host, tengbe.name)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # link-status
            sensor_name = '%s-%s-link-status' % (host.host, tengbe.name)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, '')
    except Exception as e:
        LOGGER.exception('Error updating PPS sensors for {} - '
                         '{}'.format(host.host, e.message))
        for tengbe in host.tengbes:
            # tx
            sensor_name = '%s-%s-tx-pps-ctr' % (host.host, tengbe.name)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # rx
            sensor_name = '%s-%s-rx-pps-ctr' % (host.host, tengbe.name)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # link-status
            sensor_name = '%s-%s-link-status' % (host.host, tengbe.name)
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
    # Set up a one-worker pool per host to serialise interactions with each host
    host_executors = {
        host.host: futures.ThreadPoolExecutor(max_workers=1)
        for host in sensor_manager.instrument.fhosts +
        sensor_manager.instrument.xhosts
    }
    general_executor = futures.ThreadPoolExecutor(max_workers=1)

    if not sensor_manager.instrument.initialised():
        raise RuntimeError('Cannot set up sensors until instrument is '
                           'initialised.')

    ioloop = getattr(sensor_manager.instrument, 'ioloop', None)
    if not ioloop:
        ioloop = getattr(sensor_manager.katcp_server, 'ioloop', None)
    if not ioloop:
        raise RuntimeError('IOLoop-containing katcp version required. Can go '
                           'no further.')

    sensor_manager.sensors_clear()

    # f-engine received timestamps okay and per-host received timestamps
    sensor_ok = Corr2Sensor.boolean(
        name='feng-rxtime-ok',
        description='Are the times received by f-engines in the system okay',
        initial_status=Corr2Sensor.UNKNOWN,
        manager=sensor_manager, executor=general_executor)
    sensor_values = {}
    for _f in sensor_manager.instrument.fhosts:
        sensor = Corr2Sensor.integer(
            name='%s-feng-rxtime48' % _f.host,
            description='F-engine %s - 48-bit timestamps received from '
                        'the digitisers' % _f.host,
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager)
        sensor_u = Corr2Sensor.integer(
            name='%s-feng-rxtime-unix' % _f.host,
            description='F-engine %s - UNIX timestamps received from '
                        'the digitisers' % _f.host,
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager)
        sensor_values[_f.host] = (sensor, sensor_u)
    ioloop.add_callback(_sensor_cb_feng_rxtime, sensor_ok, sensor_values)

    # f-engine lru
    for _f in sensor_manager.instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Corr2Sensor.boolean(
            name='%s-feng-lru-ok' % _f.host,
            description='F-engine %s LRU okay' % _f.host,
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_sensor_cb_flru, sensor, _f)

    # x-engine lru
    for _x in sensor_manager.instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Corr2Sensor.boolean(
            name='%s-xeng-lru-ok' % _x.host,
            description='X-engine %s LRU okay' % _x.host,
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_sensor_cb_xlru, sensor, _x)

    # x-engine QDR errors
    for _x in sensor_manager.instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Corr2Sensor.boolean(
            name='%s-xeng-qdr-ok' % _x.host,
            description='X-engine QDR okay',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_xeng_qdr_okay, sensor, _x)

    # f-engine QDR errors
    for _f in sensor_manager.instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Corr2Sensor.boolean(
            name='%s-feng-qdr-ok' % _f.host,
            description='F-engine QDR okay',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_feng_qdr_okay, sensor, _f)

    # x-engine PHY counters
    for _x in sensor_manager.instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Corr2Sensor.boolean(
            name='%s-xeng-phy-ok' % _x.host,
            description='X-engine PHY okay',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_sensor_xeng_phy, sensor, _x)

    # f-engine PHY counters
    for _f in sensor_manager.instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Corr2Sensor.boolean(
            name='%s-feng-phy-ok' % _f.host,
            description='F-engine PHY okay',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_sensor_feng_phy, sensor, _f)

    # f-engine PFB counters
    for _f in sensor_manager.instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Corr2Sensor.boolean(
            name='%s-feng-pfb-ok' % _f.host,
            description='F-engine PFB okay',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_feng_pfb_okay, sensor, _f)

    # f-engine raw rx - tengbe counters must increment
    for _f in sensor_manager.instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Corr2Sensor.boolean(
            name='%s-feng-10gbe-rx-ok' % _f.host,
            description='F-engine 10gbe RX okay',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_fhost_check_10gbe_rx, sensor, _f)

    # f-engine raw tx - tengbe counters must increment
    for _f in sensor_manager.instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Corr2Sensor.boolean(
            name='%s-feng-10gbe-tx-ok' % _f.host,
            description='F-engine 10gbe TX okay',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_fhost_check_10gbe_tx, sensor, _f)

    # x-engine raw rx - tengbe counters must increment
    for _x in sensor_manager.instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Corr2Sensor.boolean(
            name='%s-xeng-10gbe-rx-ok' % _x.host,
            description='X-engine 10gbe RX okay',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_xhost_check_10gbe_rx, sensor, _x)

    # x-engine raw tx - report tengbe counters
    for _x in sensor_manager.instrument.xhosts:
        executor = host_executors[_x.host]
        for gbe in _x.tengbes:
            sensor = Corr2Sensor.integer(
                name='%s-xeng-10gbe-%s-tx-ctr' % (_x.host, gbe.name),
                description='X-engine 10gbe TX counter',
                initial_status=Corr2Sensor.UNKNOWN,
                manager=sensor_manager, executor=executor)
            ioloop.add_callback(_xhost_report_10gbe_tx, sensor, _x, gbe)

    # f-engine rx reorder counters
    for _f in sensor_manager.instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Corr2Sensor.boolean(
            name='%s-feng-reorder-ok' % _f.host,
            description='F-engine RX okay - reorder counters incrementing'
                        'correctly',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_sensor_feng_rx_reorder, sensor, _f)

    # x-engine rx reorder counters
    for _x in sensor_manager.instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Corr2Sensor.boolean(
            name='%s-xeng-reorder-ok' % _x.host,
            description='X-engine RX okay - reorder counters incrementing'
                        'correctly',
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_sensor_xeng_rx_reorder, sensor, _x)

    # f-engine delay functionality
    for _f in sensor_manager.instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Corr2Sensor.boolean(
            name='%s-feng-delays-ok' % _f.host,
            description='F-engine %s delay functionality' % _f.host,
            initial_status=Corr2Sensor.UNKNOWN,
            manager=sensor_manager, executor=executor)
        ioloop.add_callback(_sensor_cb_fdelays, sensor, _f)

    all_hosts = sensor_manager.instrument.fhosts + \
                sensor_manager.instrument.xhosts

    # tengbe packet-per-second counters
    for _h in all_hosts:
        executor = host_executors[_h.host]
        for tengbe in _h.tengbes:
            sensor = Corr2Sensor.integer(
                name='%s-%s-tx-pps-ctr' % (_h.host, tengbe.name),
                description='%s %s TX packet-per-second counter' % (
                    _h.host, tengbe.name),
                initial_status=Corr2Sensor.UNKNOWN,
                manager=sensor_manager, executor=executor)
            sensor.previous_value = 0
            sensor = Corr2Sensor.integer(
                name='%s-%s-rx-pps-ctr' % (_h.host, tengbe.name),
                description='%s %s RX packet-per-second counter' % (
                    _h.host, tengbe.name),
                initial_status=Corr2Sensor.UNKNOWN,
                manager=sensor_manager, executor=executor)
            sensor.previous_value = 0
            sensor = Corr2Sensor.string(
                name='%s-%s-link-status' % (_h.host, tengbe.name),
                description='%s %s link status' % (
                    _h.host, tengbe.name),
                initial_status=Corr2Sensor.UNKNOWN,
                manager=sensor_manager, executor=executor)
        ioloop.add_callback(_sensor_cb_pps, _h, executor, sensor_manager)

    # read all relevant counters
    for _h in all_hosts:
        executor = host_executors[_h.host]
        host_ctrs = read_all_counters(_h)
        for ctr in host_ctrs:
            sensor = Corr2Sensor.boolean(
                name='%s' % ctr,
                description='Counter on %s, True is changed since '
                            'last read' % _h.host,
                initial_status=Corr2Sensor.UNKNOWN,
                manager=sensor_manager, executor=executor)
            sensor.previous_value = 0
        ioloop.add_callback(_sensor_cb_system_counters,
                            _h, executor, sensor_manager)

# end
