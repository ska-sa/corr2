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


# def _sensor_cb_xlru(self, sensor):
#     """
#     Sensor call back function for x-engine LRU
#     :param sensor:
#     :return:
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.xhosts[host_name].host_okay()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_sensor_cb_xlru ran on %s' % (host_name))
#     Timer(10, self._sensor_cb_xlru, sensor).start()
#
# def _sensor_feng_tx(self, sensor):
#     """
#     f-engine tx counters
#     :param sensor:
#     :return: rv
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.fhosts[host_name].tengbes.tx_okay()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_sensor_feng_tx ran on %s' % (host_name))
#     Timer(10, self._sensor_feng_tx, sensor).start()
#
# def _sensor_feng_rx(self, sensor):
#     """
#     f-engine rx counters
#     :param sensor:
#     :return: true/false
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.fhosts[host_name].check_rx_reorder()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_sensor_feng_rx ran on %s' % (host_name))
#     Timer(10, self._sensor_feng_rx, sensor).start()
#
# def _sensor_xeng_tx(self, sensor):
#     """
#     x-engine tx counters
#     :param sensor:
#     :return:
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.xhosts[host_name].tengbes.tx_okay()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_sensor_xeng_tx ran on %s' % (host_name))
#     Timer(10, self._sensor_xeng_tx, sensor).start()
#
# def _sensor_xeng_rx(self, sensor):
#     """
#     x-engine rx counters
#     :param sensor:
#     :return:
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.xhosts[host_name].check_rx_reorder()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_sensor_xeng_rx ran on %s' % (host_name))
#     Timer(10, self._sensor_xeng_rx, sensor).start()
#
# def _sensor_feng_phy(self, sensor):
#     """
#     f-engine PHY counters
#     :param sensor:
#     :return:
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.fhosts[host_name].check_phy_counter()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_sensor_feng_phy ran on %s' % host_name)
#     Timer(10, self._sensor_feng_phy, sensor).start()
#     return
#
# def _sensor_xeng_phy(self, sensor):
#     """
#     x-engine PHY counters
#     :param sensor:
#     :return:
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.xhosts[host_name].check_phy_counter()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_sensor_xeng_phy ran on %s' % host_name)
#     Timer(10, self._sensor_xeng_phy, sensor).start()
#     return
#
# def _xeng_qdr_okay(self, sensor):
#     """
#     x-engine QDR check
#     :param sensor:
#     :return:
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.xhosts[host_name].qdr_okay()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_xeng_qdr_okay ran on %s' % host_name)
#     Timer(10, self._xeng_qdr_okay, sensor).start()
#     return
#
# def _feng_qdr_okay(self, sensor):
#     """
#     f-engine QDR check
#     :param sensor:
#     :return:
#     """
#     host_name = sensor.name.split('_')[2]
#     result = self.fhosts[host_name].qdr_okay()
#     sensor.set(time.time(), Sensor.NOMINAL if result else Sensor.ERROR, result)
#     self.logger.info('_feng_qdr_okay ran on %s' % host_name)
#     IOLoop.instance().call_later(self._feng_qdr_okay, 10)
#     return

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

#     # x-engine lru
# =======
#         sensor.set(time.time(),
#                    Sensor.NOMINAL if okay_res[_f.host] else Sensor.ERROR,
#                    okay_res[_f.host])
#         self._sensors[sensor.name] = sensor
#     okay_res = THREADED_FPGA_FUNC(self.xhosts, timeout=5, target_function='host_okay')
# >>>>>>> devel
#     for _x in self.xhosts:
#         sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_lru_%s' % _x.host,
#                         description='X-engine %s LRU okay' % _x.host,
#                         default=True)
# <<<<<<< HEAD
#         ioloop.add_callback(self._sensor_cb_xlru, sensor)  # call back function
# =======
#         sensor.set(time.time(),
#                    Sensor.NOMINAL if okay_res[_x.host] else Sensor.ERROR,
#                    okay_res[_x.host])
# >>>>>>> devel
#         self._sensors[sensor.name] = sensor
#
#     # self._sensors = {'time': Sensor(sensor_type=Sensor.FLOAT, name='time_sensor', description='The time.',
#     #                                units='s', params=[-(2**64), (2**64)-1], default=-1),
#     #                 'test': Sensor(sensor_type=Sensor.INTEGER, name='test_sensor',
#     #                                description='A sensor for Marc to test.',
#     #                                units='mPa', params=[-1234, 1234], default=555),
#     #                 'meta_dest': Sensor(sensor_type=Sensor.STRING, name='meta_dest',
#     #                                     description='The meta dest string',
#     #                                     units='', default=str(self.meta_destination))
#     #                 }
#
#     # f-engine tx counters
#     for _f in self.fhosts:
#         sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_tx_%s' % _f.host,
#                         description='F-engine TX okay - counters incrementing' % _f.host,
#                         default=True)
#         self._sensor_feng_rx(sensor)
#         self._sensors[sensor.name] = sensor
#
#     # f-engine rx counters
#     for _f in self.fhosts:
#         sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_rx_%s' % _f.host,
#                         description='F-engine %s RX okay - counters incrementing' % _f.host,
#                         default=True)
#         self._sensor_feng_rx(sensor)
#         self._sensors[sensor.name] = sensor
#
#     # x-engine tx counters
#     sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_tx',
#                     description='X-engine TX okay - counters incrementing',
#                     default=True)
#     self._sensor_xeng_rx(sensor)
#     self._sensors[sensor.name] = sensor
#
#     # x-engine rx counters
#     for _x in self.xhosts:
#         sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_rx_%s' % _x.host,
#                         description='X-engine RX okay - counters incrementing' % _x.host,
#                         default=True)
#         self._sensor_xeng_rx(sensor)
#         self._sensors[sensor.name] = sensor
#
#     # # x-engine QDR errors
#     for _x in self.xhosts:
#         sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_qdr_%s' % _x.host,
#                         description='X-engine QDR okay' % _x.host,
#                         default=True)
#         self._xeng_qdr_okay(sensor)
#         self._sensors[sensor.name] = sensor
#
#     # # f-engine QDR errors
#     for _f in self.fhosts:
#         sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_qdr_%s' % _f.host,
#                         description='F-engine QDR okay' % _f.host,
#                         default=True)
#         self._feng_qdr_okay(sensor)
#         self._sensors[sensor.name] = sensor
#
#     # # x-engine PHY counters
#     for _x in self.xhosts:
#         sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='xeng_PHY_%s' % _x.host,
#                         description='X-engine PHY okay' % _x.host,
#                         default=True)
#         self._sensor_xeng_phy(sensor)
#         self._sensors[sensor.name] = sensor
#
#     # # f-engine PHY counters
#     for _f in self.fhosts:
#         sensor = Sensor(sensor_type=Sensor.BOOLEAN, name='feng_PHY_%s' % _f.host,
#                         description='F-engine PHY okay' % _f.host,
#                         default=True)
#         self._sensor_feng_phy(sensor)
#         self._sensors[sensor.name] = sensor
#
#     for val in self._sensors.values():
#         katcp_server.add_sensor(val)
#     Timer(self.sensor_poll_time, self._update_sensors).start()
#