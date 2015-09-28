import time
import tornado.gen

from katcp import Sensor
from tornado.ioloop import IOLoop
from concurrent import futures


@tornado.gen.coroutine
def _sensor_cb_flru(instr, sensor, executor, f_host):
    """
    Sensor call back function for f-engine LRU
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.host_okay)
    except Exception:
        instr.logger.exception('Exception updating flru sensor for {}'.format(f_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_sensor_cb_flru ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_cb_flru, instr, sensor, executor, f_host)

@tornado.gen.coroutine
def _sensor_cb_xlru(instr, sensor, executor, x_host):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.host_okay)
    except Exception:
        instr.logger.exception('Exception updating xlru sensor for {}'.format(x_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_sensor_cb_xlru ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_cb_xlru, instr, sensor, executor, x_host)

@tornado.gen.coroutine
def _sensor_feng_tx(instr, sensor, executor, f_host):
    """
    f-engine tx counters
    :param sensor:
    :return: rv
    """
    result = False
    try:
        for tengbe in f_host.tengbes:
            result &= yield executor.submit(tengbe.tx_okay)
    except Exception:
        instr.logger.exception('Exception updating feng_tx sensor for {}'.format(f_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_sensor_feng_tx ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_tx, instr, sensor, executor, f_host)

@tornado.gen.coroutine
def _sensor_feng_rx(instr, sensor, executor, f_host):
    """
    f-engine rx counters
    :param sensor:
    :return: true/false
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_rx_reorder)
    except Exception:
        instr.logger.exception('Exception updating feng_rx sensor for {}'.format(f_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_sensor_feng_rx ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_rx, instr, sensor, executor, f_host)

@tornado.gen.coroutine
def _sensor_xeng_tx(instr, sensor, executor, x_host):
    """
    x-engine tx counters
    :param sensor:
    :return:
    """
    result = False
    try:
        for tengbe in x_host.tengbes:
            result &= yield executor.submit(tengbe.tx_okay)
    except Exception:
        instr.logger.exception('Exception updating xeng_tx sensor for {}'.format(x_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_sensor_xeng_tx ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_tx, instr, sensor, executor, x_host)

@tornado.gen.coroutine
def _sensor_xeng_rx(instr, sensor, executor, x_host):
    """
    x-engine rx counters
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.check_rx_reorder)
    except Exception:
        instr.logger.exception('Exception updating xeng_rx sensor for {}'.format(x_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_sensor_xeng_rx ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_rx, instr, sensor, executor, x_host)

@tornado.gen.coroutine
def _sensor_feng_phy(instr, sensor, executor, f_host):
    """
    f-engine PHY counters
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_phy_counter)
    except Exception:
        instr.logger.exception('Exception updating feng_phy sensor for {}'.format(f_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_sensor_feng_phy ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_phy, instr, sensor, executor, f_host)

@tornado.gen.coroutine
def _sensor_xeng_phy(instr, sensor, executor, x_host):
    """
    x-engine PHY counters
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.check_phy_counter)
    except Exception:
        instr.logger.exception('Exception updating xeng_phy sensor for {}'.format(x_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_sensor_xeng_phy ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_phy, instr, sensor, executor, x_host)

@tornado.gen.coroutine
def _xeng_qdr_okay(instr, sensor, executor, x_host):
    """
    x-engine QDR check
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(x_host.qdr_okay)
    except Exception:
        instr.logger.exception('Exception updating xeng qdr sensor for {}'.format(x_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_xeng_qdr_okay ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _xeng_qdr_okay, instr, sensor, executor, x_host)

@tornado.gen.coroutine
def _feng_qdr_okay(instr, sensor, executor, f_host):
    """
    f-engine QDR check
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.qdr_okay)
    except Exception:
        instr.logger.exception('Exception updating feng qdr sensor for {}'.format(f_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_feng_qdr_okay ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _feng_qdr_okay, instr, sensor, executor, f_host)

def _feng_pfb_okay(instr, sensor, executor, f_host):
    """
    f-engine PFB check
    :param sensor:
    :return:
    """
    result = False
    try:
        result = yield executor.submit(f_host.check_fft_overflow)
    except Exception:
        instr.logger.exception('Exception updating feng pfb sensor for {}'.format(f_host))
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.debug('_feng_pfb_okay ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _feng_pfb_okay, instr, sensor, executor, f_host)

def setup_sensors(instrument, katcp_server):
    """
    Set up compound sensors to be reported to CAM
    :param katcp_server: the katcp server with which to register the sensors
    :return:
    """

    nr_engines = len(instrument.fhosts + instrument.xhosts)
    executor = futures.ThreadPoolExecutor(max_workers=nr_engines)
    if not instrument._initialised:
        raise RuntimeError('Cannot set up sensors until instrument is initialised.')

    ioloop = getattr(instrument, 'ioloop', None)
    if not ioloop:
        ioloop = getattr(katcp_server, 'ioloop', None)
    if not ioloop:
        raise RuntimeError('IOLoop-containing katcp version required. Can go no further.')

    instrument._sensors = {}

    # f-engine lru
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_feng_lru' % _f.host,
                        description='F-engine %s LRU okay' % _f.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_cb_flru, instrument, sensor, executor, _f)

    # x-engine lru
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_xeng_lru' % _x.host,
                        description='X-engine %s LRU okay' % _x.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_cb_xlru, instrument, sensor, executor, _x)

    # self._sensors = {'time': Sensor(sensor_type=Sensor.FLOAT, name='time_sensor', description='The time.',
    #                                units='s', params=[-(2**64), (2**64)-1], default=-1),
    #                 'test': Sensor(sensor_type=Sensor.INTEGER, name='test_sensor',
    #                                description='A sensor for Marc to test.',
    #                                units='mPa', params=[-1234, 1234], default=555),
    #                 'meta_dest': Sensor(sensor_type=Sensor.STRING, name='meta_dest',
    #                                     description='The meta dest string',
    #                                     units='', default=str(self.meta_destination))
    #                 }

    # f-engine tx counters
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_feng_tx' % _f.host,
                        description='F-engine TX okay - counters incrementing',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_feng_tx, instrument, sensor, executor, _f)

    # f-engine rx counters
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_feng_rx' % _f.host,
                        description='F-engine RX okay - counters incrementing',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_feng_rx, instrument, sensor, executor, _f)

    # x-engine tx counters
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_xeng_tx' % _x.host,
                        description='X-engine TX okay - counters incrementing',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_xeng_tx, instrument, sensor, executor, _x)

    # x-engine rx counters
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_xeng_rx' % _x.host,
                        description='X-engine RX okay - counters incrementing',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_xeng_rx, instrument, sensor, executor, _x)

    # x-engine QDR errors
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_xeng_qdr' % _x.host,
                        description='X-engine QDR okay',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_xeng_qdr_okay, instrument, sensor, executor, _x)

    # f-engine QDR errors
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_feng_qdr' % _f.host,
                        description='F-engine QDR okay',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_feng_qdr_okay, instrument, sensor, executor, _f)

    # x-engine PHY counters
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_xeng_phy' % _x.host,
                        description='X-engine PHY okay',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_xeng_phy, instrument, sensor, executor, _x)

    # f-engine PHY counters
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_feng_phy' % _f.host,
                        description='F-engine PHY okay',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_feng_phy, instrument, sensor, executor, _f)

    # f-engine PFB counters
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='%s_feng_pfb' % _f.host,
                        description='F-engine PFB okay',
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_feng_pfb_okay, instrument, sensor, executor, _f)
