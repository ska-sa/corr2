#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check the SPEAD error counter and valid counter in the 
unpack section of the F-engines.

@author: paulp
"""
import os
import logging

# force the use of the TkAgg backend
import matplotlib
matplotlib.use('TkAgg')

from matplotlib import pyplot
from casperfpga import casperfpga

logging.basicConfig(level=logging.INFO)

DENG = True

f = casperfpga.CasperFpga(os.environ['SKARAB_DSIM'])
f.get_system_information(os.environ['SKARAB_DSIM_FPG'])


def get_output_samples():
    snap = f.snapshots.ss_fifo_in_ss.read(man_trig=True)['data']
    samples = []
    for ctr in range(len(snap['d0'])):
        for ctr2 in range(8):
            samples.append(snap['d%1i' % ctr2][ctr])
    return samples


samples = get_output_samples()

print sum(samples)

fig = pyplot.figure()
sub_plot = fig.add_subplot(1, 1, 1)
sub_plot.plot(samples)
pyplot.show()


# end
