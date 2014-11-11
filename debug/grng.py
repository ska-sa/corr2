__author__ = 'paulp'

import casperfpga
import numpy

fpgfile = '/home/paulp/grng_to_snap_2014_Aug_27_1427.fpg'
host = 'roach020958'
correlation = 0  # 0-5 - see block


f = casperfpga.KatcpFpga(host)

f.upload_to_ram_and_program(fpgfile)

f.registers.control.write(reset='pulse', corrsel=correlation, snapwe=True)

f.registers.control.write(snaptrig='pulse')

data = f.snapshots.snapshot_ss.read(man_trig=True)

fftdata = numpy.fft.fft(data['data']['d0'], 1024)


