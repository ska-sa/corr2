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

def setup_sensors(sensor_manager):
    """
    INSTRUMENT-STATE-INDEPENDENT sensors to be reported to CAM
    :param sensor_manager: A SensorManager instance
    :return:
    """

    # make the mapping of hostnames to host offsets
    #TODO are these assert statements a wise idea? I think they should be refactored away in favour of something proper.
    for ctr, host in enumerate(sensor_manager.instrument.xhosts):
        assert host.host not in host_offset_lookup
        host_offset_lookup[host.host] = 'xhost{:02}'.format(ctr)
        #if host.host_type == 'xhost':
        #    host_offset_lookup[host.host] = 'xhost{:02}'.format(ctr)
        #else:
        #    # bhost, probably
        #    host_offset_lookup[host.host] = 'bhost{:02}'.format(ctr)
    for ctr, host in enumerate(sensor_manager.instrument.fhosts):
        assert host.host not in host_offset_lookup
        host_offset_lookup[host.host] = 'fhost{:02}'.format(ctr)

    # for ctr, host in enumerate(sensor_manager.instrument.bhosts):
    #     assert host.host not in host_offset_lookup
    #     host_offset_lookup[host.host] = 'bhost{:02}'.format(ctr)

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

# end
