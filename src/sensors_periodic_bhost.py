import logging
import tornado.gen as gen
from tornado.ioloop import IOLoop

import sys
import traceback as tb

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid

from sensors import Corr2Sensor, boolean_sensor_do

LOGGER = logging.getLogger(__name__)

host_offset_lookup = {}
sensor_poll_time = 10


@gen.coroutine
def _cb_bhost_lru(sensor_manager, sensor, b_host):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
    #TODO - just copied from _cb_xhost_lru function, need to update.
    # try:
    #     h = host_offset_lookup[b_host.host]
    #     # Pdb().set_trace()
    #     status = Corr2Sensor.NOMINAL
    #     for xctr in range(b_host.x_per_fpga):
    #         pref = '{bhost}.beng{xctr}'.format(bhost=h, xctr=xctr)
    #         eng_status = Corr2Sensor.NOMINAL
    #         if sensor_manager.sensor_get(
    #                 "{}.vacc.device-status".format(pref)).status() == Corr2Sensor.ERROR:
    #             status = Corr2Sensor.ERROR
    #             eng_status = Corr2Sensor.ERROR
    #         elif sensor_manager.sensor_get("{}.bram-reorder.device-status".format(pref)).status() == Corr2Sensor.ERROR:
    #             status = Corr2Sensor.ERROR
    #             eng_status = Corr2Sensor.ERROR
    #         sens_val = (eng_status == Corr2Sensor.NOMINAL)
    #         sensor_manager.sensor_get(
    #             "{}.device-status".format(pref)).set(value=sens_val, status=eng_status)
    #
    #     if sensor_manager.sensor_get(
    #             "{}.network.device-status".format(h)).status() == Corr2Sensor.ERROR:
    #         status = Corr2Sensor.ERROR
    #     elif sensor_manager.sensor_get("{}.network-reorder.device-status".format(h)).status() == Corr2Sensor.ERROR:
    #         status = Corr2Sensor.ERROR
    #     elif sensor_manager.sensor_get("{}.network.device-status".format(h)).status() == Corr2Sensor.WARN:
    #         status = Corr2Sensor.WARN
    #     elif sensor_manager.sensor_get("{}.network-reorder.device-status".format(h)).status() == Corr2Sensor.WARN:
    #         status = Corr2Sensor.WARN
    #     sens_val = (status == Corr2Sensor.NOMINAL)
    #     sensor.set(value=sens_val, status=status)
    # except Exception as e:
    #     LOGGER.error(
    #         'Error updating LRU sensor for {} - {}'.format(
    #             b_host.host, e.message))
    #     sensor.set(value=False, status=Corr2Sensor.FAILURE)
    #
    # LOGGER.debug('_cb_xhost_lru ran on {}'.format(b_host.host))
    # IOLoop.current().call_later(
    #     sensor_poll_time,
    #     _cb_xhost_lru,
    #     sensor_manager,
    #     sensor,
    #     b_host)


@gen.coroutine
def _cb_beng_pack(sensors, general_executor, sens_man):
    """

    :param sensors: all sensors for all bengine pack blocks, a nested list of dictionaries.
    :return:
    """
    value = 'ok'
    status = Corr2Sensor.NOMINAL

    try:

        executor = general_executor
        rv = []
#TODO: swap beam vs host order.
#        for beam_no in xrange(len(sens_man.instrument.bops.beams)):
#            beam_sensors = []
#            for bhost in sens_man.instrument.xhosts:
#                beam_sensors.append(bhost.get_bpack_status(beam_no))
#            rv.append((beam_sensors))
#
#        for beam_no, beam_sensors in enumerate(sensors):
#            for bhost_no, bhost_sensors in enumerate(beam_sensors):
#                for beng_no, beng_sensors in enumerate(bhost_sensors):
#                    for key in ['fifo_of_err_cnt', 'pkt_cnt']:
#                        if 'err_cnt' in key:
#                            beng_sensors[key].set(value=rv[beam_no][bhost_no][beng_no][key], errif='changed')
#                        else:
#                            beng_sensors[key].set(value=rv[beam_no][bhost_no][beng_no][key], errif='notchanged')
#                        if beng_sensors[key].status() == Corr2Sensor.ERROR:
#                            status = Corr2Sensor.ERROR
#                            value = 'fail'
#                    beng_sensors['device_status'].set(value=value, status=status)
#
    except Exception as e:
        #TODO This logger stuff doesn't seem to actually work. Not sure why.
        LOGGER.error('Error updating beng pack sensors - '
                     '{}'.format(e.message))
    IOLoop.current().call_later(sensor_poll_time, _cb_beng_pack, sensors, general_executor, sens_man)


def setup_sensors_bengine(sens_man, general_executor, host_executors, ioloop,
                          host_offset_dict):
    """
    Set up the B-engine specific sensors.
    :param sens_man:
    :param general_executor:
    :param host_executors:
    :param ioloop:
    :param host_offset_dict:
    :return: none
    """
    #TODO: update the docstring once it's clearly understood what everything actually *does*.

    global host_offset_lookup
    global sensor_poll_time
    sensor_poll_time = sens_man.instrument.sensor_poll_time
    if len(host_offset_lookup) == 0:
        host_offset_lookup = host_offset_dict.copy()

    # Beng Packetiser block

    # passes beam_sensors object to the ioloop to be populated by _cb_beng_pack
    # format is a nested list:
    # [ per beam
    #   [ per host
    #       [ per beng
    #           {sensors: name:sensor-object}
    #       ]
    #   ]
    # ]
    beam_pack_sensors = []
#TODO: swap beam and host around:
#    for beamctr in range(len(sens_man.instrument.bops.beams)):
#        bhost_pack_sensors = []
#        for _b in sens_man.instrument.xhosts:
#            executor = general_executor
#            bhost = host_offset_lookup[_b.host]
#            beng_pack_sensors = []
#            for bengctr in range(_b.x_per_fpga):
#                # TODO: This reports the hosts as xhosts. Should the sensor report them as bhosts?
#                pref = 'beam{beamctr}.{bhost}.beng{bengctr}.spead-tx'.format(beamctr=beamctr, bhost=bhost, bengctr=bengctr)
#                sensordict = {
#                    'device_status': sens_man.do_sensor(
#                        Corr2Sensor.device_status,
#                        '{}.device-status'.format(pref),
#                        'B-engine pack (TX) status',
#                        executor=executor),
#                    'fifo_of_err_cnt': sens_man.do_sensor(
#                        Corr2Sensor.integer,
#                        '{}.fifo-of-err-cnt'.format(pref),
#                        'B-engine pack (TX) FIFO overflow error count',
#                        executor=executor),
#                    'pkt_cnt': sens_man.do_sensor(
#                        Corr2Sensor.integer,
#                        '{}.pkt-cnt'.format(pref),
#                        'B-engine pack (TX) packet count',
#                        executor=executor)}
#                beng_pack_sensors.append(sensordict)
#            bhost_pack_sensors.append(beng_pack_sensors)
#        beam_pack_sensors.append(bhost_pack_sensors)
#    ioloop.add_callback(_cb_beng_pack, beam_pack_sensors, general_executor, sens_man)

    # LRU ok
    # beam.host.engine
    #A sensor for the overall health of each beam. --> NO!
    #A sensor for the overall health of each LRU (host). --> for now, only Beng parts
    #A sensor for the overall health of each engine. --> for now, only beng parts.
#    sensor = sens_man.do_sensor(
#        Corr2Sensor.device_status, '{}.device-status'.format(bhost),
#        'B-engine %s LRU ok' % _b.host, executor=executor)
#    beam_lru_sensors = []
#    for beamctr in range(len(sens_man.instrument.bops.beams)):
#        bhost_lru_sensors = []
#        for _b in sens_man.instrument.xhosts:
#            executor = general_executor
#            bhost = host_offset_lookup[_b.host]
#            beng_lru_sensors = []
#            for bengctr in range(_b.x_per_fpga):
#                pref = 'beam{beamctr}.{bhost}.beng{bengctr}'.format(beamctr=beamctr, bhost=bhost, bengctr=bengctr)
#                beng_lru_sensors.append(sens_man.do_sensor(
#                    Corr2Sensor.boolean,
#                    '{}.device-status'.format(pref),
#                    'B-engine core status'))
#            bhost_lru_sensors.append(beng_lru_sensors)
#        beam_lru_sensors.append(bhost_lru_sensors)
#    ioloop.add_callback(_cb_bhost_lru, beam_lru_sensors, sens_man)
