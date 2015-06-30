from katcp import Sensor
from tornado.ioloop import IOLoop
import time

def _sensor_cb_flru(instr, sensor):
    """
    Sensor call back function for f-engine LRU
    :param sensor:
    :return:
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _fhost in instr.fhosts:
        if _fhost.host == host_name:
            result = _fhost.host_okay()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_sensor_cb_flru ran on {}'.format(host_name))
    IOLoop.current().call_later(10, _sensor_cb_flru, instr, sensor)

def _sensor_cb_xlru(instr, sensor):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _xhost in instr.xhosts:
        if _xhost.host == host_name:
            result = _xhost.host_okay()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_sensor_cb_xlru ran on {}'.format(host_name))
    IOLoop.current().call_later(10, _sensor_cb_xlru, instr, sensor)

def _sensor_feng_tx(instr, sensor):
    """
    f-engine tx counters
    :param sensor:
    :return: rv
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _fhost in instr.fhosts:
        if _fhost.host == host_name:
            result = _fhost.tengbes.tx_okay()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_sensor_feng_tx ran on %s' % (host_name))
    IOLoop.current().call_later(10, _sensor_feng_tx, instr, sensor)

def _sensor_feng_rx(instr, sensor):
    """
    f-engine rx counters
    :param sensor:
    :return: true/false
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _fhost in instr.fhosts:
        if _fhost.host == host_name:
            result = _fhost.check_rx_reorder()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_sensor_feng_rx ran on %s' % (host_name))
    IOLoop.current().call_later(10, _sensor_feng_rx, instr, sensor)

def _sensor_xeng_tx(instr, sensor):
    """
    x-engine tx counters
    :param sensor:
    :return:
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _xhost in instr.xhosts:
        if _xhost.host == host_name:
            result = _xhost.tengbes.tx_okay()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_sensor_xeng_tx ran on %s' % (host_name))
    IOLoop.current().call_later(10, _sensor_xeng_tx, instr, sensor)

def _sensor_xeng_rx(instr, sensor):
    """
    x-engine rx counters
    :param sensor:
    :return:
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _xhost in instr.xhosts:
        if _xhost.host == host_name:
            result = _xhost.check_rx_reorder()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_sensor_xeng_rx ran on %s' % (host_name))
    IOLoop.current().call_later(10, _sensor_xeng_rx, instr, sensor)

def _sensor_feng_phy(instr, sensor):
    """
    f-engine PHY counters
    :param sensor:
    :return:
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _fhost in instr.fhosts:
        if _fhost.host == host_name:
            result = _fhost.check_phy_counter()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_sensor_feng_phy ran on %s' % host_name)
    IOLoop.current().call_later(10, _sensor_feng_phy, instr, sensor)

def _sensor_xeng_phy(instr, sensor):
    """
    x-engine PHY counters
    :param sensor:
    :return:
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _xhost in instr.xhosts:
        if _xhost.host == host_name:
            result = _xhost.check_phy_counter()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_sensor_xeng_phy ran on %s' % host_name)
    IOLoop.current().call_later(10, _sensor_xeng_phy, instr, sensor)

def _xeng_qdr_okay(instr, sensor):
    """
    x-engine QDR check
    :param sensor:
    :return:
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _xhost in instr.xhosts:
        if _xhost.host == host_name:
            result = _xhost.qdr_okay()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_xeng_qdr_okay ran on %s' % host_name)
    IOLoop.current().call_later(10, _xeng_qdr_okay, instr, sensor)

def _feng_qdr_okay(instr, sensor):
    """
    f-engine QDR check
    :param sensor:
    :return:
    """
    host_name = sensor.name.split('_')[2]
    result = False
    for _fhost in instr.fhosts:
        if _fhost.host == host_name:
            result = _fhost.qdr_okay()
    sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
    instr.logger.info('_feng_qdr_okay ran on %s' % host_name)
    IOLoop.current().call_later(10, _feng_qdr_okay, instr, sensor)

def setup_sensors(instrument, katcp_server):
    """
    Set up compound sensors to be reported to CAM
    :param katcp_server: the katcp server with which to register the sensors
    :return:
    """
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
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_lru_%s' % _f.host,
                        description='F-engine %s LRU okay' % _f.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_cb_flru, instrument, sensor)

    # x-engine lru
    for _x in self.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_lru_%s' % _x.host,
                        description='X-engine %s LRU okay' % _x.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_cb_xlru, instrument, sensor)

#     # self._sensors = {'time': Sensor(sensor_type=Sensor.FLOAT, name='time_sensor', description='The time.',
#     #                                units='s', params=[-(2**64), (2**64)-1], default=-1),
#     #                 'test': Sensor(sensor_type=Sensor.INTEGER, name='test_sensor',
#     #                                description='A sensor for Marc to test.',
#     #                                units='mPa', params=[-1234, 1234], default=555),
#     #                 'meta_dest': Sensor(sensor_type=Sensor.STRING, name='meta_dest',
#     #                                     description='The meta dest string',
#     #                                     units='', default=str(self.meta_destination))
#     #                 }

    # f-engine tx counters
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_tx_%s' % _f.host,
                        description='F-engine TX okay - counters incrementing' % _f.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_feng_tx, instrument, sensor)

    # f-engine rx counters
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_rx_%s' % _f.host,
                        description='F-engine %s RX okay - counters incrementing' % _f.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_feng_rx, instrument, sensor)

    # x-engine tx counters
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_tx_%s' % _x.host,
                        description='X-engine TX okay - counters incrementing' % _x.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_xeng_tx, instrument, sensor)

    # x-engine rx counters
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_rx_%s' % _x.host,
                        description='X-engine RX okay - counters incrementing' % _x.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_xeng_rx, instrument, sensor)

    # x-engine QDR errors
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_qdr_%s' % _x.host,
                        description='X-engine QDR okay' % _x.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_xeng_qdr_okay, instrument, sensor)

    # f-engine QDR errors
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_qdr_%s' % _f.host,
                        description='F-engine QDR okay' % _f.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_feng_qdr_okay, instrument, sensor)

    # x-engine PHY counters
    for _x in instrument.xhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_PHY_%s' % _x.host,
                        description='X-engine PHY okay' % _x.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_xeng_phy, instrument, sensor)

    # f-engine PHY counters
    for _f in instrument.fhosts:
        sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_PHY_%s' % _f.host,
                        description='F-engine PHY okay' % _f.host,
                        default=True)
        katcp_server.add_sensor(sensor)
        instrument._sensors[sensor.name] = sensor
        ioloop.add_callback(_sensor_feng_phy, instrument, sensor)
