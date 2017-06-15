#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Get the list of baselines for a given configuration.
"""

import argparse
import os

from corr2 import utils

parser = argparse.ArgumentParser(
    description='Print out the list of baselines for this correlator config.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--config', dest='config', type=str, action='store', default='',
    help='the config file to parse, $CORR2INI will be used if this is not '
         'specified')
parser.add_argument(
    '--loglevel', dest='log_level', action='store', default='INFO',
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

configd = utils.parse_ini_file(configfile)
baselines = utils.baselines_from_config(config=configd)
fhosts = utils.hosts_from_config(config=configd, section='fengine')
sources = utils.sources_from_config(config=configd)
source_to_host = utils.source_to_host(sources, config=configd)

bls_hosts = []
for ctr, baseline in enumerate(baselines):
    bls_hosts.append((source_to_host[baseline[0]],
                      source_to_host[baseline[1]]))

for ctr, baseline in enumerate(baselines):
    ax = 'A' if baseline[0] == baseline[1] else ''
    print(ctr, ':', baseline, '-', bls_hosts[ctr], ax

# end
