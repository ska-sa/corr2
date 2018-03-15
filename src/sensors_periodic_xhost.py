import logging
import time
import tornado.gen as gen

from IPython.core.debugger import Pdb

from tornado.ioloop import IOLoop

from casperfpga.transport_katcp import KatcpRequestError, KatcpRequestFail, \
    KatcpRequestInvalid

from sensors import Corr2Sensor, boolean_sensor_do

LOGGER = logging.getLogger(__name__)

XHOST_REGS = ['status']
#XHOST_REGS.extend(['status%i' % ctr for ctr in range(4)])

host_offset_lookup = {}


@gen.coroutine
def _cb_xhost_lru(sensor_manager, sensor, x_host):
    """
    Sensor call back function for x-engine LRU
    :param sensor:
    :return:
    """
    try:
        h=host_offset_lookup[x_host.host]
        #Pdb().set_trace()
        status=Corr2Sensor.NOMINAL
        for xctr in range(x_host.x_per_fpga):
            pref = '{xhost}.xeng{xctr}'.format(xhost=h, xctr=xctr)
            eng_status=Corr2Sensor.NOMINAL
            if sensor_manager.sensor_get("{}.vacc.device-status".format(pref)).status()==Corr2Sensor.ERROR:
                status=Corr2Sensor.ERROR
                eng_status=Corr2Sensor.ERROR
            elif sensor_manager.sensor_get("{}.bram-reorder.device-status".format(pref)).status()==Corr2Sensor.ERROR:
                status=Corr2Sensor.ERROR
                eng_status=Corr2Sensor.ERROR
            sens_val=(eng_status==Corr2Sensor.NOMINAL)
            sensor_manager.sensor_get("{}.device-status".format(pref)).set(value=sens_val,status=eng_status)
            
        if sensor_manager.sensor_get("{}.network.device-status".format(h)).status()==Corr2Sensor.ERROR:
            status=Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.network-reorder.device-status".format(h)).status()==Corr2Sensor.ERROR:
            status=Corr2Sensor.ERROR
        elif sensor_manager.sensor_get("{}.network.device-status".format(h)).status()==Corr2Sensor.WARN:
            status=Corr2Sensor.WARN
        elif sensor_manager.sensor_get("{}.network-reorder.device-status".format(h)).status()==Corr2Sensor.WARN:
            status=Corr2Sensor.WARN
        sens_val=(status==Corr2Sensor.NOMINAL)
        sensor.set(value=sens_val,status=status)
    except Exception as e:
        LOGGER.error(
            'Error updating LRU sensor for {} - {}'.format(
                x_host.host, e.message))
        sensor.set(value=False,status=Corr2Sensor.FAILURE)

    LOGGER.debug('_cb_xhost_lru ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xhost_lru, sensor_manager, sensor, x_host)


@gen.coroutine
def _cb_xeng_network(sensors, x_host):
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])

    executor = sensors['tx_pps'].executor
    device_status=Corr2Sensor.NOMINAL
    try:
        result = yield executor.submit(x_host.gbes.gbe0.get_stats)
        sensors['tx_err_cnt'].set(errif='changed', value=result['tx_over'])
        sensors['rx_err_cnt'].set(errif='changed', value=result['rx_bad_pkts'])
        sensors['tx_pps'].set(status=Corr2Sensor.NOMINAL, value=result['tx_pps'])
        sensors['tx_gbps'].set(status=Corr2Sensor.NOMINAL, value=result['tx_gbps'])

        if (result['rx_pps']>900000) and (result['rx_pps']<3700000):
            sensors['rx_pps'].set(status=Corr2Sensor.NOMINAL, value=result['rx_pps'])
        else:
            sensors['rx_pps'].set(status=Corr2Sensor.WARN, value=result['rx_pps'])
            device_status=Corr2Sensor.WARN

        if (result['rx_gbps']>35) and (result['rx_gbps']<34):
            sensors['rx_gbps'].set(status=Corr2Sensor.NOMINAL, value=result['rx_gbps'])
        else:
            sensors['rx_gbps'].set(status=Corr2Sensor.WARN, value=result['rx_gbps'])
            device_status=Corr2Sensor.WARN

        if ((sensors['tx_err_cnt'].status()==Corr2Sensor.ERROR) or
            (sensors['rx_err_cnt'].status()==Corr2Sensor.ERROR)):
                device_status=Corr2Sensor.ERROR
        device_status_value=(device_status==Corr2Sensor.NOMINAL)
        sensors['device_status'].set(value=device_status_value,status=device_status)

    except Exception as e:
        LOGGER.error(
            'Error updating gbe_stats for {} - {}'.format(
                x_host.host, e.message))
        set_failure()
    LOGGER.debug('_cb_xhost_check_network ran')
    IOLoop.current().call_later(10, _cb_xeng_network, sensors, x_host)

@gen.coroutine
def _cb_xeng_rx_spead(sensors, x_host): 
    def set_failure():
        for key,sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
    # SPEAD RX
    executor = sensors['time_err_cnt'].executor
    status=Corr2Sensor.NOMINAL
    value=True
    try:
        results = yield executor.submit(x_host.get_unpack_status)
#        accum_errors=0
#        for key in ['header_err_cnt','magic_err_cnt','pad_err_cnt','pkt_len_err_cnt','time_err_cnt']:
#            accum_errors+=results[key]
        sensors['time_err_cnt'].set(value=results['time_err_cnt'],errif='changed')
        sensors['cnt'].set(value=results['valid_pkt_cnt'],warnif='notchanged')
        if sensors['time_err_cnt'].status()==Corr2Sensor.ERROR:
            status=Corr2Sensor.ERROR
            value=False
        elif sensors['cnt'].status()==Corr2Sensor.WARN:
            status=Corr2Sensor.WARN
            value=False
        sensors['device_status'].set(value=value,status=status)
    except Exception as e:
        LOGGER.error('Error updating SPEAD sensors for {} - '
                     '{}'.format(x_host.host, e.message))
        set_failure()
    LOGGER.debug('_cb_xeng_rx_spead ran')
    IOLoop.current().call_later(10, _cb_xeng_rx_spead, sensors, x_host)

@gen.coroutine
def _cb_xeng_hmc_reorder(sensors, x_host):
    """
    X-engine HMC packet RX reorder counters
    :param sensors: a sensor for each xengine rx reorder
    :return:
    """
    def set_failure():
        for sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
    executor = sensors['post_ok'].executor
    try:
        results = yield executor.submit(x_host.get_hmc_reorder_status)
        device_status=Corr2Sensor.NOMINAL
        for key in ['miss_err_cnt']:
            sensors[key].set(value=results[key],warnif='changed')
        for key in ['dest_err_cnt','ts_err_cnt']:
            sensors[key].set(value=results[key],errif='changed')
        if results['post_ok']:
            sensors['post_ok'].set(value=True,status=Corr2Sensor.NOMINAL)
        else:
            sensors['post_ok'].set(value=False,status=Corr2Sensor.ERROR)
            device_status=Corr2Sensor.ERROR
        overflows=results['lnk2_nrdy_err_cnt']+results['lnk3_nrdy_err_cnt']
        sensors['hmc_overflow_err_cnt'].set(value=overflows,errif='changed')
        errs=results['err_cnt_link3']+results['err_cnt_link2']
        sensors['hmc_err_cnt'].set(value=errs,errif='changed')

        for key in ['miss_err_cnt']:
            if sensors[key].status()==Corr2Sensor.WARN:
                device_status=Corr2Sensor.WARN
        for key in ['dest_err_cnt','ts_err_cnt','post_ok','hmc_overflow_err_cnt','hmc_err_cnt']:
            if sensors[key].status()==Corr2Sensor.ERROR:
                device_status=Corr2Sensor.ERROR
        device_sensor_value=(device_status==Corr2Sensor.NOMINAL)
        sensors['device_status'].set(value=device_sensor_value,status=device_status)

    except Exception as e:
        LOGGER.error('Error updating HMC RX reorder sensors for {} - '
                     '{}'.format(x_host.host, e.message))
        set_failure() 
    LOGGER.debug('_cb_xhost_hmc_reorder ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xeng_hmc_reorder, sensors, x_host)

@gen.coroutine
def _cb_xeng_missing_ants(sensors, sensor_top, x_host):
    """
    X-engine missing packet counts per antenna.
    :param sensors:
    :return:
    """
    def set_failure():
        for sensor in sensors.iteritems():
            sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
        sensor_top.set(status=Corr2Sensor.FAILURE,value=False)
    executor = sensor_top.executor
    status=Corr2Sensor.NOMINAL
    value=True
    try:
        results = yield executor.submit(x_host.get_missing_ant_counts)
        for n_ant,missing in enumerate(results):
            sensors[n_ant].set(value=missing,warnif='changed')
            if sensors[n_ant].status()==Corr2Sensor.WARN:
                status=Corr2Sensor.WARN
                value=False
        sensor_top.set(status=status,value=value)
    except Exception as e:
        LOGGER.error('Error updating RX reorder sensors for {} - '
                     '{}'.format(x_host.host, e.message))
        set_failure()
    LOGGER.debug('_cb_xeng_missing_ants ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xeng_missing_ants, sensors, sensor_top, x_host)

@gen.coroutine
def _cb_xeng_rx_reorder(sensors, x_host):
    """
    X-engine BRAM RX reorder counters
    :param sensors: a sensor for each xengine rx reorder
    :return:
    """
    def set_failure():
        for n_xengcore,sensordict in enumerate(sensors):
            for key,sensor in sensordict.iteritems():
                sensor.set(status=Corr2Sensor.FAILURE,value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
    executor = sensors[0]['discard_err_cnt'].executor
    try:
        rv = yield executor.submit(x_host.get_rx_reorder_status)
        device_status=Corr2Sensor.NOMINAL
        for n_xengcore,sensordict in enumerate(sensors):
            sensordict['timeout_err_cnt'].set(value=rv[n_xengcore]['timeout_err_cnt'],errif='changed')
            sensordict['discard_err_cnt'].set(value=rv[n_xengcore]['discard_err_cnt'],warnif='changed')
            sensordict['missed_err_cnt'].set(value=rv[n_xengcore]['missed_err_cnt'],warnif='changed')

            for key in ['discard_err_cnt','missed_err_cnt']:
                if sensordict[key].status()==Corr2Sensor.WARN:
                    device_status=Corr2Sensor.WARN
            for key in ['timeout_err_cnt']:
                if sensordict[key].status()==Corr2Sensor.ERROR:
                    device_status=Corr2Sensor.ERROR
            device_status_value=(device_status==Corr2Sensor.NOMINAL)
            sensordict['device_status'].set(value=device_status_value,status=device_status)

    except Exception as e:
        LOGGER.error('Error updating RX reorder sensors for {} - '
                     '{}'.format(x_host.host, e.message))
    LOGGER.debug('_cb_xeng_rx_reorder ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xeng_rx_reorder, sensors, x_host)

@gen.coroutine
def _cb_xeng_vacc(sensors_value):
    """
    Sensor call back to check xeng vaccs.
    :param sensors_value: a dictionary of lists of dicts for all vaccs.
    :return:
    """
    def set_failure():
        sensors_value['synchronised'].set(status=Corr2Sensor.FAILURE, value=False)
        for _x,s in sensors_value.items():
            if _x == 'synchronised' :
                s.set(value=False,status=Corr2Sensor.FAILURE)
            else:
                for n_xengcore,sensordict in enumerate(s):
                    sensordict['arm_cnt'].set(status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['acc_cnt'].set(status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['err_cnt'].set(status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['ld_cnt'].set(status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['timestamp'].set(status=Corr2Sensor.FAILURE, value=-1)
                    sensordict['device_status'].set(status=Corr2Sensor.FAILURE, value=False)
    executor = sensors_value['synchronised'].executor
    instrument = sensors_value['synchronised'].manager.instrument
    try:
        rv = yield executor.submit(instrument.xops.get_vacc_status)
        for _x in rv:
            if _x == 'synchronised':
                status=Corr2Sensor.NOMINAL if rv['synchronised'] else Corr2Sensor.ERROR
                sensors_value['synchronised'].set(value=rv['synchronised'],status=status)
            else:
                for xctr,sensordict in enumerate(sensors_value[_x]):
                    sensordict['timestamp'].set(value=rv[_x][xctr]['timestamp'])
                    sensordict['acc_cnt'].set(value=rv[_x][xctr]['acc_cnt'])
                    sensordict['err_cnt'].set(value=rv[_x][xctr]['err_cnt'],errif='changed')
                    sensordict['arm_cnt'].set(value=rv[_x][xctr]['arm_cnt'],errif='changed')
                    sensordict['ld_cnt'].set(value=rv[_x][xctr]['ld_cnt'],errif='changed')
                    if ((sensordict['err_cnt'].status()==Corr2Sensor.ERROR) or
                        (sensordict['arm_cnt'].status()==Corr2Sensor.ERROR) or
                        (sensordict['ld_cnt'].status()==Corr2Sensor.ERROR)):
                        status = Corr2Sensor.ERROR
                        value=False
                    else:
                        status = Corr2Sensor.NOMINAL
                        value=True
                    sensordict['device_status'].set(value=value,status=status)
    except Exception as e:
        LOGGER.error('Error updating VACC sensors '
                     '- {}'.format(e.message))
        set_failure()
    LOGGER.debug('_cb_xeng_vacc ran')
    IOLoop.current().call_later(10,_cb_xeng_vacc, sensors_value) 

@gen.coroutine
def _cb_xeng_pack(sensors, x_host):
    """

    :param sensors: a sensor for each xengine pack block
    :param x_host: the host on which this is run
    :return:
    """
    def set_failure():
        for n_xengcore,sensordict in enumerate(sensors):
            for key,sensor in sensordict.iteritems():
                sensor.set(status=Corr2Sensor.FAILURE,
                value=Corr2Sensor.SENSOR_TYPES[Corr2Sensor.SENSOR_TYPE_LOOKUP[sensor.type]][1])
    value=True
    status=Corr2Sensor.NOMINAL
    try:
        executor = sensors[0]['align_err_cnt'].executor
        rv = yield executor.submit(x_host.get_pack_status)
        for n_xengcore,sensordict in enumerate(sensors):
            for key in ['align_err_cnt','overflow_err_cnt']:
                sensordict[key].set(value=rv[n_xengcore][key],errif='changed')
                if sensordict[key].status()==Corr2Sensor.ERROR:
                    status=Corr2Sensor.ERROR
                    value=False
                sensordict['device_status'].set(value=value,status=status)
    except Exception as e:
        LOGGER.error('Error updating xeng pack sensors for {} - '
                     '{}'.format(x_host.host, e.message))
    LOGGER.debug('_cb_xeng_pack ran on {}'.format(x_host.host))
    IOLoop.current().call_later(10, _cb_xeng_pack, sensors, x_host)


@gen.coroutine
def _cb_beng_pack(sensors, x_host):
    """

    :param sensors: a sensor for each xengine pack block
    :param x_host: the host on which this is run
    :return:
    """
    executor = sensors[0][0].executor
    try:
        print 'xeng pack not yet implemented'
        #results = yield executor.submit(x_host.check_beng)
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

#    # B-engine host sensors
#    for _x in sens_man.instrument.xhosts:
#        executor = host_executors[_x.host]
#        xhost = host_offset_lookup[_x.host]
#        bhost = xhost.replace('xhost', 'bhost')
#
#        # LRU ok
#        sensor = sens_man.do_sensor(
#            Corr2Sensor.boolean, '{}-lru-ok'.format(bhost),
#            'B-engine %s LRU ok' % _x.host, executor=executor)
#        ioloop.add_callback(_cb_beng_lru, sensor, _x)
#
#    #BENG packetiser
#    for _x in sens_man.instrument.xhosts:
#        executor = host_executors[_x.host]
#        xhost = host_offset_lookup[_x.host]
#        # beng
#        sensors = []
#        for xctr in range(_x.x_per_fpga):
#            bsensors = []
#            for pctr in range(2):
#                sensor_name = '{host}-beng{x}-{p}-ok'.format(
#                    host=xhost, x=xctr, p=pctr)
#                sensor_descrip = '{host} b-engine{x}-{p} ok'.format(
#                    host=xhost, x=xctr, p=pctr)
#                sensor = sens_man.do_sensor(Corr2Sensor.boolean, sensor_name,
#                                            sensor_descrip, executor=executor)
#                bsensors.append(sensor)
#            sensors.append(bsensors)
#        ioloop.add_callback(_cb_beng_pack, sensors, _x)

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

    # NETWORK
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        pref = '{xhost}.network'.format(xhost=xhost)
        network_sensors = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.boolean, '{pref}.device-status'.format(pref=pref),
                'Overall status of this HMC-reorder.',executor=executor),
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
        ioloop.add_callback(_cb_xeng_network, network_sensors, _x)

    # SPEAD counters
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        sensors = {
        'device_status': sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.spead-rx.device-status'.format(xhost),
            'X-engine RX SPEAD unpack device status',
            executor=executor),
#            'err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-timestamp-err-cnt'.format(xhost),
#            'X-engine RX SPEAD packet errors',
#            executor=executor),
        'cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.spead-rx.cnt'.format(xhost),
            'X-engine RX SPEAD packet counter',
            executor=executor),
#            'header_err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-header-err-cnt'.format(xhost),
#            'X-engine RX SPEAD packet unpack header errors',
#            executor=executor),
#            'magic_err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-magic-err-cnt'.format(xhost),
#            'X-engine RX SPEAD magic field errors',
#            executor=executor),
#            'pad_err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-pad-err-cnt'.format(xhost),
#            'X-engine RX SPEAD padding errors',
#            executor=executor),
#            'pkt_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-pkt-cnt'.format(xhost),
#            'X-engine RX SPEAD packet count',
#            executor=executor),
#            'pkt_len_err_cnt': sens_man.do_sensor(
#            Corr2Sensor.integer, '{}-spead-pkt-len-err-cnt'.format(xhost),
#            'X-engine RX SPEAD packet length errors',
#            executor=executor),
        'time_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.spead-rx.time-err-cnt'.format(xhost),
            'X-engine RX SPEAD packet timestamp has non-zero lsbs.',
            executor=executor),
        }
        ioloop.add_callback(_cb_xeng_rx_spead, sensors, _x)

    #HMC reorders
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        pref = '{xhost}.network-reorder'.format(xhost=xhost)
        sensors = {
        'device_status': sens_man.do_sensor(
            Corr2Sensor.boolean, '{pref}.device-status'.format(pref=pref),
            'Overall status of this HMC-reorder.',
            executor=executor),
        'dest_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.dest-err-cnt'.format(pref),
            'X-engine is receiving packets for a different X-engine.',
            executor=executor),
        'post_ok': sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.hmc-post'.format(pref),
            'X-engine error reordering packets: HMC POST status.',executor=executor),
        'ts_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.timestep-err-cnt'.format(pref),
            'X-engine RX timestamps not incrementing correctly.',executor=executor),
        'miss_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.miss-err-cnt'.format(pref),
            'X-engine error reordering packets: missing packet.',executor=executor),
        'hmc_overflow_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.hmc-overflow-err-cnt'.format(pref),
            'X-engine error reordering packets: HMC link not ready.',
            executor=executor),
        'hmc_err_cnt': sens_man.do_sensor(
            Corr2Sensor.integer, '{}.hmc-err-cnt'.format(pref),
            'HMC hardware memory error counters.',executor=executor),
        }
        ioloop.add_callback(_cb_xeng_hmc_reorder, sensors, _x)

    #missing antennas
    for _x in sens_man.instrument.xhosts:
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        sensor_top=sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.missing-pkts.device-status'.format(xhost),
            'Rolled-up missing packets sensor.',executor=executor)
        sensors=[]
        for ant in range(_x.n_ants):
            sensors.append(sens_man.do_sensor(
            Corr2Sensor.integer, '{}.missing-pkts.fhost{:02}-cnt'.format(xhost,ant),
            'Missing packet count for antenna %i.'%ant,executor=executor))
        ioloop.add_callback(_cb_xeng_missing_ants, sensors, sensor_top, _x)
            
    #BRAM reorders
    for _x in sens_man.instrument.xhosts:
        sensors=[]
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}.xeng{xctr}.bram-reorder'.format(xhost=xhost, xctr=xctr)
            sensordict={}
            sensordict['device_status']=sens_man.do_sensor(
                Corr2Sensor.boolean, '{pref}.device-status'.format(pref=pref),
                'Overall status of this bram-reorder.')
            sensordict['discard_err_cnt']=sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.discard-err-cnt'.format(pref=pref),
                'BRAM Reorder discard errors.',executor=executor)
            sensordict['timeout_err_cnt']=sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.timeout-err-cnt'.format(pref=pref),
                'BRAM Reorder block timed out waiting for data error counter.',executor=executor)
            sensordict['missed_err_cnt']=sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.missing-err-cnt'.format(pref=pref),
                'BRAM Reorder block missing data words error counter.',executor=executor)
            sensors.append(sensordict)
        ioloop.add_callback(_cb_xeng_rx_reorder, sensors, _x)
        

#        # VACC accumulations per second
#        for xctr in range(_x.x_per_fpga):
#            pref = '{xhost}-xeng{xctr}-'.format(xhost=xhost, xctr=xctr)
#            sensor = sens_man.do_sensor(
#                Corr2Sensor.float, '{pref}accs-per-sec'.format(pref=pref),
#                'Number of accumulations per second for this X-engine on '
#                'this host.', executor=executor)
#        ioloop.add_callback(_cb_xeng_vacc_accs_ps, _x, executor, sens_man)


    # VACC
    sensors_value = {}
    sensors_value['synchronised'] = sens_man.do_sensor(
        Corr2Sensor.boolean, 'xeng-vaccs-synchronised',
        'Are the output timestamps of the Xengine VACCs synchronised?',
        executor=general_executor)

    for _x in sens_man.instrument.xhosts:
        xhost = host_offset_lookup[_x.host]
        sensors_value[_x.host] =[]
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}.xeng{xctr}.vacc'.format(xhost=xhost, xctr=xctr)
            sensordict={}
            sensordict['device_status']=sens_man.do_sensor(
                Corr2Sensor.boolean, '{pref}.device-status'.format(pref=pref),
                'Overall status of this VACC.')
            sensordict['arm_cnt']=sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.arm-cnt'.format(pref=pref),
                'Number of times this VACC has armed.')
            sensordict['acc_cnt']=sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.cnt'.format(pref=pref),
                'Number of accumulations this VACC has performed.')
            sensordict['err_cnt']=sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.err-cnt'.format(pref=pref),
                'Number of VACC errors.')
            sensordict['ld_cnt']=sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.load-cnt'.format(pref=pref),
                'Number of times this VACC has been loaded.')
            sensordict['timestamp']=sens_man.do_sensor(
                Corr2Sensor.integer, '{pref}.timestamp'.format(pref=pref),
                'Current VACC timestamp.')
            sensors_value[_x.host].append(sensordict)
    ioloop.add_callback(_cb_xeng_vacc, sensors_value)
    

    #Xeng Packetiser block
    for _x in sens_man.instrument.xhosts:
        sensors=[]
        executor = host_executors[_x.host]
        xhost = host_offset_lookup[_x.host]
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}.xeng{xctr}.spead-tx'.format(xhost=xhost, xctr=xctr)
            sensordict = {
            'device_status': sens_man.do_sensor(
                Corr2Sensor.boolean, '{}.device-status'.format(pref),
                'X-engine pack (TX) status', executor=executor),
            'align_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.align-err-cnt'.format(pref),
                'X-engine pack (TX) misalignment error count', executor=executor),
            'overflow_err_cnt': sens_man.do_sensor(
                Corr2Sensor.integer, '{}.overflow-err-cnt'.format(pref),
                'X-engine pack (TX) fifo overflow error count', executor=executor)
            }        
            sensors.append(sensordict)
        ioloop.add_callback(_cb_xeng_pack, sensors, _x)
        

        # LRU ok
        sensor = sens_man.do_sensor(
            Corr2Sensor.boolean, '{}.device-status'.format(xhost),
            'X-engine %s LRU ok' % _x.host, executor=executor)
        for xctr in range(_x.x_per_fpga):
            pref = '{xhost}.xeng{xctr}'.format(xhost=xhost, xctr=xctr)
            sens_man.do_sensor(Corr2Sensor.boolean, 
                '{}.device-status'.format(pref),'X-engine core status')
        ioloop.add_callback(_cb_xhost_lru, sens_man, sensor, _x)

# end
