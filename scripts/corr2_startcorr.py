#!/usr/bin/env python

import argparse

from corr2 import fxcorrelator

parser = argparse.ArgumentParser(description='Start a correlator.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(dest='config', type=str, action='store',
                    help='corr2 config file')
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

c = fxcorrelator.FxCorrelator('rts correlator', config_source=args.config)
c.initialise()

# end