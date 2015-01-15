__author__ = 'paulp'

from subprocess import check_output, call, CalledProcessError
import numpy
import time

# loc_pps_ctrl = 18
# loc_msync = 1

addr_control = 0x1028000
addr_localtime_msw = 0x1028A00
addr_localtime_lsw = 0x1028900
addr_offset_msw = 0x1029200
addr_offset_lsw = 0x1029300
addr_pps_ticks = 0x1028F00


def write_register(location, value):
    try:
        resp = check_output(['dcpcmd', '-s', '10.100.0.28', '0x%X=%i' % (location, value)])
    except CalledProcessError as e:
        raise e
    assert value == read_register(location)


def read_register(location):
    try:
        resp = check_output(['dcpcmd', '-s', '10.100.0.28', '0x%X' % location])
    except CalledProcessError as e:
        raise e
    lines = resp.split('\n')
    text_value = None
    for line in lines:
        try:
            if line.index('received\_word') > 0:
                text_value = line.split('\_')[-1]
                break
        except ValueError:
            pass
    return eval(text_value)


def decode_control_reg(value):
    return {'pps_ctrl': (value >> 18) & 0x03,
            'nd_mode': (value >> 15) & 0x07,
            'tvgsel_0': (value >> 13) & 0x3,
            'tvgsel_1': (value >> 11) & 0x03,
            'grng_corr': (value >> 8) & 0x07,
            'grng_reset': (value >> 7) & 0x01,
            'snap_tx_sel': (value >> 5) & 0x03,
            'clr_status': (value >> 4) & 0x01,
            'gbe_reset': (value >> 3) & 0x01,
            'gbe_enable': (value >> 2) & 0x01,
            'msync': (value >> 1) & 0x01,
            'mrst': (value >> 0) & 0x01,
            }


def recode_control_value(valdict):
    return ((valdict['pps_ctrl'] & 0x03) << 18) | \
           ((valdict['nd_mode'] & 0x07) << 15) | \
           ((valdict['tvgsel_0'] & 0x03) << 13) | \
           ((valdict['tvgsel_1'] & 0x03) << 11) | \
           ((valdict['grng_corr'] & 0x07) << 8) | \
           ((valdict['grng_reset'] & 0x01) << 7) | \
           ((valdict['snap_tx_sel'] & 0x03) << 5) | \
           ((valdict['clr_status'] & 0x01) << 4) | \
           ((valdict['gbe_reset'] & 0x01) << 3) | \
           ((valdict['gbe_enable'] & 0x01) << 2) | \
           ((valdict['msync'] & 0x01) << 1) | \
           ((valdict['mrst'] & 0x01) << 0)

control_current = read_register(addr_control)
print 'Current control register:', format(control_current, '#032b')
print '\tdecoded:', decode_control_reg(control_current)
print '\trecoded:', format(recode_control_value(decode_control_reg(control_current)), '#032b')
assert control_current == recode_control_value(decode_control_reg(control_current))

print '\nCurrent PPS ticks: 0x%032X' % read_register(addr_pps_ticks)

local_time = (read_register(addr_localtime_msw) << 32) | (read_register(addr_localtime_lsw))
print '\nCurrent local time: %i (%.2f bits)' % (local_time, numpy.log2(local_time))

offset_time = (read_register(addr_offset_msw) << 32) | (read_register(addr_offset_lsw))
print '\nCurrent offsettime: %i (%.2f bits)' % (offset_time, numpy.log2(offset_time) if offset_time > 0 else 0)

# set the offset time so that it will wrap in 5 minutes time
wrap_offset = 2**48 - (2 * 60 * 1720000000)
# wrap_offset = int(2**47 * 1.8)
# wrap_offset = 1000000003
wrap_offset_msb = wrap_offset >> 32
wrap_offset_lsb = wrap_offset & ((2**32-1) - (2**3-1))
write_register(addr_offset_msw, wrap_offset_msb)
write_register(addr_offset_lsw, wrap_offset_lsb)

# enable the software pps
control_current = read_register(addr_control)
control_dict = decode_control_reg(control_current)
control_dict['pps_ctrl'] = 1
control_new = recode_control_value(control_dict)
print 'New control register:', format(control_new, '#032b')
print '\tdecoded:', decode_control_reg(control_new)
write_register(addr_control, control_new)
# control_dict['pps_ctrl'] = 0
# control_new = recode_control_value(control_dict)
# write_register(addr_control, control_new)

# check the ticking pps
while True:
    print '\nCurrent PPS ticks: 0x%032X' % read_register(addr_pps_ticks)
    local_time = (read_register(addr_localtime_msw) << 32) | (read_register(addr_localtime_lsw))
    print 'Current local time: %i (%.2f bits) %s' % (local_time,
                                                     numpy.log2(local_time),
                                                     '3OKAY' if local_time & (2**3-1) == 0 else '3BAD')
    offset_time = (read_register(addr_offset_msw) << 32) | (read_register(addr_offset_lsw))
    print 'Current offsettime: %i (%.2f bits)' % (offset_time, numpy.log2(offset_time) if offset_time > 0 else 0)
    time.sleep(1)
