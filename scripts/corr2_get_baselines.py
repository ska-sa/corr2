#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Get the list of baselines for a given configuration
"""

import argparse
import os

import corr2

parser = argparse.ArgumentParser(description='Print out the list of baselines for this correlator config.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='the config file to parse, $CORR2INI will be used if this is not specified')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
                    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging. %s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

configfile = args.config
if 'CORR2INI' in os.environ.keys() and configfile == '':
    configfile = os.environ['CORR2INI']
if configfile == '':
    raise RuntimeError('No good carrying on without a config file')

c = corr2.fxcorrelator.FxCorrelator('script_corr', config_source=configfile)
c.initialise(program=False)
for ctr, baseline in enumerate(c.xeng_get_baseline_order()):
    print ctr, ':', baseline
