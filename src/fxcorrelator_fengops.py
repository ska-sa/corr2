import numpy
import spead64_48 as spead
from casperfpga import utils as fpgautils
from casperfpga.tengbe import Mac
# from casperfpga.tengbe import IpAddress

from data_source import DataSource
import utils

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function

def feng_initialise(corr):
    """
    Set up f-engines on this device.
    :return:
    """
    # set eq and shift
    feng_eq_write_all(corr)
    feng_set_fft_shift_all(corr)

    # set up the fpga comms
    THREADED_FPGA_OP(corr.fhosts, timeout=10,
                     target_function=(lambda fpga_: fpga_.registers.control.write(gbe_txen=False),))
    THREADED_FPGA_OP(corr.fhosts, timeout=10,
                     target_function=(lambda fpga_: fpga_.registers.control.write(gbe_rst=True),))
    feng_clear_status_all(corr)

    # where does the f-engine data go?
    corr.fengine_output = DataSource.from_mcast_string(
        corr.configd['fengine']['destination_mcast_ips'])
    corr.fengine_output.name = 'fengine_destination'
    fdest_ip = int(corr.fengine_output.ip_address)
    THREADED_FPGA_OP(corr.fhosts, timeout=10, target_function=(
        lambda fpga_: fpga_.registers.iptx_base.write_int(fdest_ip),) )

    # set up the cores
    feng_port = int(corr.configd['fengine']['10gbe_port'])
    start_mac = int(Mac(corr.configd['fengine']['10gbe_start_mac']))
    # Set up shared board info
    boards_info = {}
    board_id = 0
    for f in corr.fhosts:
        macs = []
        # ips = [] #  not used
        for gbe in f.tengbes:
            this_mac = start_mac + gbe
            macs.append(this_mac)
            boards_info[f.host] = board_id, macs
        board_id += 1

    def setup_gbes(f):
        board_id, macs = boards_info[f.host]
        f.registers.tx_metadata.write(
            board_id=board_id, porttx=corr.fengine_output.port)
        for gbe, this_mac in zip(f.tengbes, macs):
            gbe.setup(mac=this_mac, ipaddress='0.0.0.0', port=feng_port)
            corr.logger.info(
                'fhost(%s) gbe(%s) MAC(%s) port(%i) board(%i) txIPbase(%s) txPort(%i)' %
                (f.host, gbe.name, str(Mac(this_mac)), feng_port, board_id,
                 corr.fengine_output.ip_address, corr.fengine_output.port))
            #gbe.tap_start(restart=True)
            gbe.dhcp_start()
    THREADED_FPGA_OP(corr.fhosts, timeout=10, target_function=(setup_gbes,))

    # release from reset
    THREADED_FPGA_OP(corr.fhosts, timeout=5, target_function=(
        lambda fpga_: fpga_.registers.control.write(gbe_rst=False),) )

def feng_check_rx(corr, max_waittime=30):
    """
    Check that the f-engines are receiving data correctly
    :param max_waittime:
    :return:
    """
    corr.logger.info('Checking F hosts are receiving data...')
    results = THREADED_FPGA_FUNC(corr.fhosts, timeout=max_waittime+1,
                                 target_function=('check_rx', (max_waittime,),))
    all_okay = True
    for _v in results.values():
        all_okay = all_okay and _v
    if not all_okay:
        corr.logger.error('\tERROR in F-engine rx data.')
    corr.logger.info('\tdone.')
    return all_okay

def feng_set_delay(corr, target_name, delay=0, delay_rate=0, fringe_phase=0,
                   fringe_rate=0, ld_time=-1, ld_check=True, extra_wait_time=0):
    """
    :param target_name:
    :return:
    """
    targetsrc = None
    for src in corr.fengine_sources:
        if src.name == target_name:
            targetsrc = src
            break
    if targetsrc is None:
        raise RuntimeError('Could not find target %s' % target_name)

    pol_id = targetsrc.source_number % 2
    targetsrc.fr_delay_set(pol_id, delay, delay_rate, fringe_phase,
                           fringe_rate, ld_time, ld_check, extra_wait_time)

def feng_check_tx(corr):
    """
    Check that the f-engines are sending data correctly
    :return:
    """
    corr.logger.info('Checking F hosts are transmitting data...')
    results = THREADED_FPGA_FUNC(corr.fhosts, timeout=5,
                                 target_function='check_tx_raw')
    all_okay = True
    for _v in results.values():
        all_okay = all_okay and _v
    if not all_okay:
        corr.logger.error('\tERROR in F-engine tx data.')
    corr.logger.info('\tdone.')
    return all_okay

def feng_eq_get(corr, source_name=None):
    """
    Return the EQ arrays in a dictionary, arranged by source name.
    :return:
    """
    eq_table = {}
    for fhost in corr.fhosts:
        eq_table.update(fhost.eqs)
        if source_name is not None and source_name in eq_table.keys():
            return {source_name: eq_table[source_name]}
    return eq_table

def feng_eq_set(corr, write=True, source_name=None, new_eq=None):
    """
    Set the EQ for a specific source
    :param write: should the value be written to BRAM on the device?
    :param source_name: the source name
    :param new_eq: an eq list or value or poly
    :return:
    """
    if new_eq is None:
        raise ValueError('New EQ of nothing makes no sense.')
    # if no source is given, apply the new eq to all sources
    if source_name is None:
        corr.logger.info('Setting EQ on all sources to new given EQ.')
        for fhost in corr.fhosts:
            for src_nm in fhost.eqs.keys():
                feng_eq_set(corr, write=False, source_name=src_nm, new_eq=new_eq)
        if write:
            feng_eq_write_all(corr)
    else:
        for fhost in corr.fhosts:
            if source_name in fhost.eqs.keys():
                old_eq = fhost.eqs[source_name]['eq'][:]
                try:
                    neweq = utils.process_new_eq(new_eq)
                    fhost.eqs[source_name]['eq'] = neweq
                    corr.logger.info('Updated EQ value for source %s: %s...' %
                                     (source_name, neweq[0:min(10, len(neweq))]))
                    if write:
                        fhost.write_eq(eq_name=source_name)
                except Exception as e:
                    fhost.eqs[source_name]['eq'] = old_eq[:]
                    corr.logger.error('New EQ error - REVERTED to old value! - %s' % e.message)
                    raise ValueError('New EQ error - REVERTED to old value! - %s' % e.message)
                return
        raise ValueError('Unknown source name %s' % source_name)

def feng_eq_write_all(corr, new_eq_dict=None):
    """
    Set the EQ gain for given sources and write the changes to memory.
    :param new_eq_dict: a dictionary of new eq values to store
    :return:
    """
    if new_eq_dict is not None:
        corr.logger.info('Updating some EQ values before writing.')
        for src, new_eq in new_eq_dict:
            feng_eq_set(corr, write=False, source_name=src, new_eq=new_eq)
    corr.logger.info('Writing EQ on all fhosts based on stored per-source EQ values...')
    THREADED_FPGA_FUNC(corr.fhosts, timeout=10, target_function='write_eq_all')
    if corr.spead_meta_ig is not None:
        feng_eq_update_metadata(corr)
        corr.spead_tx.send_heap(corr.spead_meta_ig.get_heap())
    corr.logger.info('done.')

def feng_eq_update_metadata(corr):
    """
    Update the EQ metadata for this correlator.
    :return:
    """
    all_eqs = feng_eq_get(corr)
    for source_ctr, source in enumerate(corr.fengine_sources):
        eqlen = len(all_eqs[source.name]['eq'])
        corr.spead_meta_ig.add_item(name='eq_coef_%s' % source.name,
                                    id=0x1400 + source_ctr,
                                    description='The unitless per-channel digital scaling factors implemented '
                                                'prior to requantisation, post-FFT, for input %s. '
                                                'Complex number real,imag 32 bit integers.' %
                                                source.name,
                                    shape=[eqlen, 2],
                                    fmt=spead.mkfmt(('u', 32)),
                                    init_val=[[numpy.real(eq_coeff), numpy.imag(eq_coeff)]
                                              for eq_coeff in all_eqs[source.name]['eq']])

def feng_set_fft_shift_all(corr, shift_value=None):
    """
    Set the FFT shift on all boards.
    :param shift_value:
    :return:
    """
    if shift_value is None:
        shift_value = int(corr.configd['fengine']['fft_shift'])
    if shift_value < 0:
        raise RuntimeError('Shift value cannot be less than zero')
    corr.logger.info('Setting FFT shift to %i on all f-engine boards...' % shift_value)
    THREADED_FPGA_FUNC(corr.fhosts, timeout=10,
                       target_function=('set_fft_shift', (shift_value,),))
    corr.logger.info('done.')
    if corr.spead_meta_ig is not None:
        corr.spead_meta_ig['fft_shift'] = int(corr.configd['fengine']['fft_shift'])
        corr.spead_tx.send_heap(corr.spead_meta_ig.get_heap())
    return shift_value

def feng_get_fft_shift_all(corr):
    """
    Get the FFT shift value on all boards.
    :return:
    """
    # get the fft shift values
    return THREADED_FPGA_FUNC(corr.fhosts, timeout=10, target_function='get_fft_shift')

def feng_clear_status_all(corr):
    """
    Clear the various status registers and counters on all the fengines
    :return:
    """
    THREADED_FPGA_FUNC(corr.fhosts, timeout=10, target_function='clear_status')

def feng_subscribe_to_multicast(corr):
    """
    Subscribe all f-engine data sources to their multicast data
    :return:
    """
    corr.logger.info('Subscribing f-engine datasources...')
    for fhost in corr.fhosts:
        corr.logger.info('\t%s:' % fhost.host)
        gbe_ctr = 0
        for source in fhost.data_sources:
            if not source.is_multicast():
                corr.logger.info('\t\tsource address %s is not multicast?' % source.ip_address)
            else:
                rxaddr = str(source.ip_address)
                rxaddr_bits = rxaddr.split('.')
                rxaddr_base = int(rxaddr_bits[3])
                rxaddr_prefix = '%s.%s.%s.' % (rxaddr_bits[0], rxaddr_bits[1], rxaddr_bits[2])
                if (len(fhost.tengbes) / corr.f_per_fpga) != source.ip_range:
                    raise RuntimeError(
                        '10Gbe ports (%d) do not match sources IPs (%d)' %
                        (len(fhost.tengbes), source.ip_range))
                for ctr in range(0, source.ip_range):
                    gbename = fhost.tengbes.names()[gbe_ctr]
                    gbe = fhost.tengbes[gbename]
                    rxaddress = '%s%d' % (rxaddr_prefix, rxaddr_base + ctr)
                    corr.logger.info('\t\t%s subscribing to address %s' % (gbe.name, rxaddress))
                    gbe.multicast_receive(rxaddress, 0)
                    gbe_ctr += 1
    corr.logger.info('done.')
