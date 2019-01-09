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
import sensors_periodic_bhost as sensors_bhost


LOGGER = logging.getLogger(__name__)

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
        host_offset_lookup[host.host] = 'xhost{:02}'.format(ctr)
    for ctr, host in enumerate(sensor_manager.instrument.fhosts):
        assert host.host not in host_offset_lookup
        host_offset_lookup[host.host] = 'fhost{:02}'.format(ctr)

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
    sensors_bhost.setup_sensors_bengine(*args)

    all_hosts = sens_man.instrument.fhosts + sens_man.instrument.xhosts

    sensor = sens_man.do_sensor(
                Corr2Sensor.string,
                'hostname-functional-mapping',
                'On which hostname is which functional host?',
                Corr2Sensor.NOMINAL, '', None)
    sensor.set_value(str(host_offset_lookup))

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
