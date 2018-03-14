import logging
import tornado.gen as gen

from tornado.ioloop import IOLoop

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid
from casperfpga.transport_skarab import \
    SkarabReorderError, SkarabReorderWarning

from sensors import Corr2Sensor, boolean_sensor_do

LOGGER = logging.getLogger(__name__)

FHOST_REGS = ['spead_status', 'reorder_status', 'sync_ctrs', 'pfb_status', 
              'cd_status', 'quant_status']
#FHOST_REGS.extend(['ct_status%i' % ctr for ctr in range(2)])
#FHOST_REGS.extend(['gbe%i_txctr' % ctr for ctr in range(1)])
#FHOST_REGS.extend(['gbe%i_txofctr' % ctr for ctr in range(1)])
#FHOST_REGS.extend(['gbe%i_rxctr' % ctr for ctr in range(1)])
#FHOST_REGS.extend(['gbe%i_rxofctr' % ctr for ctr in range(1)])
#FHOST_REGS.extend(['gbe%i_rxbadctr' % ctr for ctr in range(1)])

host_offset_lookup = {}

@gen.coroutine
def _cb_fhost_lru(sensor_manager, sensor, f_host):
    """
    Sensor call back function for F-engine LRU
    :param sensor:
    :return:
    """
    try:
        h=host_offset_lookup[f_host.host]
        if sensor_manager.sensor_get("{}.network.device-status".format(h)).status()==Corr2Sensor.ERROR:
            status=Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.network-reord.device-status".format(h)).status()==Corr2Sensor.ERROR:
            status=Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.cd.device-status".format(h)).status()==Corr2Sensor.ERROR:
            status=Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.ct.device-status".format(h)).status()==Corr2Sensor.ERROR:
            status=Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.rx-timestamp".format(h)).status()==Corr2Sensor.ERROR:
            status=Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.network.device-status".format(h)).status()==Corr2Sensor.WARN:
            status=Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.pfb.device-status".format(h)).status()==Corr2Sensor.WARN:
            status=Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.cd.device-status".format(h)).status()==Corr2Sensor.WARN:
            status=Corr2Sensor.WARN
        else:
            status=Corr2Sensor.NOMINAL
        sensor.set(value=False,status=status)
    except Exception as e:
        LOGGER.error(
            'Error updating LRU sensor for {} - {}'.format(
                f_host.host, e.message))
        sensor.set(value=False,status=Corr2Sensor.FAILURE)
    
    LOGGER.debug('_cb_fhost_lru ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_fhost_lru, sensor_manager, sensor, f_host)

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
        if result:
            sensor_ok.set(value=result,status=Corr2Sensor.NOMINAL)
        else:
            sensor_ok.set(value=result,status=Corr2Sensor.ERROR)
        for host in counts:
            sensor, sensor_u = sensors_value[host]
            sensor.set(value=counts[host],errif='notchanged')
            if times[host]>0:
                sensor_u.set(value=times[host],errif='notchanged')
            else:
                sensor_u.set(value=times[host],status=Corr2Sensor.FAILURE)
    except Exception as e:
        raise
        sensor_ok.set(value=False,status=Corr2Sensor.FAILURE)
        for sensor, sensor_u in sensors_value.values():
            sensor.set(value=0,status=Corr2Sensor.FAILURE)
            sensor_u.set(value=0,status=Corr2Sensor.FAILURE)
        LOGGER.error('Error updating feng rxtime sensor '
                     '- {}'.format(e.message))
    LOGGER.debug('_cb_feng_rxtime ran')
    IOLoop.current().call_later(10, _cb_feng_rxtime,
                                sensor_ok, sensors_value)

@gen.coroutine
def _cb_feng_delays(sensors, f_host):
    """
    Sensor call back function for F-engine delay functionality
    :param sensor:
    :return:
    """
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
            
    executor = sensors['cd_hmc_err_cnt'].executor
    try:
        results = yield executor.submit(f_host.get_cd_status)
        device_status=Corr2Sensor.NOMINAL
        cd0_cnt=f_host.registers.tl_cd0_status.read()['data']['load_count']
        cd1_cnt=f_host.registers.tl_cd1_status.read()['data']['load_count']
        if cd0_cnt == sensors['delay0_updating'].tempstore:
            sensors['delay0_updating'].set(value=False,status=Corr2Sensor.WARN)
            device_status=Corr2Sensor.WARN
        else:
            sensors['delay0_updating'].set(value=True,status=Corr2Sensor.NOMINAL)
        if cd1_cnt == sensors['delay1_updating'].tempstore:
            sensors['delay1_updating'].set(value=False,status=Corr2Sensor.WARN)
            device_status=Corr2Sensor.WARN
        else:
            sensors['delay1_updating'].set(value=True,status=Corr2Sensor.NOMINAL)
        sensors['delay0_updating'].tempstore=cd0_cnt
        sensors['delay1_updating'].tempstore=cd1_cnt
        sensors['cd_hmc_err_cnt'].set(value=results['err_cnt'],errif='changed')
        if sensors['cd_hmc_err_cnt'].status()==Corr2Sensor.ERROR:
            device_status=Corr2Sensor.ERROR
        device_status_value=True if device_status==Corr2Sensor.NOMINAL else False
        sensors['device-status'].set(value=device_status_value,status=device_status)

    except Exception as e:
        LOGGER.error(
            'Error updating delay sensors for {} - {}'.format(
                f_host.host, e.message))
        set_failure()
    LOGGER.debug('_sensor_feng_delays ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_delays, sensors, f_host)

@gen.coroutine
def _cb_feng_ct(sensors, f_host):
    """
    Sensor call back function to check F-engine corner-turner.
    :param sensor:
    :return:
    """
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
    executor = sensors['pol0_post'].executor
    try:
        results = yield executor.submit(f_host.get_ct_status)
        pol0_errs=results[0]['rd_not_rdy']|results[0]['wr_not_rdy']|results[0]['fifo_full']
        pol1_errs=results[1]['rd_not_rdy']|results[1]['wr_not_rdy']|results[1]['fifo_full']
        pol0_status=Corr2Sensor.ERROR if pol0_errs else Corr2Sensor.NOMINAL
        pol1_status=Corr2Sensor.ERROR if pol1_errs else Corr2Sensor.NOMINAL
        sensors['pol0_err'].set(value=pol0_errs,status=pol0_status)
        sensors['pol1_err'].set(value=pol1_errs,status=pol1_status)
        pol0_status=Corr2Sensor.NOMINAL if results[0]['hmc_post'] else Corr2Sensor.ERROR
        pol1_status=Corr2Sensor.NOMINAL if results[1]['hmc_post'] else Corr2Sensor.ERROR
        sensors['pol0_post'].set(value=results[0]['hmc_post'],status=pol0_status)
        sensors['pol1_post'].set(value=results[1]['hmc_post'],status=pol1_status)
        sensors['pol0_crc_err_cnt'].set(value=results[0]['crc_err_cnt'],errif='changed')
        sensors['pol1_crc_err_cnt'].set(value=results[1]['crc_err_cnt'],errif='changed')
        if ((sensors['pol0_err'].status()==Corr2Sensor.ERROR) or
            (sensors['pol1_err'].status()==Corr2Sensor.ERROR) or
            (sensors['pol0_crc_err_cnt'].status()==Corr2Sensor.ERROR) or
            (sensors['pol1_crc_err_cnt'].status()==Corr2Sensor.ERROR) or
            (sensors['pol0_post'].status()==Corr2Sensor.ERROR) or
            (sensors['pol1_post'].status()==Corr2Sensor.ERROR)):
            sensors['device-status'].set(value=False,status=Corr2Sensor.ERROR)
        else:
            sensors['device-status'].set(value=True,status=Corr2Sensor.NOMINAL)
    except Exception as e:
        LOGGER.error(
            'Error updating CT sensors for {} - {}'.format(
                f_host.host, e.message))
    LOGGER.debug('_cb_feng_ct ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_ct, sensors, f_host)

@gen.coroutine
def _cb_feng_pack(sensors, f_host):
    """
    Sensor call back function to check F-engine pack block.
    :param sensor:
    :return:
    """
    executor=sensors['err_cnt'].executor
    try:
        results = yield executor.submit(f_host.get_pack_status)
        sensors['err_cnt'].set(value=results['dvblock_err_cnt'],errif='changed')
        if sensors['err_cnt'].status()==Corr2Sensor.NOMINAL:
            status=Corr2Sensor.NOMINAL
            value=True
        else:
            status=Corr2Sensor.ERROR
            value=False
        sensors['device-status'].set(value=value,status=status)
    except Exception as e:
        LOGGER.error(
            'Error updating pack sensors for {} - {}'.format(
                f_host.host, e.message))
        sensors['device-status'].set(value=False,status=Corr2Sensor.FAILURE)
        sensors['err_cnt'].set(value=-1,status=Corr2Sensor.FAILURE)
    LOGGER.debug('_cb_feng_pack ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_pack, sensors, f_host)


@gen.coroutine
def _cb_feng_pfbs(sensors, f_host):
    """
    F-engine PFB check
    :param sensor:
    :return:
    """
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
            
    executor = sensors['sync_cnt'].executor
    try:
        results = yield executor.submit(f_host.get_pfb_status)
        device_status=Corr2Sensor.NOMINAL
        for key in ['pol0_or_err_cnt','pol1_or_err_cnt','sync_cnt']:
            sensor=sensors[key]
            sensor.set(value=results[key],warnif='changed')
            if sensor.status()==Corr2Sensor.WARN:
                device_status=Corr2Sensor.WARN
        device_status_value=(device_status==Corr2Sensor.NOMINAL)
        sensors['device-status'].set(value=device_status_value,status=device_status)
    except Exception as e:
        LOGGER.error(
            'Error updating PFB sensors for {} - {}'.format(
                f_host.host, e.message))
        set_failure()
    LOGGER.debug('_sensor_feng_pfbs ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_pfbs, sensors, f_host)


@gen.coroutine
def _cb_fhost_check_network(sensors, f_host):
    """
    Check that the f-hosts are receiving data correctly
    :param sensors: a dict of the network sensors to update
    :return:
    """
    #GBE CORE
    executor = sensors['tx_pps'].executor
    device_status=Corr2Sensor.NOMINAL
    try:
        result = yield executor.submit(f_host.gbes.gbe0.get_stats)
        sensors['tx_err_cnt'].set(errif='changed', value=result['tx_over'])
        sensors['rx_err_cnt'].set(errif='changed', value=result['rx_bad_pkts'])
        sensors['tx_pps'].set(status=Corr2Sensor.NOMINAL, value=result['tx_pps'])
        sensors['tx_gbps'].set(status=Corr2Sensor.NOMINAL, value=result['tx_gbps'])

        if (result['rx_pps']>900000) and (result['rx_pps']<950000):
            sensors['rx_pps'].set(status=Corr2Sensor.NOMINAL, value=result['rx_pps'])
        else:
            sensors['rx_pps'].set(status=Corr2Sensor.WARN, value=result['rx_pps'])
            device_status=Corr2Sensor.WARN

        if (result['rx_gbps']>35) and (result['rx_gbps']<38):
            sensors['rx_gbps'].set(status=Corr2Sensor.NOMINAL, value=result['rx_gbps'])
        else:
            sensors['rx_gbps'].set(status=Corr2Sensor.WARN, value=result['rx_gbps'])
            device_status=Corr2Sensor.WARN

        if ((sensors['tx_err_cnt'].status()==Corr2Sensor.ERROR) or
            (sensors['rx_err_cnt'].status()==Corr2Sensor.ERROR)):
                device_status=Corr2Sensor.ERROR
        device_status_value=(device_status==Corr2Sensor.NOMINAL)
        sensors['device-status'].set(value=device_status_value,status=device_status)
    except Exception as e:
        LOGGER.error(
            'Error updating gbe_stats for {} - {}'.format(
                f_host.host, e.message))
        sensors['tx_pps'].set(status=Corr2Sensor.FAILURE, value=-1)
        sensors['rx_pps'].set(status=Corr2Sensor.FAILURE, value=-1)
        sensors['tx_gbps'].set(status=Corr2Sensor.FAILURE, value=-1)
        sensors['rx_gbps'].set(status=Corr2Sensor.FAILURE, value=-1)
        sensors['tx_err_cnt'].set(status=Corr2Sensor.FAILURE, value=-1)
        sensors['rx_err_cnt'].set(status=Corr2Sensor.FAILURE, value=-1)
        sensors['device-status'].set(status=Corr2Sensor.FAILURE, value=-1)
    
    LOGGER.debug('_cb_fhost_check_network ran')
    IOLoop.current().call_later(10, _cb_fhost_check_network, sensors, f_host)

@gen.coroutine
def _cb_feng_rx_spead(sensors, f_host):
    """
    F-engine SPEAD unpack block
    :param sensor:
    :return: true/false
    """
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
            
    # SPEAD RX
    executor = sensors['cnt'].executor
    try:
        results = yield executor.submit(f_host.get_unpack_status)
#        accum_errors=0
#        for key in ['header_err_cnt','magic_err_cnt','pad_err_cnt','pkt_len_err_cnt','time_err_cnt']:
#            accum_errors+=results[key]
        sensors['time_err_cnt'].set(value=results['time_err_cnt'],errif='changed')
        sensors['cnt'].set(value=results['pkt_cnt'],warnif='notchanged')
        timestamp, status, value = sensors['cnt'].read()
        value=(status==Corr2Sensor.NOMINAL)
        sensors['device-status'].set(value=value,status=status)
    except Exception as e:
        LOGGER.error(
            'Error updating spead sensors for {} - {}'.format(
                f_host.host, e.message))
        set_failure()
    LOGGER.debug('_sensor_feng_rx_spead ran on {}: {}'.format(f_host.host,results))
    IOLoop.current().call_later(10, _cb_feng_rx_spead, sensors, f_host)


@gen.coroutine
def _cb_feng_rx_reorder(sensors, f_host):
    """
    F-engine RX reorder counters
    :param sensors: dictionary of sensors
    :return: true/false
    """
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    executor = sensors['timestep_err_cnt'].executor
    try:
        results = yield executor.submit(f_host.get_rx_reorder_status)
        device_status=True
        for key in ['timestep_err_cnt','receive_err_cnt','discard_cnt','relock_err_cnt','overflow_err_cnt']:
            sensor=sensors[key]
            #print('Processing {},{}: {}'.format(key,sensor.name,results[key]))
            sensor.set(value=results[key],errif='changed')
            if sensor.status()==Corr2Sensor.ERROR:
                device_status=False
        if device_status:
            sensors['device-status'].set(status=Corr2Sensor.NOMINAL,value=True)
        else:
            sensors['device-status'].set(status=Corr2Sensor.ERROR,value=False)
    except Exception as e:
        LOGGER.error('Error updating rx_reorder sensors for {} - '
                     '{}'.format(f_host.host, e.message))
        set_failure()

    LOGGER.debug('_sensor_feng_rx_reorder ran on {}'.format(f_host.host))
    IOLoop.current().call_later(10, _cb_feng_rx_reorder, sensors, f_host)


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
    global host_offset_lookup
    if len(host_offset_lookup) == 0:
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
            Corr2Sensor.integer, '{}.rx-timestamp'.format(fhost),
            'F-engine %s - sample-counter timestamps received from the '
            'digitisers' % _f.host)
        sensor_u = sens_man.do_sensor(
            Corr2Sensor.float, '{}.rx-unixtime'.format(fhost),
            'F-engine %s - UNIX timestamps received from '
            'the digitisers' % _f.host)
        sensors_value[_f.host] = (sensor, sensor_u)
    ioloop.add_callback(_cb_feng_rxtime, sensor_ok, sensors_value)

    # F-engine host sensors
    for _f in sens_man.instrument.fhosts:
        executor = host_executors[_f.host]
        fhost = host_offset_lookup[_f.host]
        # raw network comms - gbe counters must increment
        network_sensors = {
            'device-status': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}.network.device-status'.format(fhost),
                'F-engine network interface ok.', executor=executor),
            'tx_pps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.network.tx-pps'.format(fhost),
                'F-engine network raw TX packets per second', executor=executor),
            'rx_pps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.network.rx-pps'.format(fhost),
                'F-engine network raw RX packets per second', executor=executor),
            'tx_gbps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.network.tx-gbps'.format(fhost),
                'F-engine network raw TX rate (gigabits per second)', executor=executor),
            'rx_gbps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.network.rx-gbps'.format(fhost),
                'F-engine network raw RX rate (gibabits per second)', executor=executor),
            'tx_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.network.tx-err-cnt'.format(fhost),
                'TX network error count', executor=executor),
            'rx_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.network.tx-err-cnt'.format(fhost),
                'RX network error count (bad packets received)', executor=executor),
        }
        ioloop.add_callback(_cb_fhost_check_network, network_sensors, _f)

        # SPEAD counters
        sensors = {
        'device-status': sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.spead-rx.device-status'.format(fhost),
            'F-engine is not encountering SPEAD errors.', executor=executor),
#            'err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-timestamp-err-cnt'.format(fhost),
#            'F-engine RX SPEAD packet errors',
#            executor=executor),
        'cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.spead-rx.pkt-cnt'.format(fhost),
            'F-engine RX SPEAD packet counter',
            executor=executor),
#            'header_err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-header-err-cnt'.format(fhost),
#            'F-engine RX SPEAD packet unpack header errors',
#            executor=executor),
#            'magic_err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-magic-err-cnt'.format(fhost),
#            'F-engine RX SPEAD magic field errors',
#            executor=executor),
#            'pad_err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-pad-err-cnt'.format(fhost),
#            'F-engine RX SPEAD padding errors',
#            executor=executor),
#            'pkt_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-pkt-cnt'.format(fhost),
#            'F-engine RX SPEAD packet count',
#            executor=executor),
#            'pkt_len_err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-pkt-len-err-cnt'.format(fhost),
#            'F-engine RX SPEAD packet length errors',
#            executor=executor),
        'time_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.spead-rx.pkt-time-err-cnt'.format(fhost),
            'F-engine RX SPEAD packet timestamp has non-zero lsbs.',
            executor=executor),
        }
        ioloop.add_callback(_cb_feng_rx_spead, sensors, _f)

        # Rx reorder counters
        sensors = {
        'device-status': sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.network-reorder.device-status'.format(fhost),
            'F-engine is receiving a good, clean digitiser data stream.',
            executor=executor),
        'timestep_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.network-reorder.timestep-err-cnt'.format(fhost),
            'F-engine RX timestamps not incrementing correctly.',
            executor=executor),
        'receive_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.network-reorder.miss-err-cnt'.format(fhost),
            'F-engine error reordering packets: missing packet.',
            executor=executor),
        'discard_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.network-reorder.discard-err-cnt'.format(fhost),
            'F-engine error reordering packets: discarded packet (bad timestamp).',
            executor=executor),
        'relock_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.network-reorder.relock-err-cnt'.format(fhost),
            'F-engine error reordering packets: relocked to deng stream count.',
            executor=executor),
        'overflow_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.network-reorder.overflow-err-cnt'.format(fhost),
            'F-engine error reordering packets: input buffer overflow.',
            executor=executor),
        }
        ioloop.add_callback(_cb_feng_rx_reorder, sensors, _f)

        # CD functionality
        sensors = {
        'device-status': sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.cd.device-status'.format(fhost),
            'F-engine coarse delays ok.', executor=executor),
        'cd_hmc_err_cnt':sens_man.do_sensor(
            Corr2Sensor.integer, '{}.cd.hmc-err-cnt'.format(fhost),
            'F-engine HMC Coarse Delay failure count.',
            executor=executor),
        'delay0_updating':sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.cd.delay0-updating'.format(fhost),
            'Delay updates are being received and applied.',
            executor=executor),
        'delay1_updating':sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.cd.delay1-updating'.format(fhost),
            'Delay updates are being received and applied.',
            executor=executor),
        }
        sensors['delay0_updating'].tempstore=0
        sensors['delay1_updating'].tempstore=0
        ioloop.add_callback(_cb_feng_delays, sensors, _f)

        # PFB counters
        sensors = {
        'device-status': sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.pfb.device-status'.format(fhost),
            'F-engine PFB ok.', executor=executor),
        'pol0_or_err_cnt':sens_man.do_sensor(
            Corr2Sensor.integer, '{}.pfb.or0-err-cnt'.format(fhost),
            'F-engine PFB over-range counter', executor=executor),
        'pol1_or_err_cnt':sens_man.do_sensor(
            Corr2Sensor.integer, '{}.pfb.or1-err-cnt'.format(fhost),
            'F-engine PFB over-range counter', executor=executor),
        'sync_cnt':sens_man.do_sensor(
            Corr2Sensor.integer, '{}.pfb.sync-cnt'.format(fhost),
            'F-engine PFB resync counter', executor=executor),
        }
        ioloop.add_callback(_cb_feng_pfbs, sensors, _f)

        # CT functionality
        sensors = {
        'device-status': sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.ct.device-status'.format(fhost),
            'F-engine Corner-Turner ok.', executor=executor),
        'pol0_post':sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.ct.post0'.format(fhost),
            'F-engine corner-turner init&POST, pol0', executor=executor),
        'pol1_post':sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.ct.post1'.format(fhost),
            'F-engine corner-turner init&POST, pol1', executor=executor),
        'pol0_err':sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.ct.err0'.format(fhost),
            'F-engine corner-turner error occurred, pol0 (latching)', executor=executor),
        'pol1_err':sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.ct.err1'.format(fhost),
            'F-engine corner-turner error occurred, pol1 (latching)', executor=executor),
        'pol0_crc_err_cnt':sens_man.do_sensor(
            Corr2Sensor.integer, '{}.ct.crc0-err-cnt'.format(fhost),
            'F-engine corner-turner HMC CRC error count, pol0.', executor=executor),
        'pol1_crc_err_cnt':sens_man.do_sensor(
            Corr2Sensor.integer, '{}.ct.crc1-err-cnt'.format(fhost),
            'F-engine corner-turner HMC CRC error count, pol1.', executor=executor),
        }
        ioloop.add_callback(_cb_feng_ct, sensors, _f)
        
        #Pack block
        sensors = {
        'device-status': sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.spead-tx.device-status'.format(fhost),
            'F-engine packetiser (TX) is ok.', executor=executor),
        'err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.spead-tx.err-cnt'.format(fhost),
            'F-engine pack (TX) error count', executor=executor)
        }
        ioloop.add_callback(_cb_feng_pack, sensors, _f)

        # Overall LRU ok
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.device-status'.format(fhost),
            'F-engine %s LRU ok' % _f.host, executor=executor)
        ioloop.add_callback(_cb_fhost_lru, sens_man, sensor, _f)


# end
