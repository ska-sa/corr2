#!/usr/bin/env python
"""
Try to synch the VACCs on the x-engines in a correlator.
"""
import argparse
import os

from corr2 import fxcorrelator

parser = argparse.ArgumentParser(
    description='Try to synchronise the VACCs on the x-engines on a '
                'running correlator.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='corr2 config file')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='INFO',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level:
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=getattr(logging, log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']

c = fxcorrelator.FxCorrelator('rts correlator', config_source=args.config)
c.standard_log_config()
c.initialise(program=False)
c.xops.vacc_sync()

# end
