import logging
import time
import tornado.gen as gen

from tornado.ioloop import IOLoop
from concurrent import futures

from sensors import Corr2Sensor
import sensors_periodic_fhost as sensors_fhost
import sensors_periodic_xhost as sensors_xhost
import sensors_periodic_bhost as sensors_bhost
import sensor_scheduler

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
    
    for ctr, host in enumerate(sensor_manager.instrument.fhosts):
        assert host.host not in host_offset_lookup
        host_offset_lookup[host.host] = 'fhost{:02}'.format(ctr)

    sensor_poll_interval = sensor_manager.instrument.sensor_poll_interval;
    sensor_scheduler.sensor_call_gap_time_s = sensor_poll_interval;
    sensor_scheduler.logger = sensor_manager.logger;
        
    # Set up a one-worker pool per host to serialise interactions with each host
    host_executors = {
        host.host: futures.ThreadPoolExecutor(max_workers=1)
        for host in sensor_manager.instrument.fhosts +
        sensor_manager.instrument.xhosts
    }
    general_executor = futures.ThreadPoolExecutor(max_workers=1)
    if not sensor_manager.instrument.initialised():
        raise RuntimeError('Cannot set up sensors until instrument is '
                           'initialised.')
    ioloop = getattr(sensor_manager.instrument, 'ioloop', None)
    if not ioloop:
        ioloop = getattr(sensor_manager.katcp_server, 'ioloop', None)
    if not ioloop:
        raise RuntimeError('IOLoop-containing katcp version required. Can go '
                           'no further.')
    
    sensor_manager.sensors_clear()
    args = [sensor_manager, general_executor,
            host_executors, ioloop, host_offset_lookup]

    # create 'static' sensors
    sensor = sensor_manager.do_sensor(
                Corr2Sensor.string,
                'hostname-functional-mapping',
                'On which hostname is which functional host?',
                Corr2Sensor.NOMINAL, '', None)
    sensor.set_value(str(host_offset_lookup))

    # setup periodic sensors
    sensors_fhost.setup_sensors_fengine(*args)
    sensors_xhost.setup_sensors_xengine(*args)
    sensors_bhost.setup_sensors_bengine(*args)

    all_hosts = sensor_manager.instrument.fhosts + sensor_manager.instrument.xhosts

# end
