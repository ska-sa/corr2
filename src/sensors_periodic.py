import logging
import time
import tornado.gen as gen

from tornado.ioloop import IOLoop
from concurrent import futures

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid
from sensors import Corr2Sensor
import sensors_periodic_fhost as sensors_fhost
import sensors_periodic_xhost as sensors_xhost


LOGGER = logging.getLogger(__name__)

TX_PPS_SUFFIX = '-tx-pkt-per-s'
RX_PPS_SUFFIX = '-rx-pkt-per-s'
LINK_STATUS_SUFFIX = '-link-status'

host_offset_lookup = {}


def read_all_counters(fpga_host):
    """

    :param fpga_host:
    :return: a dictionary of all the counters in this host
    """
    if 'fft_shift' in fpga_host.registers.names():
        reglist = sensors_fhost.FHOST_REGS
    else:
        reglist = sensors_xhost.XHOST_REGS
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
            sensname = '{host}-{reg}-{key}-change'.format(
                host=host_offset_lookup[fpga_host.host],
                reg=_regrepr, key=_keyrepr)
            rvdict[sensname] = rs[reg][key]
    return rvdict


@gen.coroutine
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
        for sensor in manager.sensors.values():
            if ((sensor.name.endswith('-change')) and
                    (sensor.name.startswith(host_offset_lookup[host.host]))):
                sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
                sensor.previous_value = 0
    except Exception as e:
        LOGGER.error('Error updating counter sensors for {} - '
                     '{}'.format(host.host, e.message))
        for sensor in manager.sensors.values():
            if ((sensor.name.endswith('-change')) and
                    (sensor.name.startswith(host_offset_lookup[host.host]))):
                sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
                sensor.previous_value = 0
    IOLoop.current().call_later(10, _sensor_cb_system_counters,
                                host, host_executor, manager)


@gen.coroutine
def _sensor_cb_pps(host, host_executor, manager):
    """
    Host PPS counters
    :return:
    """
    def read_gbe_tx_rx(fpga):
        rv = {}
        for gbe in fpga.gbes:
            ctrs = gbe.read_counters()
            link_info = gbe.get_gbe_core_details()['xaui_status']
            rv[gbe.name] = (ctrs['%s_txctr' % gbe.name],
                            ctrs['%s_rxctr' % gbe.name],
                            str(link_info))
        return rv
    try:
        new_values = yield host_executor.submit(read_gbe_tx_rx, host)
        for gbe in host.gbes:
            hpref = '{host}-{gbe}'.format(
                host=host_offset_lookup[host.host], gbe=gbe.name)
            # TX
            sensor_name = '{pref}{suf}'.format(pref=hpref, suf=TX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            previous_value = sensor.previous_value
            pps = (new_values[gbe.name][0] - previous_value) / 10.0
            sensor.previous_value = new_values[gbe.name][0]
            sensor.set_value(pps)
            # RX
            sensor_name = '{pref}{suf}'.format(pref=hpref, suf=RX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            previous_value = sensor.previous_value
            pps = (new_values[gbe.name][1] - previous_value) / 10.0
            sensor.previous_value = new_values[gbe.name][1]
            if pps < 20.0:
                sensor.set(status=Corr2Sensor.WARN, value=pps)
            else:
                sensor.set_value(pps)
            # link-status
            sensor_name = '{pref}{suf}'.format(
                pref=hpref, suf=LINK_STATUS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set_value(new_values[gbe.name][2])
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        for gbe in host.gbes:
            hpref = '{host}-{gbe}'.format(
                host=host_offset_lookup[host.host], gbe=gbe.name)
            # TX
            sensor_name = '{pref}{suf}'.format(pref=hpref, suf=TX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # RX
            sensor_name = '{pref}{suf}'.format(pref=hpref, suf=RX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # link-status
            sensor_name = '{pref}{suf}'.format(
                pref=hpref, suf=LINK_STATUS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, '')
    except Exception as e:
        LOGGER.error('Error updating PPS sensors for {} - '
                     '{}'.format(host.host, e.message))
        for gbe in host.gbes:
            hpref = '{host}-{gbe}'.format(
                host=host_offset_lookup[host.host], gbe=gbe.name)
            # TX
            sensor_name = '{pref}{suf}'.format(pref=hpref, suf=TX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # RX
            sensor_name = '{pref}{suf}'.format(pref=hpref, suf=RX_PPS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            # link-status
            sensor_name = '{pref}{suf}'.format(
                pref=hpref, suf=LINK_STATUS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, '')
    LOGGER.debug('_sensor_cb_pps ran on {}'.format(host.host))
    IOLoop.current().call_later(10, _sensor_cb_pps,
                                host, host_executor, manager)


@gen.coroutine
def _sensor_cb_reorder_status(sensor, host):
    sens_man = sensor.manager
    executor = sensor.executor
    try:
        result = yield executor.submit(host.get_rx_reorder_status)
        result = str(result)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, '')
    except Exception as e:
        LOGGER.error('Error updating reorder status sensor for {} - '
                     '{}'.format(host.host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, '')
    LOGGER.debug('_sensor_cb_reorder_status ran on {}'.format(host.host))
    IOLoop.current().call_later(10, _sensor_cb_reorder_status, sensor, host)


def setup_sensors(sensor_manager, enable_counters=False):
    """
    INSTRUMENT-STATE-INDEPENDENT sensors to be reported to CAM
    :param sensor_manager: A SensorManager instance
    :param enable_counters: Enable the counter-value-changed sensors
    :return:
    """
    # make the mapping of hostnames to host offsets
    for ctr, host in enumerate(sensor_manager.instrument.xhosts):
        assert host.host not in host_offset_lookup
        host_offset_lookup[host.host] = 'xhost{}'.format(ctr)
    for ctr, host in enumerate(sensor_manager.instrument.fhosts):
        assert host.host not in host_offset_lookup
        host_offset_lookup[host.host] = 'fhost{}'.format(ctr)

    sens_man = sensor_manager

    # Set up a one-worker pool per host to serialise interactions with each host
    host_executors = {
        host.host: futures.ThreadPoolExecutor(max_workers=1)
        for host in sens_man.instrument.fhosts +
        sens_man.instrument.xhosts
    }
    general_executor = futures.ThreadPoolExecutor(max_workers=1)

    if not sens_man.instrument.initialised():
        raise RuntimeError('Cannot set up sensors until instrument is '
                           'initialised.')

    ioloop = getattr(sens_man.instrument, 'ioloop', None)
    if not ioloop:
        ioloop = getattr(sens_man.katcp_server, 'ioloop', None)
    if not ioloop:
        raise RuntimeError('IOLoop-containing katcp version required. Can go '
                           'no further.')

    sens_man.sensors_clear()

    args = [sens_man, general_executor,
            host_executors, ioloop, host_offset_lookup]
    sensors_fhost.setup_sensors_fengine(*args)
    sensors_xhost.setup_sensors_xengine(*args)
    sensors_xhost.setup_sensors_bengine(*args)

    all_hosts = sens_man.instrument.fhosts + sens_man.instrument.xhosts

    sensor = sens_man.do_sensor(
                Corr2Sensor.string,
                'hostname-functional-mapping',
                'On which hostname is which functional host?',
                Corr2Sensor.NOMINAL, '', None)
    sensor.set_value(str(host_offset_lookup))

    # gbe packet-per-second counters
    for _h in all_hosts:
        executor = host_executors[_h.host]
        for gbe in _h.gbes:
            hpref = '{host}-{gbe}'.format(host=host_offset_lookup[_h.host],
                                          gbe=gbe.name)
            sensor = sens_man.do_sensor(
                Corr2Sensor.float,
                '{pref}{suf}'.format(pref=hpref, suf=TX_PPS_SUFFIX),
                '%s %s TX packet-per-second counter' % (_h.host, gbe.name),
                Corr2Sensor.UNKNOWN, '', executor)
            sensor.previous_value = 0
            sensor = sens_man.do_sensor(
                Corr2Sensor.float,
                '{pref}{suf}'.format(pref=hpref, suf=RX_PPS_SUFFIX),
                '%s %s RX packet-per-second counter' % (_h.host, gbe.name),
                Corr2Sensor.UNKNOWN, '', executor)
            sensor.previous_value = 0
            sensor = sens_man.do_sensor(
                Corr2Sensor.string,
                '{pref}{suf}'.format(pref=hpref, suf=LINK_STATUS_SUFFIX),
                '%s %s link status' % (_h.host, gbe.name),
                Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_cb_pps, _h, executor, sens_man)

    # read all relevant counters
    if enable_counters:
        for _h in all_hosts:
            executor = host_executors[_h.host]
            host_ctrs = read_all_counters(_h)
            for ctr in host_ctrs:
                sensor = sens_man.do_sensor(
                    Corr2Sensor.boolean, '%s' % ctr,
                    'Counter on %s, True is changed since last read' % _h.host,
                    Corr2Sensor.UNKNOWN, '', executor)
                sensor.previous_value = 0
            ioloop.add_callback(_sensor_cb_system_counters,
                                _h, executor, sens_man)

# end
