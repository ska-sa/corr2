#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Issue spead metadata for this correlator

@author: paulp
"""
import argparse
import os

from corr2 import fxcorrelator

parser = argparse.ArgumentParser(
    description='Activate/deactivate partitions on the beamformer.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store',
    default='', help='corr2 config file')
# parser.add_argument(
#     '--beam', dest='beamname', type=str, action='store', default='',
#     help='beam on which to act, default: ALL beams')
# parser.add_argument(
#     '--listbeams', dest='listbeams', action='store_true', default=False,
#     help='show the beams on this beamformer')
parser.add_argument(
    '--activate', dest='activate', type=str, action='store',
    default='', help='the partitions to activate, a comma-separated list. e.g.'
                     '3,4,5,6. all means ALL.')
parser.add_argument(
    '--deactivate', dest='deactivate', type=str, action='store',
    default='', help='the partitions to deactivate, a comma-separated list. '
                     'e.g. 7,8,9. all means ALL.')
parser.add_argument(
    '--loglevel', dest='log_level', action='store',
    default='INFO',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level != '':
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=eval('logging.%s' % log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']

if args.activate == '' and args.deactivate == '':
    raise RuntimeError('Cowardly refusing to do nothing!')
elif args.activate == 'all' and args.deactivate == 'all':
    raise RuntimeError('Activate EVERYTHING and deactivate EVERYTHING? Que?')

# make the correlator object and send the metadata
c = fxcorrelator.FxCorrelator('corr', config_source=args.config)
c.standard_log_config()
c.initialise(program=False)

if args.activate == 'all':
    c.bops.partitions_activate()
    c.bops.tx_control_update()
elif args.activate != '':
    argslist = args.activate.strip().split(',')
    partlist = [int(arg) for arg in argslist]
    if len(partlist) > 0:
        c.bops.partitions_activate(partlist)
        c.bops.tx_control_update()

if args.deactivate == 'all':
    c.bops.partitions_deactivate()
    c.bops.tx_control_update()
elif args.deactivate != '':
    argslist = args.deactivate.strip().split(',')
    partlist = [int(arg) for arg in argslist]
    if len(partlist) > 0:
        c.bops.partitions_deactivate(partlist)
        c.bops.tx_control_update()

# end
