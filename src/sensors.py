import logging
import time
import tornado.gen

from katcp import Sensor
from tornado.ioloop import IOLoop
from concurrent import futures

from fhost_fpga import DelaysUnsetError

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
            rvdict['%s_%s_%s_change' % (fpga_host.host, reg, key)] = rs[reg][key]
    return rvdict


@tornado.gen.coroutine
def _sensor_cb_feng_rxtime(sensor, executor, instrument):
    """
    Sensor call back to check received f-engine times
    :param sensor:
    :param executor:
    :param instrument:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(instrument.fops.check_rx_timestamps)
    except Exception as e:
        LOGGER.exception('Error updating feng rxtime sensor '
                         '- {}'.format(e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_cb_feng_rxtime ran')
    IOLoop.current().call_later(10, _sensor_cb_feng_rxtime, sensor, executor,
                                instrument)


@tornado.gen.coroutine
def _sensor_cb_fdelays(sensor, executor, f_host):
    """
    Sensor call back function for f-engine delay functionality
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.delay_check_loadcounts)
    except DelaysUnsetError:
        sensor.set(time.time(), Sensor.UNKNOWN, None)
        return
    except Exception as e:
        LOGGER.exception('Error updating delay functionality sensor '
                         'for {} - {}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.WARN, result)
    LOGGER.debug('_sensor_cb_fdelays ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_cb_fdelays, sensor,
                                executor, f_host)


@tornado.gen.coroutine
def _sensor_cb_flru(sensor, executor, f_host):
    """
    Sensor call back function for f-engine LRU
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.host_okay)
    except Exception as e:
        LOGGER.exception('Error updating flru sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_cb_flru ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_cb_flru, sensor, executor, f_host)


@tornado.gen.coroutine
def _sensor_cb_xlru(sensor, executor, x_host):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.host_okay)
    except Exception as e:
        LOGGER.exception('Error updating xlru sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_cb_xlru ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_cb_xlru, sensor, executor, x_host)


@tornado.gen.coroutine
def _sensor_feng_phy(sensor, executor, f_host):
    """
    f-engine PHY counters
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_phy_counter)
    except Exception as e:
        LOGGER.exception('Error updating feng_phy sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_feng_phy ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_phy, sensor, executor, f_host)


@tornado.gen.coroutine
def _sensor_xeng_phy(sensor, executor, x_host):
    """
    x-engine PHY counters
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.check_phy_counter)
    except Exception as e:
        LOGGER.exception('Error updating xeng_phy sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_xeng_phy ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_phy, sensor, executor, x_host)


@tornado.gen.coroutine
def _xeng_qdr_okay(sensor, executor, x_host):
    """
    x-engine QDR check
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.qdr_okay)
    except Exception as e:
        LOGGER.exception('Error updating xeng qdr sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_xeng_qdr_okay ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _xeng_qdr_okay, sensor, executor, x_host)


@tornado.gen.coroutine
def _feng_qdr_okay(sensor, executor, f_host):
    """
    f-engine QDR check
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.qdr_okay)
    except Exception as e:
        LOGGER.exception('Error updating feng qdr sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_feng_qdr_okay ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _feng_qdr_okay, sensor, executor, f_host)


@tornado.gen.coroutine
def _feng_pfb_okay(sensor, executor, f_host):
    """
    f-engine PFB check
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_fft_overflow)
    except Exception as e:
        LOGGER.exception('Error updating feng pfb sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_feng_pfb_okay ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _feng_pfb_okay, sensor, executor, f_host)


@tornado.gen.coroutine
def _fhost_check_10gbe_rx(sensor, executor, f_host):
    """
    Check that the f-hosts are receiving data correctly
    :param sensor:
    :param executor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_rx_raw, 0.2, 5)
    except Exception as e:
        LOGGER.exception('Error updating {} for {} - '
                         '{}'.format(sensor.name, f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_fhost_check_10gbe_rx ran')
    IOLoop.current().call_later(10, _fhost_check_10gbe_rx, sensor,
                                executor, f_host)


@tornado.gen.coroutine
def _fhost_check_10gbe_tx(sensor, executor, f_host):
    """
    Check that the f-hosts are sending data correctly
    :param sensor:
    :param executor:
    :param f_host:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_tx_raw, 0.2, 5)
    except Exception as e:
        LOGGER.exception('Error updating {} for {} - '
                         '{}'.format(sensor.name, f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_fhost_check_10gbe_tx ran')
    IOLoop.current().call_later(10, _fhost_check_10gbe_tx, sensor,
                                executor, f_host)


@tornado.gen.coroutine
def _xhost_check_10gbe_rx(sensor, executor, x_host):
    """
    Check that the x-hosts are receiving data correctly
    :param sensor:
    :param executor:
    :param x_host:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.check_rx_raw, 0.2, 5)
    except Exception as e:
        LOGGER.exception('Error updating {} for {} - '
                         '{}'.format(sensor.name, x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_xhost_check_10gbe_rx ran')
    IOLoop.current().call_later(10, _xhost_check_10gbe_rx, sensor,
                                executor, x_host)


@tornado.gen.coroutine
def _xhost_report_10gbe_tx(sensor, executor, x_host, gbe):
    """
    Check that the x-hosts are sending data correctly
    :param sensor:
    :param executor:
    :param x_host:
    :param gbe:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(
            x_host.registers['%s_txctr' % gbe.name].read)
    except Exception as e:
        LOGGER.exception('Error updating {} for {} - '
                         '{}'.format(sensor.name, x_host, e.message))
    result = result['data']['reg']
    sensor.set(time.time(), Sensor.NOMINAL, result)
    LOGGER.debug('_xhost_report_10gbe_tx ran')
    IOLoop.current().call_later(10, _xhost_report_10gbe_tx, sensor,
                                executor, x_host, gbe)


@tornado.gen.coroutine
def _sensor_feng_rx_reorder(sensor, executor, f_host):
    """
    f-engine rx counters
    :param sensor:
    :return: true/false
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_rx_reorder)
    except Exception as e:
        LOGGER.exception('Error updating feng_rx sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_feng_rx ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_rx_reorder,
                                sensor, executor, f_host)


@tornado.gen.coroutine
def _sensor_xeng_rx_reorder(sensor, executor, x_host):
    """
    x-engine rx counters
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.check_rx_reorder)
    except Exception as e:
        LOGGER.exception('Error updating xeng_rx sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_xeng_rx ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_rx_reorder, sensor,
                                executor, x_host)


@tornado.gen.coroutine
def _sensor_cb_system_counters(executor, host, instrument):
    """
    Read all specified counters on this host.
    :param executor:
    :param host:
    :param instrument:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(read_all_counters, host)
    except Exception as e:
        LOGGER.exception('Error updating counter sensors for {} - '
                         '{}'.format(host, e.message))
    for sens_name in result:
        sensor = instrument.sensors_get(sens_name)
        oldval = instrument.sensors_counters_values[sens_name]
        sens_value = result[sens_name] != oldval
        sensor.set(time.time(), Sensor.NOMINAL, sens_value)
    instrument.sensors_counters_values.update(result)
    IOLoop.current().call_later(10, _sensor_cb_system_counters,
                                executor, host, instrument)


def setup_sensors(instrument, katcp_server):
    """
    Set up compound sensors to be reported to CAM
    :param instrument: the corr2.Instrument these sensors act upon
    :param katcp_server: the katcp server with which to register the sensors
    :return:
    """

    # Set up a 1-worker pool per host to serialise interactions with each host
    host_executors = {
        host.host: futures.ThreadPoolExecutor(max_workers=1)
        for host in instrument.fhosts + instrument.xhosts
    }
    general_executor = futures.ThreadPoolExecutor(max_workers=1)

    if not instrument.initialised():
        raise RuntimeError('Cannot set up sensors until instrument is '
                           'initialised.')

    ioloop = getattr(instrument, 'ioloop', None)
    if not ioloop:
        ioloop = getattr(katcp_server, 'ioloop', None)
    if not ioloop:
        raise RuntimeError('IOLoop-containing katcp version required. Can go '
                           'no further.')

    instrument.sensors_clear()

    # f-engine received timestamps
    sensor = Sensor.boolean(
        name='feng_rxtime',
        description='Are the times received by f-engines in the system okay',
        default=False)

    katcp_server.add_sensor(sensor)
    instrument.sensors_add(sensor)
    ioloop.add_callback(_sensor_cb_feng_rxtime, sensor, general_executor,
                        instrument)

    # f-engine lru
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_lru' % _f.host,
            description='F-engine %s LRU okay' % _f.host,
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_cb_flru, sensor, executor, _f)

    # x-engine lru
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_lru' % _x.host,
            description='X-engine %s LRU okay' % _x.host,
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_cb_xlru, sensor, executor, _x)

    # x-engine QDR errors
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_qdr' % _x.host,
            description='X-engine QDR okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_xeng_qdr_okay, sensor, executor, _x)

    # f-engine QDR errors
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_qdr' % _f.host,
            description='F-engine QDR okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_feng_qdr_okay, sensor, executor, _f)

    # x-engine PHY counters
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_phy' % _x.host,
            description='X-engine PHY okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_xeng_phy, sensor, executor, _x)

    # f-engine PHY counters
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_phy' % _f.host,
            description='F-engine PHY okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_feng_phy, sensor, executor, _f)

    # f-engine PFB counters
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_pfb' % _f.host,
            description='F-engine PFB okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_feng_pfb_okay, sensor, executor, _f)

    # f-engine raw rx - tengbe counters must increment
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_10gbe_rx' % _f.host,
            description='F-engine 10gbe RX okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_fhost_check_10gbe_rx, sensor, executor, _f)

    # f-engine raw tx - tengbe counters must increment
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_10gbe_tx' % _f.host,
            description='F-engine 10gbe TX okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_fhost_check_10gbe_tx, sensor, executor, _f)

    # x-engine raw rx - tengbe counters must increment
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_10gbe_rx' % _x.host,
            description='X-engine 10gbe RX okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_xhost_check_10gbe_rx, sensor, executor, _x)

    # x-engine raw tx - report tengbe counters
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        for gbe in _x.tengbes:
            sensor = Sensor.integer(
                name='%s_xeng_10gbe_%s_tx' % (_x.host, gbe.name),
                description='X-engine 10gbe TX counter',
                default=True)
            katcp_server.add_sensor(sensor)
            instrument.sensors_add(sensor)
            ioloop.add_callback(_xhost_report_10gbe_tx, sensor,
                                executor, _x, gbe)

    # f-engine rx reorder counters
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_reorder_rx' % _f.host,
            description='F-engine RX okay - reorder counters incrementing'
                        'correctly',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_feng_rx_reorder, sensor, executor, _f)

    # x-engine rx reorder counters
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_reorder_rx' % _x.host,
            description='X-engine RX okay - reorder counters incrementing'
                        'correctly',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_xeng_rx_reorder,  sensor, executor, _x)

    # f-engine delay functionality
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_delays' % _f.host,
            description='F-engine %s delay functionality' % _f.host,
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_cb_fdelays, sensor, executor, _f)

    # read all relevant counters
    instrument.sensors_counters_values = {}
    for _h in instrument.fhosts + instrument.xhosts:
        executor = host_executors[_h.host]
        host_ctrs = read_all_counters(_h)
        for ctr in host_ctrs:
            sensor = Sensor.boolean(
                name='%s' % ctr,
                description='Counter on %s, True is changed since '
                            'last read' % _h.host,
                default=False)
            katcp_server.add_sensor(sensor)
            instrument.sensors_add(sensor)
        instrument.sensors_counters_values.update(host_ctrs)
        ioloop.add_callback(_sensor_cb_system_counters, executor,
                            _h, instrument)

# end
