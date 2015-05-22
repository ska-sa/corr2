#!/usr/bin/env python

import argparse
import os

from corr2 import fxcorrelator

parser = argparse.ArgumentParser(description='Start a correlator.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--config', dest='config', type=str, action='store', default='',
                    help='corr2 config file')
parser.add_argument('--noprogram', dest='noprogram', action='store_true', default=False,
                    help='do NOT program the FPGAs, and everything that goes with that')
parser.add_argument('--noqdrcal', dest='no_qdr_cal', action='store_true', default=False,
                    help='do NOT calibrate the QDRs')
parser.add_argument('--loglevel', dest='log_level', action='store', default='',
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

c = fxcorrelator.FxCorrelator('rts correlator', config_source=args.config)
c.initialise(program=not args.noprogram, qdr_cal=not args.no_qdr_cal)

# end