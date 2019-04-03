#!/usr/bin/env python
import numpy
import matplotlib.pyplot as plt
import corr2
import casperfpga
import time
import argparse
import os

parser = argparse.ArgumentParser(
    description='Display the input power levels from the DIGs.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='a corr2 config file.')
parser.add_argument('-d', '--db', dest='plot_db', action='store_true',
                    default=False,
                    help='Plot power in dBFS rather than linear raw ADC values.')
args = parser.parse_args()
configfile = args.config
if 'CORR2INI' in os.environ.keys() and configfile == '':
    configfile = os.environ['CORR2INI']
if configfile == '':
    raise RuntimeError('No good carrying on without a config file')
c = corr2.fxcorrelator.FxCorrelator('adcplot', config_source=configfile)

plot_db=args.plot_db
n_bits=10
min_range=20*numpy.log10(1./(2**n_bits))

fig, axs = plt.subplots(nrows=1, ncols=2, sharex=True)
plt.ion()
plt.show(False)
plt.draw()

c.initialise(program=False,configure=False,require_epoch=False)
plt_update=0

def plot_linear():
    xmean=[[],[]]
    xmax=[[],[]]
    xmin=[[],[]]
    stdev=[[],[]]
    for pol in range(2):
        xmean[pol]=numpy.zeros(len(results))
        stdev[pol]=numpy.zeros(len(results))
        xmax[pol]=numpy.zeros(len(results))
        xmin[pol]=numpy.zeros(len(results))
        for n,fhost in enumerate(c.fhosts):
            xmean[pol][n] = (results[fhost.host]['p%i_min'%pol]+results[fhost.host]['p%i_max'%pol])/2
            stdev[pol][n] = 10**(results[fhost.host]['p%i_pwr_dBFS'%pol]/20)
            xmax[pol][n] = results[fhost.host]['p%i_max'%pol]
            xmin[pol][n] = results[fhost.host]['p%i_min'%pol]

    y = numpy.arange(len(results))

    ax = axs[0]
    ax.hlines(y, xmin[0], xmax[0], color='g',linewidth=2.0)
    ax.hlines(y, -stdev[0], stdev[0], color='b',linewidth=3.0)
    ax.plot(xmean[0],y,'ro')
    ax.set_title('Pol 0')
    ax.set_xlim(-1,1)
    ax.set_ylim(-1,len(results))

    ax = axs[1]
    ax.hlines(y, xmin[1], xmax[1], color='g',linewidth=2.0)
    ax.hlines(y, -stdev[1], stdev[1], color='b',linewidth=3.0)
    ax.plot(xmean[1],y,'ro')
    ax.set_title('Pol 1')
    ax.set_xlim(-1,1)
    ax.set_ylim(-1,len(results))

def plot_log():
    xmean=[[],[]]
    xmax=[[],[]]
    for pol in range(2):
        xmean[pol]=numpy.zeros(len(results))
        xmax[pol]=numpy.zeros(len(results))
        for n,fhost in enumerate(c.fhosts):
            xmean[pol][n] = results[fhost.host]['p%i_pwr_dBFS'%pol]
            xmax[pol][n] = 20*numpy.log10(results[fhost.host]['p%i_max'%pol])

    y = numpy.arange(len(results))

    ax = axs[0]
    ax.clear()
    ax.hlines(y, min_range, xmax[0], color='b',linewidth=2.0)
    ax.hlines(y, min_range, xmean[0], color='g',linewidth=3.0)
    ax.set_title('Pol 0')
    ax.set_xlim(min_range,0)
    ax.set_ylim(-1,len(results))

    ax = axs[1]
    ax.clear()
    ax.hlines(y, min_range, xmax[1], color='b',linewidth=2.0)
    ax.hlines(y, min_range, xmean[1], color='g',linewidth=3.0)
    ax.set_title('Pol 1')
    ax.set_xlim(min_range,0)
    ax.set_ylim(-1,len(results))


while(True):
    plt_update += 1
    results=casperfpga.utils.threaded_fpga_operation(c.fhosts,timeout=10,target_function=(lambda feng_:feng_.get_adc_status(),))
    #fig.canvas.clear()
    if plot_db: plot_log()
    else: plot_linear()
    #from IPython import embed; embed()
    fig.canvas.draw()
    print  'Update {}'.format(plt_update)
    time.sleep(0.1)

plt.close(fig)
