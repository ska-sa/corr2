import logging
import time
import tornado.gen

from tornado.ioloop import IOLoop
from concurrent import futures

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid

from sensors import Corr2Sensor

LOGGER = logging.getLogger(__name__)

FHOST_REGS = ['spead_ctrs', 'reorder_ctrs', 'sync_ctrs', 'pfb_ctrs', 'ct_ctrs',
              'cd_ctrs']
FHOST_REGS.extend(['gbe%i_txctr' % ctr for ctr in range(4)])
FHOST_REGS.extend(['gbe%i_txerrctr' % ctr for ctr in range(4)])
FHOST_REGS.extend(['gbe%i_rxctr' % ctr for ctr in range(4)])
FHOST_REGS.extend(['gbe%i_rxerrctr' % ctr for ctr in range(4)])

XHOST_REGS = ['rx_cnt%i' % ctr for ctr in range(4)]
XHOST_REGS.extend(['rx_err_cnt%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['dest_err_cnt%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reordcnt_spec%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reord_missant%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reordcnt_recv%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reorderr_recv%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reorderr_timeout%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['reorderr_disc%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['bf%i_out_count' % ctr for ctr in range(2)])
XHOST_REGS.extend(['bf%i_of_count' % ctr for ctr in range(2)])
XHOST_REGS.extend(['vacccnt%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vaccout%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vaccerr%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vacc_ld_status%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['vacc_errors%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['packcnt_out%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['packerr_%i' % ctr for ctr in range(4)])
XHOST_REGS.extend(['gbe%i_txctr' % ctr for ctr in range(4)])
XHOST_REGS.extend(['gbe%i_rxctr' % ctr for ctr in range(4)])
XHOST_REGS.extend(['gbe%i_rxerrctr' % ctr for ctr in range(4)])

TX_PPS_SUFFIX = '-tx-pkt-per-s'
RX_PPS_SUFFIX = '-rx-pkt-per-s'
LINK_STATUS_SUFFIX = '-link-status'

host_lookup = {}


def read_all_counters(fpga_host):
    """

    :param fpga_host:
    :return: a dictionary of all the counters in this host
    """
    if 'fft_shift' in fpga_host.registers.names():
        reglist = FHOST_REGS
    else:
        reglist = XHOST_REGS
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
                host=host_lookup[fpga_host.host], reg=_regrepr, key=_keyrepr)
            rvdict[sensname] = rs[reg][key]
    return rvdict


@tornado.gen.coroutine
def _sensor_cb_feng_rxtime(sensor_ok, sensor_values):
    """
    Sensor call back to check received F-engine times
    :param sensor_ok: the combined times-are-okay sensor
    :param sensor_values: per-host sensors for time and unix-time
    :return:
    """
    executor = sensor_ok.executor
    instrument = sensor_ok.manager.instrument
    try:
        result, counts, times = yield executor.submit(
            instrument.fops.check_rx_timestamps)
        sensor_ok.set(time.time(),
                      Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR,
                      result)
        for host in counts:
            sensor, sensor_u = sensor_values[host]
            sensor.set_value(counts[host])
            sensor_u.set_value(times[host])
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor_ok.set(time.time(), Corr2Sensor.UNKNOWN, False)
        for sensor, sensor_u in sensor_values.values():
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            sensor_u.set(time.time(), Corr2Sensor.UNKNOWN, -1)
    except Exception as e:
        LOGGER.error('Error updating feng rxtime sensor '
                     '- {}'.format(e.message))
        sensor_ok.set(time.time(), Corr2Sensor.UNKNOWN, False)
        for sensor, sensor_u in sensor_values.values():
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, -1)
            sensor_u.set(time.time(), Corr2Sensor.UNKNOWN, -1)
    LOGGER.debug('_sensor_cb_feng_rxtime ran')
    IOLoop.current().call_later(10, _sensor_cb_feng_rxtime,
                                sensor_ok, sensor_values)


# @tornado.gen.coroutine
# def _sensor_cb_fdelays(sensor, f_host):
#     """
#     Sensor call back function for F-engine delay functionality
#     :param sensor:
#     :return:
#     """
#     executor = sensor.executor
#     try:
#         result = yield executor.submit(f_host.delay_check_loadcounts)
#         sensor.set(time.time(),
#                    Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
#     except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
#         sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
#     except Exception as e:
#         LOGGER.error('Error updating delay functionality sensor '
#                      'for {} - {}'.format(f_host, e.message))
#         sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
#     LOGGER.debug('_sensor_cb_fdelays ran on {}'.format(f_host))
#     IOLoop.current().call_later(10, _sensor_cb_fdelays, sensor, f_host)


@tornado.gen.coroutine
def _sensor_cb_flru(sensor, f_host):
    """
    Sensor call back function for F-engine LRU
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.host_okay)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating flru sensor for {} - '
                     '{}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_cb_flru ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_cb_flru, sensor, f_host)


@tornado.gen.coroutine
def _sensor_cb_xlru(sensor, x_host):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.host_okay)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating xlru sensor for {} - '
                     '{}'.format(x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_cb_xlru ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_cb_xlru, sensor, x_host)




@tornado.gen.coroutine
def _feng_pfb_okay(sensor, f_host):
    """
    F-engine PFB check
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_fft_overflow)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating feng pfb sensor for {} - '
                     '{}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_feng_pfb_okay ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _feng_pfb_okay, sensor, f_host)


@tornado.gen.coroutine
def _fhost_check_network_rx(sensor, f_host):
    """
    Check that the f-hosts are receiving data correctly
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_rx_raw, 0.2, 5)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating {} for {} - '
                     '{}'.format(sensor.name, f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_fhost_check_network_rx ran')
    IOLoop.current().call_later(10, _fhost_check_network_rx, sensor, f_host)


@tornado.gen.coroutine
def _fhost_check_network_tx(sensor, f_host):
    """
    Check that the f-hosts are sending data correctly
    :param sensor:
    :param f_host:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_tx_raw, 0.2, 5)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating {} for {} - '
                     '{}'.format(sensor.name, f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_fhost_check_network_tx ran')
    IOLoop.current().call_later(10, _fhost_check_network_tx, sensor, f_host)


@tornado.gen.coroutine
def _xhost_check_network_rx(sensor, x_host):
    """
    Check that the x-hosts are receiving data correctly
    :param sensor:
    :param x_host:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.check_rx)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating {} for {} - '
                     '{}'.format(sensor.name, x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_xhost_check_network_rx ran')
    IOLoop.current().call_later(10, _xhost_check_network_rx, sensor, x_host)


@tornado.gen.coroutine
def _xhost_report_network_tx(sensor_manager, x_host):
    """
    Check that the x-hosts are sending data correctly
    :param x_host:
    :return:
    """
    xhost = host_lookup[x_host.host]
    counters_ticking = True
    for gbe in x_host.gbes:
        sensor = sensor_manager.sensor_get(
            '{xhost}-network-{gbe}-tx-ctr'.format(
                xhost=xhost, gbe=gbe.name))
        old_val = sensor.value()
        executor = sensor.executor
        try:
            result = yield executor.submit(
                x_host.registers['%s_txctr' % gbe.name].read)
            result = result['data']['reg']
            sensor.set_value(result)
            if result == old_val:
                counters_ticking = False
        except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
            new_vals = None
        except Exception as e:
            LOGGER.error('Error updating {} for {} - '
                         '{}'.format(sensor.name, x_host, e.message))
            sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
            new_vals = None
    sensor_ok = sensor = sensor_manager.sensor_get(
        '{}-network-tx-ok'.format(xhost))
    sensor.set_value(counters_ticking)
    LOGGER.debug('_xhost_report_network_tx ran')
    IOLoop.current().call_later(10, _xhost_report_network_tx,
                                sensor_manager, x_host)


@tornado.gen.coroutine
def _sensor_feng_rx_reorder(sensor, f_host):
    """
    F-engine RX counters
    :param sensor:
    :return: true/false
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(f_host.check_rx_reorder)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating feng_rx sensor for {} - '
                     '{}'.format(f_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_feng_rx ran on {}'.format(f_host))
    IOLoop.current().call_later(10, _sensor_feng_rx_reorder, sensor, f_host)


@tornado.gen.coroutine
def _sensor_xeng_rx_reorder(sensor, x_host):
    """
    X-engine RX counters
    :param sensor:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(x_host.check_rx_reorder)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating xeng_rx sensor for {} - '
                     '{}'.format(x_host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_xeng_rx ran on {}'.format(x_host))
    IOLoop.current().call_later(10, _sensor_xeng_rx_reorder, sensor, x_host)


@tornado.gen.coroutine
def _sensor_xeng_vacc_ctrs(host, host_executor, manager):
    """
    Populate VACC counter sensors: arm, accumulation, errors, load
    :param host:
    :param host_executor:
    :param manager:
    :return:
    """
    results = [{'armcount': -1, 'count': -1, 'errors': -1, 'loadcount': -1}
               for ctr in range(host.x_per_fpga)]
    try:
        results = yield host_executor.submit(host.vacc_get_status)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        LOGGER.error('Katcp error updating vacc counter sensors '
                     'for {}'.format(host.host))
    except Exception as e:
        LOGGER.error('Error updating vacc counter sensors for {} - '
                     '{}'.format(host.host, e.message))
    for xctr in range(host.x_per_fpga):
        sens_pref = '{xhost}-xeng{xctr}'.format(
            xhost=host_lookup[host.host], xctr=xctr)

        sensor = manager.sensor_get('{}-vacc-arm-cnt'.format(sens_pref))
        sensor.set(time.time(), Corr2Sensor.NOMINAL, results[xctr]['armcount'])

        sensor = manager.sensor_get('{}-vacc-ctr'.format(sens_pref))
        sensor.set(time.time(), Corr2Sensor.NOMINAL, results[xctr]['count'])

        sensor = manager.sensor_get('{}-vacc-error-ctr'.format(sens_pref))
        sensor.set(time.time(), Corr2Sensor.NOMINAL, results[xctr]['errors'])

        sensor = manager.sensor_get('{}-vacc-load-ctr'.format(sens_pref))
        sensor.set(time.time(), Corr2Sensor.NOMINAL, results[xctr]['loadcount'])
    LOGGER.debug('_sensor_xeng_vacc_ctrs ran on {}'.format(host))
    IOLoop.current().call_later(10, _sensor_xeng_vacc_ctrs, host,
                                host_executor, manager)


@tornado.gen.coroutine
def _sensor_xeng_vacc_accs_ps(host, host_executor, manager):
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
            xhost=host_lookup[host.host], xctr=xctr))
        sensor.set(time.time(), Corr2Sensor.NOMINAL, results[xctr])
    LOGGER.debug('_sensor_xeng_vacc_accs_ps ran on {}'.format(host.host))
    IOLoop.current().call_later(10, _sensor_xeng_vacc_accs_ps, host,
                                host_executor, manager)


@tornado.gen.coroutine
def _sensor_xeng_vacc_sync_time(sensor, host):
    """

    :param sensor:
    :param host:
    :return:
    """
    executor = sensor.executor
    try:
        result = yield executor.submit(host.vacc_get_loadtime)
        sensor.set(time.time(),
                   Corr2Sensor.NOMINAL if result else Corr2Sensor.ERROR, result)
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    except Exception as e:
        LOGGER.error('Error updating VACC sync time sensor for {} - '
                     '{}'.format(host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, False)
    LOGGER.debug('_sensor_xeng_rx ran on {}'.format(host))
    IOLoop.current().call_later(10, _sensor_xeng_vacc_sync_time, sensor, host)


@tornado.gen.coroutine
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
                    (sensor.name.startswith(host_lookup[host.host]))):
                sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
                sensor.previous_value = 0
    except Exception as e:
        LOGGER.error('Error updating counter sensors for {} - '
                     '{}'.format(host, e.message))
        for sensor in manager.sensors.values():
            if ((sensor.name.endswith('-change')) and
                    (sensor.name.startswith(host_lookup[host.host]))):
                sensor.set(time.time(), Corr2Sensor.UNKNOWN, 0)
                sensor.previous_value = 0
    IOLoop.current().call_later(10, _sensor_cb_system_counters,
                                host, host_executor, manager)


@tornado.gen.coroutine
def _sensor_cb_pps(host, host_executor, manager):
    """
    Host PPS counters
    :return:
    """
    def read_gbe_tx_rx(fpga):
        rv = {}
        for gbe in fpga.gbes:
            ctrs = gbe.read_counters()
            link_info = gbe.get_10gbe_core_details()['xaui_status']
            rv[gbe.name] = (ctrs['%s_txctr' % gbe.name],
                            ctrs['%s_rxctr' % gbe.name],
                            str(link_info))
        return rv
    try:
        new_values = yield host_executor.submit(read_gbe_tx_rx, host)
        for gbe in host.gbes:
            hpref = '{host}-{gbe}'.format(host=host_lookup[host.host],
                                          gbe=gbe.name)
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
            sensor.set_value(pps)
            # link-status
            sensor_name = '{pref}{suf}'.format(
                pref=hpref, suf=LINK_STATUS_SUFFIX)
            sensor = manager.sensor_get(sensor_name)
            sensor.set_value(new_values[gbe.name][2])
    except (KatcpRequestError, KatcpRequestFail, KatcpRequestInvalid):
        for gbe in host.gbes:
            hpref = '{host}-{gbe}'.format(host=host_lookup[host.host],
                                          gbe=gbe.name)
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
            hpref = '{host}-{gbe}'.format(host=host_lookup[host.host],
                                          gbe=gbe.name)
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


@tornado.gen.coroutine
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
                     '{}'.format(host, e.message))
        sensor.set(time.time(), Corr2Sensor.UNKNOWN, '')
    LOGGER.debug('_sensor_cb_reorder_status ran on {}'.format(host))
    IOLoop.current().call_later(10, _sensor_cb_reorder_status, sensor, host)


def _setup_sensors_bengine(sens_man, general_executor, host_executors, ioloop):
    """
    Set up the B-engine specific sensors.
    :param sens_man:
    :param general_executor:
    :param host_executors:
    :param ioloop:
    :return:
    """
    # TODO - right now this just mirrors the xhostn-lru-ok sensors

    # B-engine host sensors
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_lookup[_x.host]
        bhost = xhost.replace('xhost', 'bhost')

        # LRU okay
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-lru-ok'.format(bhost),
            'B-engine %s LRU okay' % _x.host, Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_cb_xlru, sensor, _x)


def _setup_sensors_xengine(sens_man, general_executor, host_executors, ioloop):
    """
    Set up the X-engine specific sensors.
    :param sens_man:
    :param general_executor:
    :param host_executors:
    :param ioloop:
    :return:
    """
    # X-engine host sensors
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_lookup[_x.host]

        # LRU okay
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-lru-ok'.format(xhost),
            'X-engine %s LRU okay' % _x.host, Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_cb_xlru, sensor, _x)

        # Raw RX - gbe counters must increment
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-network-rx-ok'.format(xhost),
            'X-engine network RX okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_xhost_check_network_rx, sensor, _x)

        # Rx reorder counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-reorder-ok'.format(xhost),
            'X-engine RX okay - reorder counters incrementing correctly',
            Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_xeng_rx_reorder, sensor, _x)

        # VACC counters
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}-xeng{xctr}'.format(xhost=xhost, xctr=xctr)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-arm-cnt'.format(pref=pref),
                'Number of times this VACC has armed.',
                Corr2Sensor.UNKNOWN, '', executor)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-ctr'.format(pref=pref),
                'Number of accumulations this VACC has performed.',
                Corr2Sensor.UNKNOWN, '', executor)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-error-ctr'.format(pref=pref),
                'Number of VACC errors.',
                Corr2Sensor.UNKNOWN, '', executor)
            sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}-vacc-load-ctr'.format(pref=pref),
                'Number of times this VACC has been loaded.',
                Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_xeng_vacc_ctrs, _x, executor,
                            sens_man)

        # VACC accumulations per second
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}-xeng{xctr}-'.format(xhost=xhost, xctr=xctr)
            sensor = sens_man.do_sensor(
                Corr2Sensor.float, '{pref}accs-per-sec'.format(pref=pref),
                'Number of accumulations per second for this X-engine on '
                'this host.',
                Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_xeng_vacc_accs_ps, _x, executor,
                            sens_man)

        # VACC synch time
        sensor = sens_man.do_sensor(
            Corr2Sensor.integer, '{}-vacc-sync-time'.format(xhost),
            'X-engine VACC sync time - when was the VACC last syncd, in '
            'ADC ticks',
            Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_xeng_vacc_sync_time, sensor, _x)

        # Raw TX - gbe counters must increment, report the counters also
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-network-tx-ok'.format(xhost),
            'X-engine network TX okay', Corr2Sensor.UNKNOWN, '', None)
        for gbe in _x.gbes:
            sensor = sens_man.do_sensor(
                Corr2Sensor.integer,
                '{xhost}-network-{gbe}-tx-ctr'.format(
                    xhost=xhost, gbe=gbe.name),
                'X-engine network TX counter', Corr2Sensor.UNKNOWN,
                '', executor)
        ioloop.add_callback(_xhost_report_network_tx, sens_man, _x)


def _setup_sensors_fengine(sens_man, general_executor, host_executors, ioloop):
    """
    Set up the F-engine specific sensors.
    :param sens_man:
    :param general_executor:
    :param host_executors:
    :param ioloop:
    :return:
    """
    # F-engine received timestamps okay and per-host received timestamps
    sensor_ok = sens_man.do_sensor(
        Corr2Sensor.boolean, 'feng-rxtime-ok',
        'Are the times received by F-engines in the system okay?',
        Corr2Sensor.UNKNOWN, '', general_executor)
    sensor_values = {}
    for _f in sens_man.instrument.fhosts:
        fhost = host_lookup[_f.host]
        sensor = sens_man.do_sensor(
            Corr2Sensor.integer, '{}-rxtimestamp'.format(fhost),
            'F-engine %s - sample-counter timestamps received from the '
            'digitisers' % _f.host,
            Corr2Sensor.UNKNOWN)
        sensor_u = sens_man.do_sensor(
            Corr2Sensor.float, '{}-rxtime-unix'.format(fhost),
            'F-engine %s - UNIX timestamps received from '
            'the digitisers' % _f.host,
            Corr2Sensor.UNKNOWN)
        sensor_values[_f.host] = (sensor, sensor_u)
    ioloop.add_callback(_sensor_cb_feng_rxtime, sensor_ok, sensor_values)

    # F-engine host sensors
    for _f in sens_man.instrument.fhosts:
        executor = host_executors[_f.host]
        fhost = host_lookup[_f.host]

        #TODO: add check for sync cnt. If SKARAB requires resync, must set delay to zero, resync and then continue delay operations.

        # Raw RX - gbe counters must increment
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-network-rx-ok'.format(fhost),
            'F-engine network RX okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_fhost_check_network_rx, sensor, _f)

        # Rx reorder counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-reorder-ok'.format(fhost),
            'F-engine RX okay - reorder counters incrementing correctly',
            Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_feng_rx_reorder, sensor, _f)

        # TODO: reenable this check. Go into warning if no updates received in period.
        # # Delay functionality
        # sensor = sens_man.do_sensor(
        #     Corr2Sensor.boolean, '{}-delays-ok'.format(fhost),
        #     'F-engine delay functionality okay',
        #     Corr2Sensor.UNKNOWN, '', executor)
        # ioloop.add_callback(_sensor_cb_fdelays, sensor, _f)

        # PFB counters
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-pfb-ok'.format(fhost),
            'F-engine PFB okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_feng_pfb_okay, sensor, _f)

        #TODO: Add CT/HMC counters.

        # Raw TX - gbe counters must increment
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-network-tx-ok'.format(fhost),
            'F-engine network TX okay', Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_fhost_check_network_tx, sensor, _f)

        # Overall LRU okay
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}-lru-ok'.format(fhost),
            'F-engine %s LRU okay' % _f.host, Corr2Sensor.UNKNOWN, '', executor)
        ioloop.add_callback(_sensor_cb_flru, sensor, _f)



def setup_sensors(sensor_manager, enable_counters=False):
    """
    INSTRUMENT-STATE-INDEPENDENT sensors to be reported to CAM
    :param sensor_manager: A SensorManager instance
    :param enable_counters: Enable the counter-value-changed sensors
    :return:
    """
    # make the mapping of hostnames to host offsets
    for ctr, host in enumerate(sensor_manager.instrument.xhosts):
        assert host.host not in host_lookup
        host_lookup[host.host] = 'xhost{}'.format(ctr)
    for ctr, host in enumerate(sensor_manager.instrument.fhosts):
        assert host.host not in host_lookup
        host_lookup[host.host] = 'fhost{}'.format(ctr)

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

    _setup_sensors_fengine(sens_man, general_executor, host_executors, ioloop)
    _setup_sensors_xengine(sens_man, general_executor, host_executors, ioloop)
    _setup_sensors_bengine(sens_man, general_executor, host_executors, ioloop)

    all_hosts = sens_man.instrument.fhosts + sens_man.instrument.xhosts

    sensor = sens_man.do_sensor(
                Corr2Sensor.string,
                'hostname-functional-mapping',
                'On which hostname is which functional host?',
                Corr2Sensor.NOMINAL, '', None)
    sensor.set_value(str(host_lookup))

    # gbe packet-per-second counters
    for _h in all_hosts:
        executor = host_executors[_h.host]
        for gbe in _h.gbes:
            hpref = '{host}-{gbe}'.format(host=host_lookup[_h.host],
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

        # DEPRECATED - ALREADY HAPPENING IN F- and X- SECTIONS
        # # reorder counters
        # sensor = sens_man.do_sensor(
        #     Corr2Sensor.string, '%s-reorder-status' % _h.host,
        #     'Host %s reorder block status' % _h.host,
        #     Corr2Sensor.UNKNOWN, '', executor)
        # ioloop.add_callback(_sensor_cb_reorder_status, sensor, _h)

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
