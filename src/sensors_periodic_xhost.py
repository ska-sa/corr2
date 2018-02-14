import logging
import time
import tornado.gen as gen

from tornado.ioloop import IOLoop

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid

from sensors import Corr2Sensor, boolean_sensor_do

LOGGER = logging.getLogger(__name__)

XHOST_REGS = ['status']
XHOST_REGS.extend(['status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['spead_status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reord_status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['bf0_status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['bf1_status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vacc_status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['pack_status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['gbe%i_txctr' % ctr for ctr in range(1)])
XHOST_REGS.extend(['gbe%i_txofctr' % ctr for ctr in range(1)])
XHOST_REGS.extend(['gbe%i_rxctr' % ctr for ctr in range(1)])
XHOST_REGS.extend(['gbe%i_rxofctr' % ctr for ctr in range(1)])
XHOST_REGS.extend(['gbe%i_rxbadctr' % ctr for ctr in range(1)])

host_offset_lookup = {}


@gen.coroutine
def _cb_xhost_lru(sensor, x_host):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
    boolean_sensor_do(x_host, sensor, [x_host.host_okay])
    LOGGER.debug('_cb_xhost_lru ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xhost_lru, sensor, x_host)


@gen.coroutine
def _cb_xhost_check_network(sensors, x_host):
    """

    :param sensors:
    :param x_host:
    :return:
    """
    #GBE CORE
    # TODO add check for bad RX packets and TX overflows
    executor = sensors['tx_pps'].executor
    try:
        result = yield executor.submit(x_host.gbes.gbe0.get_stats)
        sensors['tx_pps'].set(status=Corr2Sensor.NOMINAL, value=result['tx_pps'])
        sensors['tx_gbps'].set(status=Corr2Sensor.NOMINAL, value=result['tx_gbps'])

        if result['rx_pps']>3000000:
            sensors['rx_pps'].set(status=Corr2Sensor.NOMINAL, value=result['rx_pps'])
        else:
            sensors['rx_pps'].set(status=Corr2Sensor.WARN, value=result['rx_pps'])

        if result['rx_gbps']>30:
            sensors['rx_gbps'].set(status=Corr2Sensor.NOMINAL, value=result['rx_gbps'])
        else:
            sensors['rx_gbps'].set(status=Corr2Sensor.WARN, value=result['rx_gbps'])
    except Exception as e:
        LOGGER.error(
            'Error updating gbe_stats for {} - {}'.format(
                x_host.host, e.message))
        sensors['tx_pps'].set(status=Corr2Sensor.UNKNOWN, value=-1)
        sensors['rx_pps'].set(status=Corr2Sensor.UNKNOWN, value=-1)
        sensors['tx_gbps'].set(status=Corr2Sensor.UNKNOWN, value=-1)
        sensors['rx_gbps'].set(status=Corr2Sensor.UNKNOWN, value=-1)

    # SPEAD RX
    sensor_spead = sensors['spead']
    executor = sensor_spead.executor
    result = (1, 1)
    try:
        result = yield executor.submit(x_host.check_rx_spead)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor_spead.set(value=False)
    except Exception as e:
        LOGGER.error('Error updating {} for {} - '
                     '{}'.format(sensor_spead.name, x_host.host, e.message))
        sensor_spead.set(value=False)
    if result[0] == 0:
        sensor_spead.set(status=Corr2Sensor.NOMINAL, value=True)
    elif result[0] == 1:
        sensor_spead.set(status=Corr2Sensor.WARN, value=False)
    else:
        sensor_spead.set(status=Corr2Sensor.ERROR, value=False)
    LOGGER.debug('_cb_xhost_check_network ran')
    IOLoop.current().call_later(10, _cb_xhost_check_network, sensors, x_host)


@gen.coroutine
def _cb_xhost_rx_reorder(sensors, x_host):
    """
    X-engine RX counters
    :param sensors: a sensor for each xengine rx reorder
    :return:
    """
    executor = sensors[0].executor
    try:
        results = yield executor.submit(x_host.check_rx_reorder)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        results = None
    except Exception as e:
        LOGGER.error('Error updating RX reorder sensors for {} - '
                     '{}'.format(x_host.host, e.message))
        results = None
    if results is not None:
        for xctr, res in enumerate(results):
            if res == 0:
                sensors[xctr].set(status=Corr2Sensor.NOMINAL, value=True)
            elif res == 1:
                sensors[xctr].set(status=Corr2Sensor.ERROR, value=False)
            elif res == 2:
                sensors[xctr].set(status=Corr2Sensor.WARN, value=False)
    else:
        for xctr in range(x_host.x_per_fpga):
            sensors[xctr].set(value=False)
    LOGGER.debug('_cb_xhost_rx_reorder ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xhost_rx_reorder, sensors, x_host)


@gen.coroutine
def _cb_xeng_pack(sensors, x_host):
    """

    :param sensors: a sensor for each xengine pack block
    :param x_host: the host on which this is run
    :return:
    """
    executor = sensors[0].executor
    try:
        results = yield executor.submit(x_host.check_pack)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        results = None
    except Exception as e:
        LOGGER.error('Error updating pack sensors for {} - '
                     '{}'.format(x_host.host, e.message))
        results = None
    if results is not None:
        for xctr, res in enumerate(results):
            if res == 0:
                sensors[xctr].set(status=Corr2Sensor.NOMINAL, value=True)
            elif res == 1:
                sensors[xctr].set(status=Corr2Sensor.ERROR, value=False)
            elif res == 2:
                sensors[xctr].set(status=Corr2Sensor.WARN, value=False)
    else:
        for xctr in range(x_host.x_per_fpga):
            sensors[xctr].set(value=False)
    LOGGER.debug('_cb_xeng_pack ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xeng_pack, sensors, x_host)


@gen.coroutine
def _cb_beng(sensors, x_host):
    """

    :param sensors: a sensor for each xengine pack block
    :param x_host: the host on which this is run
    :return:
    """
    executor = sensors[0][0].executor
    try:
        results = yield executor.submit(x_host.check_beng)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        results = None
    except Exception as e:
        LOGGER.error('Error updating beng sensors for {} - '
                     '{}'.format(x_host.host, e.message))
        results = None
    if results is not None:
        for xctr, res in enumerate(results):
            for pctr in range(2):
                sensor = sensors[xctr][pctr]
                if res == 0:
                    sensor.set(status=Corr2Sensor.NOMINAL, value=True)
                elif res == 1:
                    sensor.set(status=Corr2Sensor.ERROR, value=False)
                elif res == 2:
                    sensor.set(status=Corr2Sensor.WARN, value=False)
    else:
        for xctr in range(x_host.x_per_fpga):
            for pctr in range(2):
                sensors[xctr][pctr].set(value=False)
    LOGGER.debug('_cb_beng ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_beng, sensors, x_host)


@gen.coroutine
def _cb_xeng_vacc(sensors, x_host):
    """

    :param sensors: a list of sensors, one for each vacc
    :param x_host: the host on which this is run
    :return:
    """
    executor = sensors[0].executor
    results = None
    try:
        results = yield executor.submit(x_host.check_vacc)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        pass
    except Exception as exc:
        LOGGER.error('Error updating vacc sensors for {} - '
                     '{}'.format(x_host.host, exc.message))
    if results is not None:
        for xctr, res in enumerate(results):
            if res == 0:
                sensors[xctr].set(status=Corr2Sensor.NOMINAL, value=True)
            elif res == 1:
                sensors[xctr].set(status=Corr2Sensor.ERROR, value=False)
            elif res == 2:
                sensors[xctr].set(status=Corr2Sensor.WARN, value=False)
    else:
        for xctr in range(x_host.x_per_fpga):
            sensors[xctr].set(value=False)
    LOGGER.debug('_cb_xeng_vacc ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xeng_vacc, sensors, x_host)


@gen.coroutine
def _cb_xeng_vacc_ctrs(host, host_executor, manager):
    """
    Populate VACC counter sensors: arm, accumulation, errors, load
    :param host:
    :param host_executor:
    :param manager:
    :return:
    """
    def sensors_unknown():
        for xctr in range(host.x_per_fpga):
            sens_pref = '{xhost}-xeng{xctr}'.format(xhost=xhost, xctr=xctr)
            update_time = time.time()
            sensor = manager.sensor_get('{}-vacc-arm-cnt'.format(sens_pref))
            sensor.set(value=-1)
            sensor = manager.sensor_get('{}-vacc-ctr'.format(sens_pref))
            sensor.set(value=-1)
            sensor = manager.sensor_get('{}-vacc-error-ctr'.format(sens_pref))
            sensor.set(value=-1)
            sensor = manager.sensor_get('{}-vacc-load-ctr'.format(sens_pref))
            sensor.set(value=-1)
            sensor = manager.sensor_get('{}-vacc-timestamp'.format(sens_pref))
            sensor.set(value=-1)

    xhost = host_offset_lookup[host.host]
    results = [{'armcount': -1, 'count': -1, 'errors': -1, 'loadcount': -1, 
                'timestamp':-1} for ctr in range(host.x_per_fpga)]
    try:
        results = yield host_executor.submit(host.vacc_get_status)
    except Exception as e:
        LOGGER.error('Error updating vacc counter sensors for {} - '
                     '{}'.format(host.host, e.message))
    if results is None:
        sensors_unknown()
    else:
        for xctr in range(host.x_per_fpga):
            sens_pref = '{xhost}-xeng{xctr}'.format(xhost=xhost, xctr=xctr)
            update_time = time.time()
            sensor = manager.sensor_get('{}-vacc-arm-cnt'.format(sens_pref))
            sensor.set(update_time, Corr2Sensor.NOMINAL,
                       results[xctr]['armcount'])
            sensor = manager.sensor_get('{}-vacc-ctr'.format(sens_pref))
            sensor.set(update_time, Corr2Sensor.NOMINAL, results[xctr]['count'])
            sensor = manager.sensor_get('{}-vacc-error-ctr'.format(sens_pref))
            sensor.set(update_time, Corr2Sensor.NOMINAL,
                       results[xctr]['errors'])
            sensor = manager.sensor_get('{}-vacc-load-ctr'.format(sens_pref))
            sensor.set(update_time, Corr2Sensor.NOMINAL,
                       results[xctr]['loadcount'])
            sensor = manager.sensor_get('{}-vacc-timestamp'.format(sens_pref))
            sensor.set(update_time, Corr2Sensor.NOMINAL,
                       results[xctr]['timestamp'])
    LOGGER.debug('_cb_xeng_vacc_ctrs ran on {}'.format(host.host))
    IOLoop.current().call_later(10, _cb_xeng_vacc_ctrs, host,
                                host_executor, manager)


@gen.coroutine
def _cb_xeng_vacc_accs_ps(host, host_executor, manager):
    """

    :param host:
    :param host_executor:
    :param manager:
    :return:
    """
    results = [-1] * host.x_per_fpga
    try:
        results = yield host_executor.submit(host.vacc_accumulations_per_second)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        LOGGER.error('Katcp error updating vacc rate sensors for '
                     '{}'.format(host.host))
    except Exception as e:
        LOGGER.error('Error updating vacc rate sensors for {} - '
                     '{}'.format(host.host, e.message))
    for xctr in range(host.x_per_fpga):
        sensor = manager.sensor_get('{xhost}-xeng{xctr}-accs-per-sec'.format(
            xhost=host_offset_lookup[host.host], xctr=xctr))
        sensor.set(time.time(), Corr2Sensor.NOMINAL, results[xctr])
    LOGGER.debug('_cb_xeng_vacc_accs_ps ran on {}'.format(host.host))
    IOLoop.current().call_later(10, _cb_xeng_vacc_accs_ps, host,
                                host_executor, manager)


@gen.coroutine
def _cb_xeng_vacc_sync_time(sensor, host):
    """

    :param sensor:
    :param host:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(host.vacc_get_loadtime)
        sensor.set(value=result, status=Corr2Sensor.NOMINAL)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(status=Corr2Sensor.WARN, value=-1)
    except Exception as e:
        LOGGER.error('Error updating {} for {} - '
                     '{}'.format(sensor.name, host.host, e.message))
        sensor.set(status=Corr2Sensor.WARN, value=-1)
    LOGGER.debug('_cb_xeng_vacc_sync_time ran on {}'.format(host.host))
    IOLoop.current().call_later(10, _cb_xeng_vacc_sync_time, sensor, host)


def setup_sensors_bengine(sens_man, general_executor, host_executors, ioloop,
                          host_offset_dict):
    """
    Set up the B-engine specific sensors.
    :param sens_man:
    :param general_executor:
    :param host_executors:
    :param ioloop:
    :param host_offset_dict:
    :return:
    """
    global host_offset_lookup
    if len(host_offset_lookup) == 0:
        host_offset_lookup = host_offset_dict.copy()

    # TODO - right now this just mirrors the xhostn-lru-ok sensors

    # B-engine host sensors
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        bhost = xhost.replace('xhost', 'bhost')

        # LRU ok
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-lru-ok'.format(bhost),
            'B-engine %s LRU ok' % _x.host, executor=executor)
        ioloop.add_callback(_cb_xhost_lru, sensor, _x)


def setup_sensors_xengine(sens_man, general_executor, host_executors, ioloop,
                          host_offset_dict):
    """
    Set up the X-engine specific sensors.
    :param sens_man:
    :param general_executor:
    :param host_executors:
    :param ioloop:
    :param host_offset_dict:
    :return:
    """
    global host_offset_lookup
    if len(host_offset_lookup) == 0:
        host_offset_lookup = host_offset_dict.copy()

    # X-engine host sensors
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        network_sensors = {
            'tx_pps': sens_man.do_sensor(
                Corr2Sensor.float, '{}-network-tx-pps'.format(xhost),
                'X-engine network raw TX packets per second', executor=executor),
            'rx_pps': sens_man.do_sensor(
                Corr2Sensor.float, '{}-network-rx-pps'.format(xhost),
                'X-engine network raw RX packets per second', executor=executor),
            'tx_gbps': sens_man.do_sensor(
                Corr2Sensor.float, '{}-network-tx-gbps'.format(xhost),
                'X-engine network raw TX rate (gigabits per second)', executor=executor),
            'rx_gbps': sens_man.do_sensor(
                Corr2Sensor.float, '{}-network-rx-gbps'.format(xhost),
                'X-engine network raw RX rate (gibabits per second)', executor=executor),
            'spead': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}-spead-rx-ok'.format(xhost),
                'X-engine SPEAD RX ok', executor=executor),
        }
        ioloop.add_callback(_cb_xhost_check_network, network_sensors, _x)

        # Rx reorder
        sensors = []
        for xctr in range(_x.x_per_fpga):
            sensor = sens_man.do_sensor(
                Corr2Sensor.boolean, '{host}-reorder{xeng}-ok'.format(
                    host=xhost, xeng=xctr),
                '{host} x-engine{xeng} RX reorder ok - counters incrementing '
                'correctly'.format(host=xhost, xeng=xctr), executor=executor)
            sensors.append(sensor)
        ioloop.add_callback(_cb_xhost_rx_reorder, sensors, _x)

        # VACC
        sensors = []
        for xctr in range(_x.x_per_fpga):
            sensor = sens_man.do_sensor(
                Corr2Sensor.boolean, '{host}-vacc{xeng}-ok'.format(
                    host=xhost, xeng=xctr),
                '{host} x-engine{xeng} vacc ok - vaccs operating '
                'correctly'.format(host=xhost, xeng=xctr), executor=executor)
            sensors.append(sensor)
        ioloop.add_callback(_cb_xeng_vacc, sensors, _x)
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}-xeng{xctr}'.format(xhost=xhost, xctr=xctr)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-arm-cnt'.format(pref=pref),
                'Number of times this VACC has armed.', executor=executor)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-ctr'.format(pref=pref),
                'Number of accumulations this VACC has performed.',
                executor=executor)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-error-ctr'.format(pref=pref),
                'Number of VACC errors.', executor=executor)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-load-ctr'.format(pref=pref),
                'Number of times this VACC has been loaded.',
                executor=executor)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-timestamp'.format(pref=pref),
                'Current VACC timestamp.',
                executor=executor)
        ioloop.add_callback(_cb_xeng_vacc_ctrs, _x, executor, sens_man)

#        # VACC accumulations per second
#        for xctr in range(_x.x_per_fpga):
#            pref = '{xhost}-xeng{xctr}-'.format(xhost=xhost, xctr=xctr)
#            sensor = sens_man.do_sensor(
#                Corr2Sensor.float, '{pref}accs-per-sec'.format(pref=pref),
#                'Number of accumulations per second for this X-engine on '
#                'this host.', executor=executor)
#        ioloop.add_callback(_cb_xeng_vacc_accs_ps, _x, executor, sens_man)

        # VACC synch time
        sensor = sens_man.do_sensor(
            Corr2Sensor.integer, '{}-vacc-sync-time'.format(xhost),
            'X-engine VACC sync time - when was the VACC last syncd, in '
            'ADC ticks', executor=executor)
        ioloop.add_callback(_cb_xeng_vacc_sync_time, sensor, _x)

        # packetiser
        sensors = []
        for xctr in range(_x.x_per_fpga):
            sensor = sens_man.do_sensor(
                Corr2Sensor.boolean, '{host}-pack{xeng}-ok'.format(
                    host=xhost, xeng=xctr),
                '{host} x-engine{xeng} pack ok'.format(host=xhost, xeng=xctr),
                executor=executor)
            sensors.append(sensor)
        ioloop.add_callback(_cb_xeng_pack, sensors, _x)

        # beng
        sensors = []
        for xctr in range(_x.x_per_fpga):
            bsensors = []
            for pctr in range(2):
                sensor_name = '{host}-beng{x}-{p}-ok'.format(
                    host=xhost, x=xctr, p=pctr)
                sensor_descrip = '{host} b-engine{x}-{p} ok'.format(
                    host=xhost, x=xctr, p=pctr)
                sensor = sens_man.do_sensor(Corr2Sensor.boolean, sensor_name,
                                            sensor_descrip, executor=executor)
                bsensors.append(sensor)
            sensors.append(bsensors)
        ioloop.add_callback(_cb_beng, sensors, _x)

        # LRU ok
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-lru-ok'.format(xhost),
            'X-engine %s LRU ok' % _x.host, executor=executor)
        ioloop.add_callback(_cb_xhost_lru, sensor, _x)

# end
