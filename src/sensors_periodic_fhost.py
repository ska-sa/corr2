import logging
import tornado.gen as gen

from tornado.ioloop import IOLoop

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid
from casperfpga.transport_skarab import \
    SkarabReorderError, SkarabReorderWarning, \
    SkarabSpeadError, SkarabSpeadWarning

from sensors import Corr2Sensor, boolean_sensor_do

LOGGER = logging.getLogger(__name__)

FHOST_REGS = ['spead_status', 'reorder_status', 'sync_ctrs', 'pfb_status', 
              'cd_status', 'quant_status']
FHOST_REGS.extend(['ct_status%i' % ctr for ctr in range(2)])
FHOST_REGS.extend(['gbe%i_txctr' % ctr for ctr in range(1)])
FHOST_REGS.extend(['gbe%i_txofctr' % ctr for ctr in range(1)])
FHOST_REGS.extend(['gbe%i_rxctr' % ctr for ctr in range(1)])
FHOST_REGS.extend(['gbe%i_rxofctr' % ctr for ctr in range(1)])
FHOST_REGS.extend(['gbe%i_rxbadctr' % ctr for ctr in range(1)])


@gen.coroutine
def _cb_feng_rxtime(sensor_ok, sensors_value):
    """
    Sensor call back to check received F-engine times
    :param sensor_ok: the combined times-are-ok sensor
    :param sensors_value: per-host sensors for time and unix-time
    :return:
    """
    executor = sensor_ok.executor
    instrument = sensor_ok.manager.instrument
    try:
        result, counts, times = yield executor.submit(
            instrument.fops.get_rx_timestamps)
        sensor_ok.set_value(result)
        for host in counts:
            sensor, sensor_u = sensors_value[host]
            sensor.set_value(counts[host])
            sensor_u.set_value(times[host])
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor_ok.set(value=False)
        for sensor, sensor_u in sensors_value.values():
            sensor.set(value=-1)
            sensor_u.set(value=-1)
    except Exception as e:
        LOGGER.error('Error updating feng rxtime sensor '
                     '- {}'.format(e.message))
        sensor_ok.set(value=False)
        for sensor, sensor_u in sensors_value.values():
            sensor.set(value=-1)
            sensor_u.set(value=-1)
    LOGGER.debug('_cb_feng_rxtime ran')
    IOLoop.current().call_later(10, _cb_feng_rxtime,
                                sensor_ok, sensors_value)


@gen.coroutine
def _cb_feng_delays(sensor, f_host):
    """
    Sensor call back function for F-engine delay functionality
    :param sensor:
    :return:
    """
    boolean_sensor_do(f_host, sensor, [f_host.check_cd])
    LOGGER.debug('_cb_feng_delays ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_delays, sensor, f_host)


@gen.coroutine
def _cb_feng_ct_okay(sensor, f_host):
    """
    Sensor call back function for F-engine delay functionality
    :param sensor:
    :return:
    """
    boolean_sensor_do(f_host, sensor, [f_host.check_ct])
    LOGGER.debug('_cb_feng_ct_okay ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_ct_okay, sensor, f_host)


@gen.coroutine
def _cb_fhost_lru(sensor, f_host):
    """
    Sensor call back function for F-engine LRU
    :param sensor:
    :return:
    """
    boolean_sensor_do(f_host, sensor, [f_host.host_okay])
    LOGGER.debug('_cb_fhost_lru ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_fhost_lru, sensor, f_host)


@gen.coroutine
def _cb_feng_pfb_okay(sensor, f_host):
    """
    F-engine PFB check
    :param sensor:
    :return:
    """
    boolean_sensor_do(f_host, sensor, [f_host.check_fft_overflow])
    if sensor.status() == Corr2Sensor.ERROR:
        sensor.set(status=Corr2Sensor.WARN, value=sensor.value())
    LOGGER.debug('_cb_feng_pfb_okay ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_pfb_okay, sensor, f_host)


@gen.coroutine
def _cb_fhost_check_network(sensors, f_host):
    """
    Check that the f-hosts are receiving data correctly
    :param sensors: a dict of the network sensors to update
    :return:
    """
    # RX
    boolean_sensor_do(f_host, sensors['rx'], [f_host.check_rx_raw, 0.2, 5])
    # TX
    boolean_sensor_do(f_host, sensors['tx'], [f_host.check_tx_raw, 0.2, 5])
    # both
    rx_okay = sensors['rx'].status() == Corr2Sensor.NOMINAL
    tx_okay = sensors['tx'].status() == Corr2Sensor.NOMINAL
    sensors['combined'].sensor_set_on_condition(rx_okay and tx_okay)
    # SPEAD RX
    sensor = sensors['spead']
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_rx_spead)
        sensor.set(status=Corr2Sensor.NOMINAL, value=True)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(value=False)
    except SkarabSpeadWarning:
        sensor.set(status=Corr2Sensor.WARN, value=False)
    except SkarabSpeadError:
        sensor.set(status=Corr2Sensor.ERROR, value=False)
    except Exception as e:
        LOGGER.error('Error updating {} for {} - '
                     '{}'.format(sensor.name, f_host.host, e.message))
        sensor.set(value=False)
    LOGGER.debug('_cb_fhost_check_network ran')
    IOLoop.current().call_later(10, _cb_fhost_check_network, sensors, f_host)


@gen.coroutine
def _cb_feng_rx_reorder(sensor, f_host):
    """
    F-engine RX counters
    :param sensor:
    :return: true/false
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_rx_reorder)
        sensor.sensor_set_on_condition(result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(value=False)
    except SkarabReorderWarning:
        sensor.set(status=Corr2Sensor.WARN, value=False)
    except SkarabReorderError:
        sensor.set(status=Corr2Sensor.ERROR, value=False)
    except Exception as e:
        LOGGER.error('Error updating {} for {} - '
                     '{}'.format(sensor.name, f_host.host, e.message))
        sensor.set(value=False)
    LOGGER.debug('_sensor_feng_rx ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_rx_reorder, sensor, f_host)


def setup_sensors_fengine(sens_man, general_executor, host_executors, ioloop,
                          host_offset_dict):
    """
    Set up the F-engine specific sensors.
    :param sens_man:
    :param general_executor:
    :param host_executors:
    :param ioloop:
    :param host_offset_dict:
    :return:
    """
    host_offset_lookup = host_offset_dict.copy()

    # F-engine received timestamps ok and per-host received timestamps
    sensor_ok = sens_man.do_sensor(
        Corr2Sensor.boolean, 'feng-rxtime-ok',
        'Are the times received by F-engines in the system ok?',
        executor=general_executor)
    sensors_value = {}
    for _f in sens_man.instrument.fhosts:
        fhost = host_offset_lookup[_f.host]
        sensor = sens_man.do_sensor(
            Corr2Sensor.integer, '{}-rxtimestamp'.format(fhost),
            'F-engine %s - sample-counter timestamps received from the '
            'digitisers' % _f.host)
        sensor_u = sens_man.do_sensor(
            Corr2Sensor.float, '{}-rxtime-unix'.format(fhost),
            'F-engine %s - UNIX timestamps received from '
            'the digitisers' % _f.host)
        sensors_value[_f.host] = (sensor, sensor_u)
    ioloop.add_callback(_cb_feng_rxtime, sensor_ok, sensors_value)

    # F-engine host sensors
    for _f in sens_man.instrument.fhosts:
        executor = host_executors[_f.host]
        fhost = host_offset_lookup[_f.host]

        # TODO: add check for sync cnt. If SKARAB requires resync,
        # must set delay to zero, resync and then continue delay operations.

        # raw network comms - gbe counters must increment
        network_sensors = {
            'rx': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}-network-rx-ok'.format(fhost),
                'F-engine network RX ok', executor=executor),
            'tx': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}-network-tx-ok'.format(fhost),
                'F-engine network TX ok', executor=executor),
            'combined': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}-network-ok'.format(fhost),
                'F-engine network raw RX/TX ok', executor=executor),
            'spead': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}-spead-rx-ok'.format(fhost),
                'F-engine SPEAD RX ok', executor=executor),
        }
        ioloop.add_callback(_cb_fhost_check_network, network_sensors, _f)

        # Rx reorder counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-reorder-ok'.format(fhost),
            'F-engine RX ok - reorder counters incrementing correctly',
            executor=executor)
        ioloop.add_callback(_cb_feng_rx_reorder, sensor, _f)

        # Delay functionality
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-delays-ok'.format(fhost),
            'F-engine delay functionality ok',
            executor=executor)
        ioloop.add_callback(_cb_feng_delays, sensor, _f)

        # PFB counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-pfb-ok'.format(fhost),
            'F-engine PFB ok', executor=executor)
        ioloop.add_callback(_cb_feng_pfb_okay, sensor, _f)

        # CT functionality
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-ct-ok'.format(fhost),
            'F-engine CT ok', executor=executor)
        ioloop.add_callback(_cb_feng_ct_okay, sensor, _f)

        # Overall LRU ok
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-lru-ok'.format(fhost),
            'F-engine %s LRU ok' % _f.host, executor=executor)
        ioloop.add_callback(_cb_fhost_lru, sensor, _f)

# end
