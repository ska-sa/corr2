#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103
# pylint: disable-msg=C0301
"""
View the status of a given SNB filter board.

@author: paulp
"""
import argparse

parser = argparse.ArgumentParser(
    description='Display information about a MeerKAT SNB filter host.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='',
    help='log level to use, default None, options INFO, DEBUG, ERROR')
args = parser.parse_args()

if args.log_level:
    import logging
    log_level = args.log_level.strip()
    try:
        logging.basicConfig(level=getattr(logging, log_level))
    except AttributeError:
        raise RuntimeError('No such log level: %s' % log_level)

raise NotImplementedError('This will be completed when filter hosts'
                          'are in use.')

# end
