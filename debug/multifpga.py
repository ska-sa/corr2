import logging

from casperfpga import utils as casperutils

logging.basicConfig(level=logging.INFO)

some_skarabs = ['10.99.49.171', '10.99.51.170', '10.99.53.170', '10.99.57.170']
a_fpg = '/home/paulp/bofs/sbram_test_2017-6-14_1312.fpg'
program = False

fpgas = casperutils.threaded_create_fpgas_from_hosts(some_skarabs)

# a func that exists on the fpga object
if program:
    casperutils.threaded_fpga_function(
        fpgas, timeout=120,
        target_function=('upload_to_ram_and_program', [a_fpg], {}))
else:
    casperutils.threaded_fpga_function(
        fpgas, timeout=120,
        target_function=('get_system_information', [a_fpg], {}))
print(50*'%')

# another func that exists on the fpga object
print(casperutils.threaded_fpga_function(
    fpgas, timeout=120, target_function=('listdev', [], {})))
print(50*'%')


def some_func(fpga, an_arg, a_kwarg):
    return fpga.host + '_' + str(an_arg) + '_' + str(a_kwarg)

# a custom func
print(casperutils.threaded_fpga_operation(
    fpgas, timeout=10,
    target_function=(some_func, [34], {'a_kwarg': 'astring'})))
print(50*'%')

# a lambda func
print(casperutils.threaded_fpga_operation(
    fpgas, timeout=10,
    target_function=(
        lambda fpga: fpga.registers.ram_control.read()['data'], [], {})))

# end
