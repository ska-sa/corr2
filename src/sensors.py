import logging
import time
import tornado.gen

from katcp import Sensor
from tornado.ioloop import IOLoop
from concurrent import futures

LOGGER = logging.getLogger(__name__)


@tornado.gen.coroutine
def _sensor_cb_fdelays(sensor, executor, f_host):
    """
    Sensor call back function for f-engine delay functionality
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_delays)
    except Exception as e:
        LOGGER.exception('Exception updating delay functionality sensor '
                         'for {} - {}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
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
        LOGGER.exception('Exception updating flru sensor for {} - '
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
        LOGGER.exception('Exception updating xlru sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_cb_xlru ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_cb_xlru, sensor, executor, x_host)


@tornado.gen.coroutine
def _sensor_feng_tx(sensor, executor, f_host):
    """
    f-engine tx counters
    :param sensor:
    :return: rv
    """
    result = False
    try:
        for tengbe in f_host.tengbes:
            result &= yield executor.submit(tengbe.tx_okay)
    except Exception as e:
        LOGGER.exception('Exception updating feng_tx sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_feng_tx ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_tx, sensor, executor, f_host)


@tornado.gen.coroutine
def _sensor_feng_rx(sensor, executor, f_host):
    """
    f-engine rx counters
    :param sensor:
    :return: true/false
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_rx_reorder)
    except Exception as e:
        LOGGER.exception('Exception updating feng_rx sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_feng_rx ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_rx, sensor, executor, f_host)


@tornado.gen.coroutine
def _sensor_xeng_tx(sensor, executor, x_host):
    """
    x-engine tx counters
    :param sensor:
    :return:
    """
    result = False
    try:
        for tengbe in x_host.tengbes:
            result &= yield executor.submit(tengbe.tx_okay)
    except Exception as e:
        LOGGER.exception('Exception updating xeng_tx sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_xeng_tx ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_tx, sensor, executor, x_host)


@tornado.gen.coroutine
def _sensor_xeng_rx(sensor, executor, x_host):
    """
    x-engine rx counters
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.check_rx_reorder)
    except Exception as e:
        LOGGER.exception('Exception updating xeng_rx sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_sensor_xeng_rx ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_rx, sensor, executor, x_host)


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
        LOGGER.exception('Exception updating feng_phy sensor for {} - '
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
        LOGGER.exception('Exception updating xeng_phy sensor for {} - '
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
        LOGGER.exception('Exception updating xeng qdr sensor for {} - '
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
        LOGGER.exception('Exception updating feng qdr sensor for {} - '
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
        LOGGER.exception('Exception updating feng pfb sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_feng_pfb_okay ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _feng_pfb_okay, sensor, executor, f_host)


@tornado.gen.coroutine
def _fhost_check_rx(sensor, executor, f_host):
    """
    Check that the f-hosts are receiving data correctly
    :param sensor:
    :param executor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_rx)
    except Exception as e:
        LOGGER.exception('Exception updating fhost rx sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_fhost_check_rx ran')
    IOLoop.current().call_later(10, _fhost_check_rx, sensor, executor, f_host)


@tornado.gen.coroutine
def _fhost_check_tx(sensor, executor, f_host):
    """
    Check that the f-hosts are sending data correctly
    :param sensor:
    :param executor:
    :param f_host:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_tx_raw)
    except Exception as e:
        LOGGER.exception('Exception updating fhost tx sensor for {} - '
                         '{}'.format(f_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_fhost_check_tx ran')
    IOLoop.current().call_later(10, _fhost_check_tx, sensor, executor, f_host)


@tornado.gen.coroutine
def _xhost_check_rx(sensor, executor, x_host):
    """
    Check that the x-hosts are receiving data correctly
    :param sensor:
    :param executor:
    :param x_host:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.check_rx)
    except Exception as e:
        LOGGER.exception('Exception updating xhost rx sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_xhost_check_rx ran')
    IOLoop.current().call_later(10, _xhost_check_rx, sensor, executor, x_host)


@tornado.gen.coroutine
def _xhost_check_tx(sensor, executor, x_host):
    """
    Check that the x-hosts are sending data correctly
    :param sensor:
    :param executor:
    :param x_host:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.check_tx_raw)
    except Exception as e:
        LOGGER.exception('Exception updating xhost tx sensor for {} - '
                         '{}'.format(x_host, e.message))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    LOGGER.debug('_xhost_check_tx ran')
    IOLoop.current().call_later(10, _xhost_check_tx, sensor, executor, x_host)


def setup_sensors(instrument, katcp_server):
    """
    Set up compound sensors to be reported to CAM
    :param katcp_server: the katcp server with which to register the sensors
    :return:
    """

    # Set up a 1-worker pool per host to serialise interactions with each host
    host_executors = {
        host.host: futures.ThreadPoolExecutor(max_workers=1)
        for host in instrument.fhosts + instrument.xhosts
    }

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

    # f-engine tx counters
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_tx' % _f.host,
            description='F-engine TX okay - counters incrementing',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_feng_tx, sensor, executor, _f)

    # f-engine rx counters
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_rx' % _f.host,
            description='F-engine RX okay - counters incrementing',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_feng_rx, sensor, executor, _f)

    # x-engine tx counters
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_tx' % _x.host,
            description='X-engine TX okay - counters incrementing',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_xeng_tx, sensor, executor, _x)

    # x-engine rx counters
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_rx' % _x.host,
            description='X-engine RX okay - counters incrementing',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_sensor_xeng_rx,  sensor, executor, _x)

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

    # f-engine comms rx
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_check_rx' % _f.host,
            description='F-engine RX path okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_fhost_check_rx, sensor, executor, _f)

    # f-engine comms tx
    for _f in instrument.fhosts:
        executor = host_executors[_f.host]
        sensor = Sensor.boolean(
            name='%s_feng_check_tx' % _f.host,
            description='F-engine TX okay transmitting packets without error',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_fhost_check_tx, sensor, executor, _f)

    # x-engine comms rx
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_check_rx' % _x.host,
            description='X-engine RX path okay',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_xhost_check_rx, sensor, executor, _x)

    # x-engine comms tx
    for _x in instrument.xhosts:
        executor = host_executors[_x.host]
        sensor = Sensor.boolean(
            name='%s_xeng_check_tx' % _x.host,
            description='X-engine TX okay transmitting packets without error',
            default=True)
        katcp_server.add_sensor(sensor)
        instrument.sensors_add(sensor)
        ioloop.add_callback(_xhost_check_tx, sensor, executor, _x)

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
