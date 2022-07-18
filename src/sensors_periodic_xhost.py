import logging
import time
import tornado.gen as gen
import tornado

from IPython.core.debugger import Pdb

from tornado.ioloop import IOLoop

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid

import sensor_scheduler
from sensors import Corr2Sensor, boolean_sensor_do

host_offset_lookup = {}

@gen.coroutine
def _cb_xhost_lru(sensor_manager, sensor, sensors, x_host,sensor_task):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
   
    functionStartTime = time.time();
    #print("13 on %s Started at %f" % (x_host.host ,functionStartTime))

    try:
        h = host_offset_lookup[x_host.host]
        # Pdb().set_trace()
        status = Corr2Sensor.NOMINAL
        for xctr in range(x_host.x_per_fpga):
            pref = '{xhost}.xeng{xctr}'.format(xhost=h, xctr=xctr)
            eng_status = Corr2Sensor.NOMINAL
            if sensor_manager.sensor_get("{}.vacc.device-status".format(pref)).status() == Corr2Sensor.ERROR:
                status = Corr2Sensor.ERROR
                eng_status = Corr2Sensor.ERROR
            elif sensor_manager.sensor_get("{}.bram-reorder.device-status".format(pref)).status() == Corr2Sensor.ERROR:
                status = Corr2Sensor.ERROR
                eng_status = Corr2Sensor.ERROR
            elif sensor_manager.sensor_get("{}.spead-tx.device-status".format(pref)).status() == Corr2Sensor.ERROR:
                status = Corr2Sensor.ERROR
                eng_status = Corr2Sensor.ERROR
            if sensor_manager.sensor_get("{}.vacc.device-status".format(pref)).status() == Corr2Sensor.WARN:
                status = Corr2Sensor.WARN
                eng_status = Corr2Sensor.WARN
            elif sensor_manager.sensor_get("{}.bram-reorder.device-status".format(pref)).status() == Corr2Sensor.WARN:
                status = Corr2Sensor.WARN
                eng_status = Corr2Sensor.WARN
            elif sensor_manager.sensor_get("{}.spead-tx.device-status".format(pref)).status() == Corr2Sensor.WARN:
                status = Corr2Sensor.WARN
                eng_status = Corr2Sensor.WARN

            eng_sens_val = 'fail'
            if(eng_status == Corr2Sensor.NOMINAL):
                eng_sens_val = 'ok'
            elif(eng_status == Corr2Sensor.WARN):
                eng_sens_val = 'degraded'

            sensors[xctr].set(value=eng_sens_val, status=eng_status)

        if status != Corr2Sensor.ERROR:
            if sensor_manager.sensor_get("{}.network.device-status".format(h)).status() == Corr2Sensor.ERROR:
                status = Corr2Sensor.ERROR
            elif sensor_manager.sensor_get("{}.network-reorder.device-status".format(h)).status() == Corr2Sensor.ERROR:
                status = Corr2Sensor.ERROR
            elif sensor_manager.sensor_get("{}.spead-rx.device-status".format(h)).status() == Corr2Sensor.ERROR:
                status = Corr2Sensor.ERROR
            elif sensor_manager.sensor_get("{}.network.device-status".format(h)).status() == Corr2Sensor.WARN:
                status = Corr2Sensor.WARN
            elif sensor_manager.sensor_get("{}.network-reorder.device-status".format(h)).status() == Corr2Sensor.WARN:
                status = Corr2Sensor.WARN
            elif sensor_manager.sensor_get("{}.spead-rx.device-status".format(h)).status() == Corr2Sensor.WARN:
                status = Corr2Sensor.WARN

        sens_val = 'fail'
        if(status == Corr2Sensor.NOMINAL):
            sens_val = 'ok'
        elif(status == Corr2Sensor.WARN):
            sens_val = 'degraded'

        sensor.set(value=sens_val, status=status)

    except Exception as e:
        sensor_manager.logger.error(
            'Error updating LRU sensor for {} - {}'.format(
                x_host.host, e.message))
        for xctr in range(x_host.x_per_fpga):
            sensors[xctr].set(value='fail', status=Corr2Sensor.FAILURE)
        sensor.set(value='fail', status=Corr2Sensor.FAILURE)

    sensor_manager.logger.debug('_cb_xhost_lru ran')

    functionRunTime = time.time() - functionStartTime;
    #print("13 on %s Ended End Time %f, Run Time %f" % (x_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,x_host.host,'13'))
    IOLoop.current().call_at(
        sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime),
        _cb_xhost_lru,
        sensor_manager,
        sensor, sensors,
        x_host,sensor_task)


@gen.coroutine
def _cb_xeng_network(sensors, x_host, sensor_manager,sensor_task):
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();

    #print("14 on %s Started at %f" % (x_host.host ,functionStartTime))

    device_status = Corr2Sensor.NOMINAL
    try:
        result = x_host.gbes.gbe0.get_hw_gbe_stats()
        sensors['tx_err_cnt'].set(errif='changed', value=result['tx_over_err_cnt'])
        sensors['rx_err_cnt'].set(errif='changed', value=result['rx_bad_pkt_cnt'])
        sensors['tx_pps'].set(
            status=Corr2Sensor.NOMINAL,
            value=result['tx_pps'])
        sensors['tx_gbps'].set(
            status=Corr2Sensor.NOMINAL,
            value=result['tx_gbps'])

        if (result['rx_pps'] < 3500000) and (result['rx_pps'] > 2000000):
            sensors['rx_pps'].set(
                status=Corr2Sensor.NOMINAL,
                value=result['rx_pps'])
        else:
            sensors['rx_pps'].set(
                status=Corr2Sensor.WARN,
                value=result['rx_pps'])
            device_status = Corr2Sensor.WARN

        if (result['rx_gbps'] < 32) and (result['rx_gbps'] > 18):
            sensors['rx_gbps'].set(
                status=Corr2Sensor.NOMINAL,
                value=result['rx_gbps'])
        else:
            sensors['rx_gbps'].set(
                status=Corr2Sensor.WARN,
                value=result['rx_gbps'])
            device_status = Corr2Sensor.WARN

        if ((sensors['tx_err_cnt'].status() == Corr2Sensor.ERROR) or
                (sensors['rx_err_cnt'].status() == Corr2Sensor.ERROR)):
            device_status = Corr2Sensor.ERROR

        sens_val = 'fail'
        if(device_status == Corr2Sensor.NOMINAL):
            sens_val = 'ok'
        elif(device_status == Corr2Sensor.WARN):
            sens_val = 'degraded'

        sensors['device_status'].set(
            value=sens_val,
            status=device_status)

    except Exception as e:
        sensor_manager.logger.error(
            'Error updating gbe_stats for {} - {}'.format(
                x_host.host, e.message))
        set_failure()

    sensor_manager.logger.debug('_cb_xeng_network ran')

    functionRunTime = time.time() - functionStartTime;
    #print("14 on %s Ended End Time %f, Run Time %f" % (x_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,x_host.host,'14'))
    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_xeng_network, sensors, x_host, sensor_manager,sensor_task)


@gen.coroutine
def _cb_xeng_rx_spead(sensors, x_host, sensor_manager,sensor_task):
    def set_failure():
        for key, sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();
    #print("15 on %s Started at %f" % (x_host.host ,functionStartTime))
    # SPEAD RX
    status = Corr2Sensor.NOMINAL
    value = 'ok'
    try:
        results = x_host.get_unpack_status()
        sensors['err_cnt'].set(
            value=results['time_err_cnt'],
            errif='changed')
        sensors['cnt'].set(value=results['valid_pkt_cnt'], warnif='notchanged')
        if sensors['err_cnt'].status() == Corr2Sensor.ERROR:
            status = Corr2Sensor.ERROR
            value = 'fail'
        elif sensors['cnt'].status() == Corr2Sensor.WARN:
            status = Corr2Sensor.WARN
            value = 'degraded'
        sensors['device_status'].set(value=value, status=status)
    except Exception as e:
        sensor_manager.logger.error('Error updating SPEAD sensors for {} - '
                                    '{}'.format(x_host.host, e.message))
        set_failure()

    sensor_manager.logger.debug('_cb_xeng_rx_spead ran')

    functionRunTime = time.time() - functionStartTime;
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,x_host.host,'15'))
    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_xeng_rx_spead, sensors, x_host, sensor_manager,sensor_task)


@gen.coroutine
def _cb_xeng_hmc_reorder(sensors, x_host, sensor_manager,sensor_task):
    """
    X-engine HMC packet RX reorder counters
    :param sensors: a sensor for each xengine rx reorder
    :return:
    """
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time(); 
    #print("16 on %s Started at %f" % (x_host.host ,functionStartTime))       

    try:
        results = x_host.get_hmc_reorder_status()
        device_status = Corr2Sensor.NOMINAL
        sens_val = 'ok'
        sensors['miss_err_cnt'].set(value=results['miss_err_cnt'], warnif='changed')
        total_errors=results['dest_err_cnt'] + results['ts_err_cnt'] + results['hmc_err_cnt'] + results['lnk2_nrdy_err_cnt'] + results['lnk3_nrdy_err_cnt'] + results['mcnt_timeout_cnt']
        sensors['err_cnt'].set(value=total_errors, errif='changed')

        if sensors['err_cnt'].status() != Corr2Sensor.NOMINAL:
                device_status = Corr2Sensor.ERROR
                sens_val = 'fail'
        elif sensors['miss_err_cnt'].status() == Corr2Sensor.WARN:
            device_status = Corr2Sensor.WARN
            sens_val = 'degraded'
        else:
            device_status = Corr2Sensor.NOMINAL
            sens_val = 'ok'

        if device_status == Corr2Sensor.ERROR:
            x_host.logger.error("HMC Reorder error: %s"%str(results))
            x_host.logger.error("HMC Reorder HMC status: %s"%str(x_host.hmcs.hmc_pkt_reord_hmc.get_hmc_status()))

        sensors['device_status'].set(
            value=sens_val,
            status=device_status)

    except Exception as e:
        sensor_manager.logger.error('Error updating HMC RX reorder sensors for {} - '
                     '{}'.format(x_host.host, e.message))
        set_failure()

    sensor_manager.logger.debug('_cb_xeng_hmc_reorder ran')

    functionRunTime = time.time() - functionStartTime;
    #print("16 on %s Ended End Time %f, Run Time %f" % (x_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,x_host.host,'16'))
    IOLoop.current().call_at(
        sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime),
        _cb_xeng_hmc_reorder,
        sensors,
        x_host, sensor_manager,sensor_task)


@gen.coroutine
def _cb_xeng_missing_ants(sensors, sensor_top, x_host, sensor_manager,sensor_task):
    """
    X-engine missing packet counts per antenna.
    :param sensors:
    :return:
    """
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,
                       value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
        sensor_top.set(status=Corr2Sensor.FAILURE, value='fail')

    functionStartTime = time.time();
    #print("17 on %s Started at %f" % (x_host.host ,functionStartTime))

    status = Corr2Sensor.NOMINAL
    value = 'ok'
    try:
        results = x_host.get_missing_ant_counts()
        for n_ant, missing in enumerate(results):
            sensors[n_ant].set(value=missing, warnif='changed')
            if sensors[n_ant].status() == Corr2Sensor.WARN:
                status = Corr2Sensor.WARN
                value = 'degraded'
        sensor_top.set(status=status, value=value)
    except Exception as e:
        sensor_manager.logger.error('Error updating RX reorder sensors for {} - '
                     '{}'.format(x_host.host, e.message))
        set_failure()

    sensor_manager.logger.debug('_cb_xeng_missing_ants ran')

    functionRunTime = time.time() - functionStartTime;
    #print("17 on %s Ended End Time %f, Run Time %f" % (x_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,x_host.host,'17'))
    IOLoop.current().call_at(
        sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime),
        _cb_xeng_missing_ants,
        sensors,
        sensor_top,
        x_host, sensor_manager,sensor_task)


@gen.coroutine
def _cb_xeng_rx_reorder(sensors, x_host, sensor_manager,sensor_task):
    """
    X-engine BRAM RX reorder counters
    :param sensors: a sensor for each xengine rx reorder
    :return:
    """

    functionStartTime = time.time();
    #print("18 on %s Started at %f" % (x_host.host ,functionStartTime))

    try:
        rv = x_host.get_rx_reorder_status()
        is_ok=True
        for n_xengcore, sensordict in enumerate(sensors):
            sens_val = 'ok'
            device_status = Corr2Sensor.NOMINAL

            accumulated_errors = rv[n_xengcore]['timeout_err_cnt'] + rv[n_xengcore]['discard_err_cnt'] + rv[n_xengcore]['missed_err_cnt']
            sensordict['err_cnt'].set(value=accumulated_errors, errif='changed')

            if sensordict['err_cnt'].status() == Corr2Sensor.WARN:
                    device_status = Corr2Sensor.WARN
                    sens_val = 'degraded'
                    is_ok=False
            elif sensordict['err_cnt'].status() == Corr2Sensor.ERROR:
                    device_status = Corr2Sensor.ERROR
                    sens_val = 'fail'
                    is_ok=False

            sensordict['device_status'].set(
                value=sens_val, status=device_status)

        if not is_ok:
            x_host.logger.error("BRAM RX reorder error: %s"%(str(rv)))

    except Exception as e:
        sensor_manager.logger.error('Error updating RX reorder sensors for {} - '
                     '{}'.format(x_host.host, e.message))

    sensor_manager.logger.debug('_cb_xeng_rx_reorder ran')

    functionRunTime = time.time() - functionStartTime;
    #print("18 on %s Ended End Time %f, Run Time %f" % (x_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,x_host.host,'18'))
    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_xeng_rx_reorder, sensors, x_host, sensor_manager,sensor_task)


@gen.coroutine
def _cb_xeng_vacc(sensors_value, sensor_manager,sensor_task):
    """
    Sensor call back to check xeng vaccs.
    :param sensors_value: a dictionary of lists of dicts for all vaccs.
    :return:
    """
    def set_failure():
        sensors_value['synchronised'].set(
            status=Corr2Sensor.FAILURE, value=False)
        for _x, s in sensors_value.items():
            if _x == 'synchronised':
                s.set(value=False, status=Corr2Sensor.FAILURE)
            else:
                for n_xengcore, sensordict in enumerate(s):
                    sensordict['arm_cnt'].set(
                        status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['acc_cnt'].set(
                        status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['resync_cnt'].set(
                        status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['err_cnt'].set(
                        status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['ld_cnt'].set(
                        status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['timestamp'].set(
                        status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['device_status'].set(
                        status=Corr2Sensor.FAILURE, value='fail')

    functionStartTime = time.time();
    #print("19 on all at %f" % (functionStartTime))

    instrument = sensors_value['synchronised'].manager.instrument
    try:
        synced = instrument.xops.vaccs_synchronised()
        status = Corr2Sensor.NOMINAL if synced else Corr2Sensor.ERROR
        sensors_value['synchronised'].set(value=synced, status=status)
        
        rv = instrument.xops.get_vacc_status()
        for _x in rv:
            for xctr, sensordict in enumerate(sensors_value[_x]):
                sensordict['timestamp'].set(
                    value=rv[_x][xctr]['timestamp'])
                sensordict['acc_cnt'].set(value=rv[_x][xctr]['acc_cnt'])
                sensordict['resync_cnt'].set(value=rv[_x][xctr]['rst_cnt'])
                sensordict['err_cnt'].set(
                    value=rv[_x][xctr]['err_cnt'], errif='changed')
                sensordict['arm_cnt'].set(
                    value=rv[_x][xctr]['arm_cnt'], errif='changed')
                sensordict['ld_cnt'].set(
                    value=rv[_x][xctr]['ld_cnt'], errif='changed')
                if ((sensordict['err_cnt'].status() == Corr2Sensor.ERROR) or
                    (sensordict['resync_cnt'].status() == Corr2Sensor.ERROR) or
                    (sensordict['arm_cnt'].status() == Corr2Sensor.ERROR) or
                        (sensordict['ld_cnt'].status() == Corr2Sensor.ERROR)):
                    status = Corr2Sensor.ERROR
                    value = 'fail'
                    faulty_host_idx=instrument.xops.board_ids[_x]
                    faulty_host=instrument.xhosts[faulty_host_idx]
                    sensor_values_str_list = ['{} - {}'.format(name, sensor.value()) for name, sensor in 
                                                                sensors_value[_x][xctr].iteritems()]
                    sensor_values_str = ', '.join(sensor_values_str_list)
                    # faulty_host.logger.error('VACC%i error status: %s'%(xctr,str(sensors_value[_x][xctr])))
                    faulty_host.logger.error('VACC%i error status: %s'%(xctr, sensor_values_str))
                    if (xctr < 2):
                        faulty_host.logger.error('VACC HMC0 error status: %s'%(str(faulty_host.hmcs.sys0_vacc_hmc_vacc_hmc.get_hmc_status())))
                    else:
                        faulty_host.logger.error('VACC HMC1 error status: %s'%(str(faulty_host.hmcs.sys2_vacc_hmc_vacc_hmc.get_hmc_status())))
                else:
                    status = Corr2Sensor.NOMINAL
                    value = 'ok'
                sensordict['device_status'].set(value=value, status=status)
    except Exception as e:
        sensor_manager.logger.error('Error updating VACC sensors '
                     '- {}'.format(e.message))
        set_failure()

    sensor_manager.logger.debug('_cb_xeng_vacc ran')

    functionRunTime = time.time() - functionStartTime;
    #print("19 on %s Ended, Run Time %f" % (time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,'19'))
    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_xeng_vacc, sensors_value, sensor_manager,sensor_task)


@gen.coroutine
def _cb_xeng_pack(sensors, x_host, sensor_manager,sensor_task):
    """

    :param sensors: a sensor for each xengine pack block
    :param x_host: the host on which this is run
    :return:
    """
    def set_failure():
        for n_xengcore, sensordict in enumerate(sensors):
            for key, sensor in sensordict.iteritems():
                sensor.set(status=Corr2Sensor.FAILURE,
                           value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    functionStartTime = time.time();
    #print("20 on %s Started at %f" % (x_host.host ,functionStartTime))
    try:
        rv = x_host.get_pack_status()
        is_ok=True
        for n_xengcore, sensordict in enumerate(sensors):
            accum_errors = rv[n_xengcore]['align_err_cnt'] + rv[n_xengcore]['overflow_err_cnt'] 
            sensordict['err_cnt'].set(value=accum_errors, errif='changed')
            if sensordict['err_cnt'].status() == Corr2Sensor.ERROR:
                sensordict['device_status'].set(value='fail', status=Corr2Sensor.ERROR)
                is_ok=False
            else:
                sensordict['device_status'].set(value='ok', status=Corr2Sensor.NOMINAL)
        if not is_ok: 
            x_host.logger.error("SPEAD pack error: %s"%(str(rv)))

    except Exception as e:
        sensor_manager.logger.error('Error updating xeng pack sensors for {} - '
                     '{}'.format(x_host.host, e.message))
    sensor_manager.logger.debug('_cb_xeng_pack ran on {}'.format(x_host.host))

    sensor_manager.logger.debug('_cb_xeng_pack ran')

    functionRunTime = time.time() - functionStartTime;
    #print("20 on %s Ended End Time %f, Run Time %f" % (x_host.host,time.time(), functionRunTime))
    #print("%.4f %.4f %f %i %s %s" % (functionStartTime,sensor_task.last_runtime_utc,functionRunTime,sensor_task.flow_control_increments,x_host.host,'20'))
    IOLoop.current().call_at(sensor_task.getNextSensorCallTime(current_function_runtime=functionRunTime), _cb_xeng_pack, sensors, x_host, sensor_manager,sensor_task)


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
    #sensor_poll_time = sens_man.instrument.sensor_poll_time
    if len(host_offset_lookup) == 0:
        host_offset_lookup = host_offset_dict.copy()

    # NETWORK
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        pref = '{xhost}.network'.format(xhost=xhost)
        network_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{pref}.device-status'.format(pref=pref),
                'Overall status of this network interface.', executor=executor),
            'tx_pps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.tx-pps'.format(pref),
                'X-engine network raw TX packets per second', executor=executor),
            'rx_pps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.rx-pps'.format(pref),
                'X-engine network raw RX packets per second', executor=executor),
            'tx_gbps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.tx-gbps'.format(pref),
                'X-engine network raw TX rate (gigabits per second)', executor=executor),
            'rx_gbps': sens_man.do_sensor(
                Corr2Sensor.float, '{}.rx-gbps'.format(pref),
                'X-engine network raw RX rate (gibabits per second)', executor=executor),
            'tx_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.tx-err-cnt'.format(pref),
                'TX network error count', executor=executor),
            'rx_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.rx-err-cnt'.format(pref),
                'RX network error count (bad packets received)', executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_xeng_network',_x.host))
        ioloop.add_callback(_cb_xeng_network, network_sensors, _x, sens_man,sensor_task)

    # SPEAD counters

    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{}.spead-rx.device-status'.format(xhost),
                'X-engine RX SPEAD unpack device status',
                executor=executor),
            'cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.spead-rx.cnt'.format(xhost),
                'X-engine RX SPEAD packet counter',
                executor=executor),
            'err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.spead-rx.err-cnt'.format(xhost),
                'X-engine RX SPEAD packet error counter.',
                executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_xeng_rx_spead',_x.host))
        ioloop.add_callback(_cb_xeng_rx_spead, sensors, _x, sens_man,sensor_task)


    # HMC reorders
    for _x in sens_man.instrument.xhosts:
        xhost = host_offset_lookup[_x.host]
        pref = '{xhost}.network-reorder'.format(xhost=xhost)
        sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.device_status, '{pref}.device-status'.format(pref=pref),
                'Overall status of this HMC packet reorder.',
                executor=executor),
            'err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.err-cnt'.format(pref),
                'X-engine error count while reordering packets.', executor=executor),
            'miss_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.miss-err-cnt'.format(pref),
                'X-engine missing F-engine packet count; data filled with zeros.', executor=executor),
        }
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_xeng_hmc_reorder',_x.host))
        ioloop.add_callback(_cb_xeng_hmc_reorder, sensors, _x, sens_man,sensor_task)

    # missing antennas

    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        sensor_top = sens_man.do_sensor(
            Corr2Sensor.device_status, '{}.missing-pkts.device-status'.format(xhost),
            'Rolled-up missing packets sensor.', executor=executor)
        sensors = []
        for ant in range(_x.n_ants):
            sensors.append(sens_man.do_sensor(
                Corr2Sensor.integer, '{}.missing-pkts.fhost{:02}-cnt'.format(xhost, ant),
                'Missing packet count for antenna %i.' % ant, executor=executor))
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_xeng_missing_ants',_x.host))
        ioloop.add_callback(_cb_xeng_missing_ants, sensors, sensor_top, _x, sens_man,sensor_task)

    # BRAM reorders

    for _x in sens_man.instrument.xhosts:
        sensors = []
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}.xeng{xctr}.bram-reorder'.format(
                xhost=xhost, xctr=xctr)
            sensordict = {}
            sensordict['device_status'] = sens_man.do_sensor(
                Corr2Sensor.device_status, '{pref}.device-status'.format(pref=pref),
                'Overall status of this bram-reorder.')
            sensordict['err_cnt'] = sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.err-cnt'.format(pref=pref),
                'BRAM packet reorder errors.', executor=executor)
            sensors.append(sensordict)
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_xeng_rx_reorder',_x.host))
        ioloop.add_callback(_cb_xeng_rx_reorder, sensors, _x, sens_man,sensor_task)


    # VACC
    sensors_value = {}
    sensors_value['synchronised'] = sens_man.do_sensor(
        Corr2Sensor.boolean, 'xeng-vaccs-synchronised',
        'Are the output timestamps of the Xengine VACCs synchronised?',
        executor=general_executor)

    for _x in sens_man.instrument.xhosts:
        xhost = host_offset_lookup[_x.host]
        sensors_value[_x.host] = []
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}.xeng{xctr}.vacc'.format(xhost=xhost, xctr=xctr)
            sensordict = {}
            sensordict['device_status'] = sens_man.do_sensor(
                Corr2Sensor.device_status, '{pref}.device-status'.format(pref=pref),
                'Overall status of this VACC.')
            sensordict['arm_cnt'] = sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.arm-cnt'.format(pref=pref),
                'Number of times this VACC has armed.')
            sensordict['acc_cnt'] = sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.cnt'.format(pref=pref),
                'Number of accumulations this VACC has performed.')
            sensordict['resync_cnt'] = sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.resync-cnt'.format(pref=pref),
                'Number of times this VACC has reset itself.')
            sensordict['err_cnt'] = sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.err-cnt'.format(pref=pref),
                'Number of VACC errors.')
            sensordict['ld_cnt'] = sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.load-cnt'.format(pref=pref),
                'Number of times this VACC has been loaded.')
            sensordict['timestamp'] = sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.timestamp'.format(pref=pref),
                'Current VACC timestamp.')
            sensors_value[_x.host].append(sensordict)
    sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_xeng_vacc',_x.host))
    ioloop.add_callback(_cb_xeng_vacc, sensors_value, sens_man,sensor_task)

    # Xeng Packetiser block

    increment = 0;
    for _x in sens_man.instrument.xhosts:
        sensors = []
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}.xeng{xctr}.spead-tx'.format(xhost=xhost, xctr=xctr)
            sensordict = {
                'device_status': sens_man.do_sensor(
                    Corr2Sensor.device_status,
                    '{}.device-status'.format(pref),
                    'X-engine pack (TX) status',
                    executor=executor),
                'err_cnt': sens_man.do_sensor(
                    Corr2Sensor.integer,
                    '{}.err-cnt'.format(pref),
                    'X-engine pack (TX) error count',
                    executor=executor)
                }
            sensors.append(sensordict)
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_xeng_pack',_x.host))
        ioloop.add_callback(_cb_xeng_pack, sensors, _x, sens_man,sensor_task)


        # LRU ok
        sensor = sens_man.do_sensor(
            Corr2Sensor.device_status, '{}.device-status'.format(xhost),
            'X-engine %s LRU ok' % _x.host, executor=executor)
        sensors=[]
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}.xeng{xctr}'.format(xhost=xhost, xctr=xctr)
            xeng_sensor = sens_man.do_sensor(
                Corr2Sensor.device_status,
                '{}.device-status'.format(pref),
                'X-engine core status')
            sensors.append(xeng_sensor)
        sensor_task = sensor_scheduler.SensorTask('{0: <25} on {1: >15}'.format('_cb_xhost_lru',_x.host))
        ioloop.add_callback(_cb_xhost_lru, sens_man, sensor, sensors, _x,sensor_task)


# end
