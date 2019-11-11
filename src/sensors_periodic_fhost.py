import logging
import tornado.gen as gen
import tornado
import time

from tornado.ioloop import IOLoop

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid
from casperfpga.transport_skarab import \
    SkarabReorderError, SkarabReorderWarning

import sensor_scheduler
from sensors import Corr2Sensor, boolean_sensor_do

LOGGER = logging.getLogger(__name__)

host_offset_lookup = {}

@gen.coroutine
def _cb_fhost_lru(sensor_manager, sensor, f_host,sensor_task):
    """
    Sensor call back function for F-engine LRU
    :param sensor:
    :return:
    """
    
    functionStartTime = time.time();
    ##print("1 on %s Started at %f" % (f_host.host ,functionStartTime))

    try:
        h = host_offset_lookup[f_host.host]
        if sensor_manager.sensor_get(
                "{}.network.device-status".format(h)).status() == Corr2Sensor.ERROR:
            status = Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.network-reorder.device-status".format(h)).status() == Corr2Sensor.ERROR:
            status = Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.cd.device-status".format(h)).status() == Corr2Sensor.ERROR:
            status = Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.ct.device-status".format(h)).status() == Corr2Sensor.ERROR:
            status = Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.sync.device-status".format(h)).status() == Corr2Sensor.ERROR:
            status = Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.rx-timestamp".format(h)).status() == Corr2Sensor.ERROR:
            status = Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.network.device-status".format(h)).status() == Corr2Sensor.ERROR:
            status = Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.network.device-status".format(h)).status() == Corr2Sensor.WARN:
            status = Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.pfb.device-status".format(h)).status() == Corr2Sensor.WARN:
            status = Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.quant.device-status".format(h)).status() == Corr2Sensor.WARN:
            status = Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.cd.device-status".format(h)).status() == Corr2Sensor.WARN:
            status = Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.dig.device-status".format(h)).status() == Corr2Sensor.WARN:
            status = Corr2Sensor.WARN
        else:
            status = Corr2Sensor.NOMINAL

        sens_val = 'fail'
        if(status == Corr2Sensor.NOMINAL):
            sens_val = 'ok'
        elif(status == Corr2Sensor.WARN):
            sens_val = 'degraded'

        sensor.set(value=sens_val, status=status)
    except Exception as e:
        sensor_manager.logger.error(
            'Error updating LRU sensor for {} - {}'.format(
                f_host.host, e.message))
        sensor.set(value="ok", status=Corr2Sensor.FAILURE)

    
    

    functionRunTime = time.time() - functionStartTime;
    nextCallTime = sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime);
    #sensor_manager.logger.debug('Sensor {0: >20} ran on {1: >15} at {2:.4f}. Next Call:{3:.4f} Runtime: {4:.5f}.'.format('_cb_fhost_lru',f_host.host,time.time(),nextCallTime,functionRunTime))

    IOLoop.current().call_at(
        nextCallTime,
        _cb_fhost_lru,
        sensor_manager,
        sensor,
        f_host,sensor_task)


@gen.coroutine
def _cb_feng_rxtime(sensor_ok, sensors_value, sensor_manager,sensor_task):
    """
    Sensor call back to check received F-engine times
    :param sensor_ok: the combined times-are-ok sensor
    :param sensors_value: per-host sensors for time and unix-time
    :return:
    """

    functionStartTime = time.time();
    ##print("2 on all Started at %f" % (functionStartTime))

    instrument = sensor_ok.manager.instrument
    try:
        result, counts, times = instrument.fops.get_rx_timestamps()
        if result:
            sensor_ok.set(value=result, status=Corr2Sensor.NOMINAL)
        else:
            sensor_ok.set(value=result, status=Corr2Sensor.ERROR)
        for host in counts:
            sensor, sensor_u = sensors_value[host]
            sensor.set(value=counts[host], errif='notchanged')
            if times[host] > 0:
                sensor_u.set(value=times[host], errif='notchanged')
            else:
                sensor_u.set(value=times[host], status=Corr2Sensor.FAILURE)
    except Exception as e:
        sensor_ok.set(value=False, status=Corr2Sensor.FAILURE)
        for sensor, sensor_u in sensors_value.values():
            sensor.set(value=0, status=Corr2Sensor.FAILURE)
            sensor_u.set(value=0, status=Corr2Sensor.FAILURE)
        sensor_manager.logger.error('Error updating feng rxtime sensor '
                     '- {}.'.format(e.message))
    sensor_manager.logger.debug('_cb_feng_rxtime ran')
    
    functionRunTime = time.time() - functionStartTime;
    ##print("2 on all Ended End Time %f, Run Time %f" % (time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,'2'))

    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_rxtime,
                                sensor_ok, sensors_value, sensor_manager,sensor_task)


@gen.coroutine
def _cb_feng_delays(sensors, f_host, sensor_manager,sensor_task):
    """
    Sensor call back function for F-engine delay functionality
    :param sensor:
    :return:
    """
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();
    ##print("3 on %s Started at %f" % (f_host.host ,functionStartTime))

    device_status = Corr2Sensor.NOMINAL
    device_status_value = 'ok'
    try:
        cd0_cnt = f_host.registers.tl_cd0_status.read()['data']['load_count']
        cd1_cnt = f_host.registers.tl_cd1_status.read()['data']['load_count']
        if cd0_cnt == sensors['delay0_updating'].tempstore:
            sensors['delay0_updating'].set(
                value=False, status=Corr2Sensor.WARN)
            device_status = Corr2Sensor.WARN
            device_status_value = 'degraded'
        else:
            sensors['delay0_updating'].set(
                value=True, status=Corr2Sensor.NOMINAL)
        if cd1_cnt == sensors['delay1_updating'].tempstore:
            sensors['delay1_updating'].set(
                value=False, status=Corr2Sensor.WARN)
            device_status = Corr2Sensor.WARN
            device_status_value = 'degraded'
        else:
            sensors['delay1_updating'].set(
                value=True, status=Corr2Sensor.NOMINAL)
        sensors['delay0_updating'].tempstore = cd0_cnt
        sensors['delay1_updating'].tempstore = cd1_cnt

        results = f_host.get_cd_status()
        sensors['current_cd0'].set(
            value=results['current_cd0'], status=Corr2Sensor.NOMINAL)
        sensors['current_cd1'].set(
            value=results['current_cd1'], status=Corr2Sensor.NOMINAL)

        pol0_errs = results['hmc_err_cnt'] + results['reord_jitter_err_cnt_pol0'] + \
            results['hmc_overflow_err_cnt_pol0'] + results['parity_err_cnt_pol0'] + \
            results['reord_missing_err_cnt_pol0']
        pol1_errs = results['hmc_err_cnt'] + results['reord_jitter_err_cnt_pol1'] + \
            results['hmc_overflow_err_cnt_pol1'] + results['parity_err_cnt_pol1'] + \
            results['reord_missing_err_cnt_pol1']
        sensors['pol0_err_cnt'].set(value=pol0_errs, errif='changed')
        sensors['pol1_err_cnt'].set(value=pol1_errs, errif='changed')

        if ((sensors['pol0_err_cnt'].status() == Corr2Sensor.ERROR) or
            (sensors['pol1_err_cnt'].status() == Corr2Sensor.ERROR)):
            device_status = Corr2Sensor.ERROR
            device_status_value = 'fail'
            f_host.logger.error("CD error: %s"%str(sensors))
            f_host.logger.error("CD HMC status: %s"%str(f_host.hmcs.cd_hmc_hmc_delay_hmc.get_hmc_status()))

        sensors['device_status'].set(value=device_status_value,
                                     status=device_status)

    except Exception as e:
        sensor_manager.logger.error(
            'Error updating delay sensors for {} - {}.'.format(
                f_host.host, e.message))
        set_failure()
    sensor_manager.logger.debug('_sensor_feng_delays ran on {}'.format(f_host.host))

    functionRunTime = time.time() - functionStartTime;
    ##print("3 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'3'))

    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_delays, sensors, f_host, sensor_manager,sensor_task)


@gen.coroutine
def _cb_feng_ct(sensors, f_host, sensor_manager,sensor_task):
    """
    Sensor call back function to check F-engine corner-turner.
    :param sensor:
    :return:
    """
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();
    ##print("4 on %s Started at %f" % (f_host.host ,functionStartTime))

    try:
        results = f_host.get_ct_status()
        common_errs = results['obuff_bank_err_cnt'] + results['rd_go_err_cnt'] + \
            results['sync_in_err_cnt'] + results['fifo_full_err_cnt']
        pol0_errs = results['bank_err_cnt_pol0'] + \
            results['hmc_overflow_err_cnt_pol0'] + common_errs + \
            results['hmc_err_cnt0'] + results['reorder_missing_err_cnt']
        pol1_errs = results['bank_err_cnt_pol1'] + \
            results['hmc_overflow_err_cnt_pol1'] + common_errs + \
            results['hmc_err_cnt1'] + results['reorder_missing_err_cnt1']
        sensors['pol0_err_cnt'].set(value=pol0_errs, errif='changed')
        sensors['pol1_err_cnt'].set(value=pol1_errs, errif='changed')

        device_status = Corr2Sensor.NOMINAL
        device_value = 'ok'
        if (sensors['pol0_err_cnt'].status() == Corr2Sensor.ERROR):
            device_value = 'fail'
            f_host.logger.error("CT error: %s"%str(results))
            f_host.logger.error("CT hmc0 status: %s"%str(f_host.hmcs.hmc_ct_hmc.get_hmc_status()))
        if (sensors['pol1_err_cnt'].status() == Corr2Sensor.ERROR):
            device_value = 'fail'
            f_host.logger.error("CT error: %s"%str(results))
            f_host.logger.error("CT hmc1 status: %s"%str(f_host.hmcs.hmc_ct_hmc.get_hmc_status()))
        #if(device_status == Corr2Sensor.WARN):
        #    device_value = 'degraded'
        sensors['device_status'].set(value=device_value, status=device_status)
    except Exception as e:
        sensor_manager.logger.error(
            'Error updating CT sensors for {} - {}.'.format(
                f_host.host, e.message))
    sensor_manager.logger.debug('_cb_feng_ct ran on {}'.format(f_host.host))

    functionRunTime = time.time() - functionStartTime;
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'4'))
    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_ct, sensors, f_host, sensor_manager,sensor_task)
    ##print("4 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))


@gen.coroutine
def _cb_feng_pack(sensors, f_host, sensor_manager,sensor_task):
    """
    Sensor call back function to check F-engine pack block.
    :param sensor:
    :return:
    """

    functionStartTime = time.time();
    ##print("5 on %s Started at %f" % (f_host.host ,functionStartTime))

    try:
        results = f_host.get_pack_status()
        sensors['err_cnt'].set(
            value=results['dvblock_err_cnt'],
            errif='changed')
        if sensors['err_cnt'].status() == Corr2Sensor.NOMINAL:
            status = Corr2Sensor.NOMINAL
            value = 'ok'
        else:
            status = Corr2Sensor.ERROR
            value = 'fail'
        sensors['device_status'].set(value=value, status=status)
    except Exception as e:
        sensor_manager.logger.error(
            'Error updating pack sensors for {} - {}.'.format(
                f_host.host, e.message))
        sensors['device_status'].set(value='fail', status=Corr2Sensor.FAILURE)
        sensors['err_cnt'].set(value=-1, status=Corr2Sensor.FAILURE)
    sensor_manager.logger.debug('_cb_feng_pack ran on {}'.format(f_host.host))

    functionRunTime = time.time() - functionStartTime;
    ##print("5 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'5'))

    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_pack, sensors, f_host, sensor_manager,sensor_task)

@gen.coroutine
def _cb_feng_adcs(sensors, f_host, sensor_manager,sensor_task):
    """
    F-engine ADC/DIG check
    :param sensor:
    :return:
    """
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();
    ##print("6 on %s Started at %f" % (f_host.host ,functionStartTime))

    try:
        results = f_host.get_adc_status()
        device_status = Corr2Sensor.NOMINAL

        for key in ['p0_min', 'p1_min']:
            sensor = sensors[key]
            if results[key] < -0.9:
                sensor.set(value=results[key], status=Corr2Sensor.WARN)
                device_status = Corr2Sensor.WARN
            else:
                sensor.set(value=results[key], status=Corr2Sensor.NOMINAL)

        for key in ['p0_max', 'p1_max']:
            sensor = sensors[key]
            if results[key] > 0.9:
                sensor.set(value=results[key], status=Corr2Sensor.WARN)
                device_status = Corr2Sensor.WARN
            else:
                sensor.set(value=results[key], status=Corr2Sensor.NOMINAL)

        for key in ['p0_pwr_dBFS', 'p1_pwr_dBFS']:
            sensor = sensors[key]
            if (results[key] > -22) or (results[key] < -32):
                sensor.set(value=results[key], status=Corr2Sensor.WARN)
                device_status = Corr2Sensor.WARN
                f_host.logger.warn('Input levels ({:.1f}dBFS) are poor on the {} digitiser. Consider adjusting the Digitiser attenuators so Digitiser outputs falls in the range -32 dBFS to -22 dBFS.'.format(results[key],f_host.fengines[int(key[1])].name))
            else:
                sensor.set(value=results[key], status=Corr2Sensor.NOMINAL)

        for key in ['p0_dig_clip_cnt', 'p1_dig_clip_cnt']:
            sensor = sensors[key]
            sensor.set(value=results[key], status=Corr2Sensor.NOMINAL)

        device_status_value = 'fail'
        if(device_status == Corr2Sensor.WARN):
            device_status_value = 'degraded'
        if(device_status == Corr2Sensor.NOMINAL):
            device_status_value = 'ok'

        sensors['device_status'].set(value=device_status_value,
                                     status=device_status)
    except Exception as e:
        sensor_manager.logger.error(
            'Error updating DIG ADC sensors for {} - {}.'.format(
                f_host.host, e.message))
        set_failure()

    sensor_manager.logger.debug('_sensor_feng_adc ran on {}'.format(f_host.host))

    functionRunTime = time.time() - functionStartTime;
    ##print("6 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'6'))

    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_adcs, sensors, f_host, sensor_manager,sensor_task)

@gen.coroutine
def _cb_feng_pfbs(sensors, f_host, min_pfb_pwr, sensor_manager, sensor_task):
    """
    F-engine PFB check
    :param sensor:
    :return:
    """
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();
    ##print("7 on %s Started at %f" % (f_host.host ,functionStartTime))

    try:
        results = f_host.get_pfb_status()
        device_status = Corr2Sensor.NOMINAL
        for key in ['pol0_or_err_cnt', 'pol1_or_err_cnt', 'sync_cnt']:
            sensor = sensors[key]
            sensor.set(value=results[key], warnif='changed')
            if sensor.status() == Corr2Sensor.WARN:
                device_status = Corr2Sensor.WARN

        for key in ['pol0_pfb_out_dBFS','pol1_pfb_out_dBFS']:
            sensor = sensors[key]
            if (results[key] > -24) or (results[key] < min_pfb_pwr):
                sensor.set(value=results[key], status=Corr2Sensor.WARN)
                device_status = Corr2Sensor.WARN
                f_host.logger.warn('PFB output levels ({}dBFS) are poor on {}. Consider adjusting FFT shift so that {} dBFS < PFB output < -24 dBFS.'.format(results[key],f_host.fengines[int(key[3])].name,min_pfb_pwr))
            else:
                sensor.set(value=results[key], status=Corr2Sensor.NOMINAL)

        device_status_value = 'fail'
        if(device_status == Corr2Sensor.WARN):
            device_status_value = 'degraded'
        if(device_status == Corr2Sensor.NOMINAL):
            device_status_value = 'ok'

        sensors['device_status'].set(value=device_status_value,
                                     status=device_status)
    except Exception as e:
        sensor_manager.logger.error(
            'Error updating PFB sensors for {} - {}.'.format(
                f_host.host, e.message))
        set_failure()
    sensor_manager.logger.debug('_sensor_feng_pfbs ran on {}'.format(f_host.host))

    functionRunTime = time.time() - functionStartTime;
    ##print("7 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'7'))
    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_pfbs, sensors, f_host, min_pfb_pwr, sensor_manager,sensor_task)


@gen.coroutine
def _cb_feng_quant(sensors, f_host, sensor_manager,sensor_task):
    """
    F-engine quantiser check
    :param sensor:
    :return:
    """
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();
    ##print("8 on %s Started at %f" % (f_host.host ,functionStartTime))

    try:
        results = f_host.get_quant_status()
        device_status = Corr2Sensor.NOMINAL

        for key in ['p0_quant_out_dBFS','p1_quant_out_dBFS']:
            sensor = sensors[key]
            if (results[key] > -10) or (results[key] < -30):
                sensor.set(value=results[key], status=Corr2Sensor.WARN)
                device_status = Corr2Sensor.WARN
                f_host.logger.warn('Quantiser output levels ({}dBFS) are poor on {}. Check FFT shift and adjust EQ gain so -30 dBFS < quantiser_output < -10 dBFS.'.format(results[key],f_host.fengines[int(key[1])].name))
            else:
                sensor.set(value=results[key], status=Corr2Sensor.NOMINAL)

        device_status_value = 'fail'
        if(device_status == Corr2Sensor.WARN):
            device_status_value = 'degraded'
        if(device_status == Corr2Sensor.NOMINAL):
            device_status_value = 'ok'

        sensors['device_status'].set(value=device_status_value,
                                     status=device_status)
    except Exception as e:
        sensor_manager.logger.error(
            'Error updating quantiser sensors for {} - {}.'.format(
                f_host.host, e.message))
        set_failure()
    sensor_manager.logger.debug('_sensor_feng_quant ran on {}'.format(f_host.host))

    functionRunTime = time.time() - functionStartTime;
    ##print("8 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'8'))
    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_quant, sensors, f_host, sensor_manager,sensor_task)

@gen.coroutine
def _cb_fhost_check_network(sensors, f_host, sensor_manager,sensor_task):
    """
    Check that the f-hosts are receiving data correctly
    :param sensors: a dict of the network sensors to update
    :return:
    """
    # GBE CORE
    functionStartTime = time.time();
    ##print("9 on %s Started at %f" % (f_host.host ,functionStartTime))

    device_status = Corr2Sensor.NOMINAL

    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
            # heck dictionary
    try:
        result = f_host.gbes.gbe0.get_stats()
        tx_enabled = f_host.registers.control.read()['data']['gbe_txen']
        sensors['tx_enabled'].set(errif='False', value=tx_enabled)
        sensors['tx_err_cnt'].set(errif='changed', value=result['tx_over'])
        sensors['rx_err_cnt'].set(errif='changed', value=result['rx_bad_pkts'])
        sensors['tx_pps'].set(
            status=Corr2Sensor.NOMINAL,
            value=result['tx_pps'])
        sensors['tx_gbps'].set(
            status=Corr2Sensor.NOMINAL,
            value=result['tx_gbps'])

# The software-based PPS and Gbps counters aren't reliable, so ignore them for now:
        if (result['rx_pps'] > 800000) and (result['rx_pps'] < 900000):
            sensors['rx_pps'].set(
                status=Corr2Sensor.NOMINAL,
                value=result['rx_pps'])
        else:
            sensors['rx_pps'].set(
                status=Corr2Sensor.WARN,
                value=result['rx_pps'])
            #device_status = Corr2Sensor.WARN

        if (result['rx_gbps'] > 35) and (result['rx_gbps'] < 38):
            sensors['rx_gbps'].set(
                status=Corr2Sensor.NOMINAL,
                value=result['rx_gbps'])
        else:
            sensors['rx_gbps'].set(
                status=Corr2Sensor.WARN,
                value=result['rx_gbps'])
            #device_status = Corr2Sensor.WARN

        if ((sensors['tx_err_cnt'].status() == Corr2Sensor.ERROR) or
            (sensors['rx_err_cnt'].status() == Corr2Sensor.ERROR) or
                (sensors['tx_enabled'].status() == Corr2Sensor.ERROR)):
            device_status = Corr2Sensor.ERROR

        sens_val = 'fail'
        if(device_status == Corr2Sensor.NOMINAL):
            sens_val = 'ok'
        elif(device_status == Corr2Sensor.WARN):
            sens_val = 'degraded'

        sensors['device_status'].set(value=sens_val,
                                     status=device_status)
    except Exception as e:
        sensor_manager.logger.error(
            'Error updating gbe_stats for {} - {}'.format(
                f_host.host, e.message))
        set_failure()
    sensor_manager.logger.debug('_sensor_fhost_check_network ran on {}'.format(f_host.host))

    functionRunTime = time.time() - functionStartTime;
    ##print("9 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'9'))

    IOLoop.current().call_at(
        sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime),
        _cb_fhost_check_network,
        sensors,
        f_host, sensor_manager,sensor_task)

@gen.coroutine
def _cb_feng_sync(sensors, f_host, sensor_manager,sensor_task):
    """
    F-engine synchroniser
    :param sensor:
    :return: 
    """
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();
    ##print("10 on %s Started at %f" % (f_host.host ,functionStartTime))

    device_status = Corr2Sensor.NOMINAL
    try:
        sensors['device_status'].set(value='ok',status=Corr2Sensor.NOMINAL)
        results = f_host.get_sync_status()

        if results['synced'] and not results['board_in_fault']:
            sensors['syncd'].set(value=True,status=Corr2Sensor.NOMINAL)
            sensors['device_status'].set(value='ok',status=Corr2Sensor.NOMINAL)
        else:
            sensors['syncd'].set(value=False,status=Corr2Sensor.FAILURE)
            sensors['device_status'].set(value='fail',status=Corr2Sensor.FAILURE)

        for ret in ['cd_resync_cnt', 'ct_resync_cnt', 'fault_clear_timeout_cnt', 'fault_present_timeout_cnt', 'time_diff_resync_cnt', 'timestep_resync_cnt','timeout_resync_cnt']:
            sensors[ret].set(value=results[ret],errif='changed')

    except Exception as e:
        sensor_manager.logger.error(
            'Error updating sync sensors for {} - {}'.format(
                f_host.host, e.message))
        set_failure()
    sensor_manager.logger.debug(
        '_sensor_feng_sync ran on {}'.format(
            f_host.host))

    functionRunTime = time.time() - functionStartTime;
    ##print("10 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'10'))

    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_sync, sensors, f_host, sensor_manager,sensor_task)

@gen.coroutine
def _cb_feng_rx_spead(sensors, f_host, sensor_manager,sensor_task):
    """
    F-engine SPEAD unpack block
    :param sensor:
    :return: true/false
    """
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])


    functionStartTime = time.time();
    ##print("11 on %s Started at %f" % (f_host.host ,functionStartTime))
    # SPEAD RX
    try:
        results = f_host.get_unpack_status()
#        accum_errors=0
#        for key in ['header_err_cnt','magic_err_cnt','pad_err_cnt','pkt_len_err_cnt','time_err_cnt']:
#            accum_errors+=results[key]
        sensors['time_err_cnt'].set(
            value=results['time_err_cnt'],
            errif='changed')
        sensors['cnt'].set(value=results['pkt_cnt'], warnif='notchanged')
        timestamp, status, value = sensors['cnt'].read()
        value = (status == Corr2Sensor.NOMINAL)

        value = 'fail'
        if(status == Corr2Sensor.NOMINAL):
            value = 'ok'

        sensors['device_status'].set(value=value, status=status)
    except Exception as e:
        sensor_manager.logger.error(
            'Error updating spead sensors for {} - {}'.format(
                f_host.host, e.message))
        set_failure()
    sensor_manager.logger.debug(
        '_sensor_feng_rx_spead ran on {}'.format(
            f_host.host))

    functionRunTime = time.time() - functionStartTime;
    ##print("11 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'11'))

    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_rx_spead, sensors, f_host, sensor_manager,sensor_task)


@gen.coroutine
def _cb_feng_rx_reorder(sensors, f_host, sensor_manager,sensor_task):
    """
    F-engine RX reorder counters
    :param sensors: dictionary of sensors
    :return: true/false
    """
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])


    functionStartTime = time.time();
    ##print("12 on %s Started at %f" % (f_host.host ,functionStartTime))

    try:
        results = f_host.get_rx_reorder_status()
        device_status = True
        for key in [
            'timestep_err_cnt',
            'receive_err_cnt',
            'discard_cnt',
            'relock_err_cnt',
                'overflow_err_cnt']:
            sensor = sensors[key]
            sensor.set(value=results[key], errif='changed')
        for key in [
            'timestep_err_cnt',
            'receive_err_cnt',
            'relock_err_cnt',
                'overflow_err_cnt']:
            sensor = sensors[key]
            if sensor.status() == Corr2Sensor.ERROR:
                device_status = False

        if device_status:
            sensors['device_status'].set(
                status=Corr2Sensor.NOMINAL, value='ok')
        else:
            sensors['device_status'].set(status=Corr2Sensor.ERROR, value='fail')

    except Exception as e:
        sensor_manager.logger.error('Error updating rx_reorder sensors for {} - '
                     '{}'.format(f_host.host, e.message))
        set_failure()

    sensor_manager.logger.debug('_sensor_feng_rx_reorder ran on {}'.format(f_host.host))
    functionRunTime = time.time() - functionStartTime;
    ##print("12 on %s Ended End Time %f, Run Time %f" % (f_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,f_host.host,'12'))

    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_feng_rx_reorder, sensors, f_host, sensor_manager,sensor_task)


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
    #sensor_poll_time = sens_man.instrument.sensor_poll_time
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
    sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_rxtime','all boards'))
    ioloop.add_callback(_cb_feng_rxtime, sensor_ok, sensors_value, sens_man,sensor_task)
    import numpy
    min_pfb_pwr = -20*numpy.log10(2**(sens_man.instrument.fops.pfb_bits-4-1))
    # F-engine host sensors
    for _f in sens_man.instrument.fhosts:
        executor = host_executors[_f.host]
        fhost = host_offset_lookup[_f.host]
        # raw network comms - gbe counters must increment
        network_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.network.device-status'.format(fhost),
                'Overall network interface ok.', executor=executor),
            'tx_enabled': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}.network.tx-enabled'.format(fhost),
                'Network interface transmission enabled.', executor=executor),
            'tx_pps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.network.tx-pps'.format(fhost),
                'Network raw TX packets per second', executor=executor),
            'rx_pps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.network.rx-pps'.format(fhost),
                'Network raw RX packets per second', executor=executor),
            'tx_gbps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.network.tx-gbps'.format(fhost),
                'Network raw TX rate (gigabits per second)', executor=executor),
            'rx_gbps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.network.rx-gbps'.format(fhost),
                'Network raw RX rate (gibabits per second)', executor=executor),
            'tx_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.network.tx-err-cnt'.format(fhost),
                'TX network error count', executor=executor),
            'rx_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.network.rx-err-cnt'.format(fhost),
                'RX network error count (bad packets received)', executor=executor),
        }
        #sensor_task = sensor_scheduler.SensorTask('_cb_fhost_check_network on '+_f.host)
        #ioloop.add_callback(_cb_fhost_check_network, network_sensors, _f, sens_man,sensor_task)

        # SPEAD counters
        spead_rx_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.spead-rx.device-status'.format(fhost),
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
                Corr2Sensor.integer, '{}.spead-rx.pkt-time-err-cnt'.format(
                    fhost),
                'F-engine RX SPEAD packet timestamp has non-zero lsbs.',
                executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_rx_spead',_f.host))
        ioloop.add_callback(_cb_feng_rx_spead, spead_rx_sensors, _f, sens_man,sensor_task)


        # Rx reorder counters
        rx_reorder_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.network-reorder.device-status'.format(fhost),
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
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_rx_reorder',_f.host))
        ioloop.add_callback(_cb_feng_rx_reorder, rx_reorder_sensors, _f, sens_man,sensor_task)


        # CD functionality
        cd_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.cd.device-status'.format(fhost),
                'F-engine coarse delays ok.', executor=executor),
            'delay0_updating': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}.cd.delay0-updating'.format(fhost),
                'Delay updates are being received and applied for pol0.',
                executor=executor),
            'delay1_updating': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}.cd.delay1-updating'.format(fhost),
                'Delay updates are being received and applied for pol1.',
                executor=executor),
            'pol0_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.cd.err-cnt0'.format(fhost),
                'F-engine coarse delay error counter, pol0', executor=executor),
            'pol1_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.cd.err-cnt1'.format(fhost),
                'F-engine coarse delay error counter, pol1', executor=executor),
            'current_cd0': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.cd.current0'.format(fhost),
                'F-engine coarse delay current value, pol0, in samples.', executor=executor),
            'current_cd1': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.cd.current1'.format(fhost),
                'F-engine coarse delay current value, pol1, in samples.', executor=executor),
        }
        cd_sensors['delay0_updating'].tempstore = 0
        cd_sensors['delay1_updating'].tempstore = 0
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_delay',_f.host),minimum_time_between_calls_s=6)
        ioloop.add_callback(_cb_feng_delays, cd_sensors, _f, sens_man,sensor_task)


        # DIG ADC counters
        adc_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.dig.device-status'.format(fhost),
                'F-engine DIG ADC levels ok.', executor=executor),
            'p0_max': sens_man.do_sensor(
                Corr2Sensor.float, '{}.dig.p0-max'.format(fhost),
                'F-engine DIG ADC peak value, pol0, over ~70ms period. range -1 to +1.', executor=executor),
            'p1_max': sens_man.do_sensor(
                Corr2Sensor.float, '{}.dig.p1-max'.format(fhost),
                'F-engine DIG ADC peak value, pol1, over ~70ms period. range -1 to +1.', executor=executor),
            'p0_min': sens_man.do_sensor(
                Corr2Sensor.float, '{}.dig.p0-min'.format(fhost),
                'F-engine DIG ADC minimum value, pol0, over ~70ms period. range -1 to +1.', executor=executor),
            'p1_min': sens_man.do_sensor(
                Corr2Sensor.float, '{}.dig.p1-min'.format(fhost),
                'F-engine DIG ADC minimum value, pol1, over ~70ms period. range: -1 to +1.', executor=executor),
            'p0_pwr_dBFS': sens_man.do_sensor(
                Corr2Sensor.float, '{}.dig.p0-rms-dbfs'.format(fhost),
                'F-engine DIG ADC RMS average power, dBFS, pol0, over ~70ms period.', executor=executor),
            'p1_pwr_dBFS': sens_man.do_sensor(
                Corr2Sensor.float, '{}.dig.p1-rms-dbfs'.format(fhost),
                'F-engine DIG ADC RMS average power, dBFS, pol1, over ~70ms period.', executor=executor),
            'p0_dig_clip_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.dig.p0-dig-clip-cnt'.format(fhost),
                'F-engine DIG reported overrange counter.', executor=executor),
            'p1_dig_clip_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.dig.p1-dig-clip-cnt'.format(fhost),
                'F-engine DIG reported overrange counter.', executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_adcs',_f.host))
        ioloop.add_callback(_cb_feng_adcs, adc_sensors, _f, sens_man,sensor_task)


        # PFB counters
        pfb_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.pfb.device-status'.format(fhost),
                'F-engine PFB ok.', executor=executor),
            'pol0_or_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.pfb.or0-err-cnt'.format(fhost),
                'F-engine PFB over-range counter', executor=executor),
            'pol1_or_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.pfb.or1-err-cnt'.format(fhost),
                'F-engine PFB over-range counter', executor=executor),
            'pol0_pfb_out_dBFS': sens_man.do_sensor(
                Corr2Sensor.float, '{}.pfb.pol0-pfb-out-rms-pwr-dbfs'.format(fhost),
                'F-engine PFB output RMS power in dBFS, pol0.', executor=executor),
            'pol1_pfb_out_dBFS': sens_man.do_sensor(
                Corr2Sensor.float, '{}.pfb.pol1-pfb-out-rms-pwr-dbfs'.format(fhost),
                'F-engine PFB output RMS power in dBFS, pol1.', executor=executor),
            'sync_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.pfb.sync-cnt'.format(fhost),
                'F-engine PFB resync counter', executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_pfbs',_f.host))
        ioloop.add_callback(_cb_feng_pfbs, pfb_sensors, _f, min_pfb_pwr, sens_man,sensor_task)


        # CT functionality
        ct_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.ct.device-status'.format(fhost),
                'F-engine Corner-Turner ok.', executor=executor),
            'pol0_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.ct.err-cnt0'.format(fhost),
                'F-engine corner-turner error counter, pol0', executor=executor),
            'pol1_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.ct.err-cnt1'.format(fhost),
                'F-engine corner-turner error counter, pol1', executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_ct',_f.host))
        ioloop.add_callback(_cb_feng_ct, ct_sensors, _f, sens_man,sensor_task)


        # Pack block
        pack_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.spead-tx.device-status'.format(fhost),
                'F-engine packetiser (TX) is ok.', executor=executor),
            'err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.spead-tx.err-cnt'.format(fhost),
                'F-engine pack (TX) error count', executor=executor)
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_pack',_f.host))
        ioloop.add_callback(_cb_feng_pack, pack_sensors, _f, sens_man,sensor_task)


        
        #EQ quant/gain level sensors
        quant_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.quant.device-status'.format(fhost),
                'F-engine Quantiser ok.', executor=executor),
            'p0_quant_out_dBFS': sens_man.do_sensor(
                Corr2Sensor.float, '{}.quant.pol0-quant-out-rms-pwr-dbfs'.format(fhost),
                'F-engine Quantiser output RMS power in dBFS, pol0.', executor=executor),
            'p1_quant_out_dBFS': sens_man.do_sensor(
                Corr2Sensor.float, '{}.quant.pol1-quant-out-rms-pwr-dbfs'.format(fhost),
                'F-engine Quantiser output RMS power in dBFS, pol1.', executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_quant on',_f.host))
        ioloop.add_callback(_cb_feng_quant, quant_sensors, _f, sens_man,sensor_task)



        #Sync status
        sync_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.sync.device-status'.format(fhost),
                'F-engine synchroniser ok.', executor=executor),
            'cd_resync_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.sync.cd-resync-cnt'.format(fhost),
                'Count of F-engine coarse delay faults causing system resync.', executor=executor),
            'ct_resync_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.sync.ct-resync-cnt'.format(fhost),
                'Count of F-engine corner-turner faults causing system resync', executor=executor),
            'fault_clear_timeout_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.sync.fault-clear-timeout-cnt'.format(fhost),
                'Count of F-engine fault clear timeouts (faults have all cleared, but system hasnt resyncd).', executor=executor),
            'fault_present_timeout_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.sync.fault-present-timeout-cnt'.format(fhost),
                'Count of F-engine fault present timeout (a fault was continuously present for a long time)', executor=executor),
            'syncd': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}.sync.syncd'.format(fhost),
                'F-engine is synchronised to digitiser stream.', executor=executor),
            'time_diff_resync_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.sync.time-diff-resync-cnt'.format(fhost),
                'Count of F-engine timestamp faults causing host to resync.', executor=executor),
            'timestep_resync_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.sync.timestep-resync-cnt'.format(fhost),
                'Count of the number of times jumps in the digitiser streams timestamps were seen.', executor=executor),
            'timeout_resync_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.sync.timeout-resync-cnt'.format(fhost),
                'Count of the number of times the synchronisation process timed-out.', executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_feng_sync',_f.host))
        ioloop.add_callback(_cb_feng_sync, sync_sensors, _f, sens_man,sensor_task)



        # Overall LRU ok
        lru_sensor = sens_man.do_sensor(
            Corr2Sensor.device_status, '{}.device-status'.format(fhost),
            'F-engine %s LRU ok' % _f.host, executor=executor)
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_fhost_lru',_f.host))
        ioloop.add_callback(_cb_fhost_lru, sens_man, lru_sensor, _f,sensor_task)


        

# end
