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
    description='Issue SPEAD metadata.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store',
    default='', help='corr2 config file')
parser.add_argument(
    '--comms', dest='comms', action='store', default='katcp',
    type=str, help='katcp (default) or dcp?')
parser.add_argument(
    '--beamformer', dest='beamformer', action='store_true', default=False,
    help='send beamformer metadata as well')
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

# make the correlator object and send the metadata
c = fxcorrelator.FxCorrelator('corr', config_source=args.config)
c.standard_log_config()
c.initialise(program=False)
c.speadops.meta_issue_all()
if args.beamformer:
    c.bops.spead_meta_issue_all()

# end
