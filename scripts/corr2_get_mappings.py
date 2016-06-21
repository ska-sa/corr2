#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Get different mappings in this system
"""

import argparse
import os

from corr2 import utils

parser = argparse.ArgumentParser(
    description='Print out different mappings in this system.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument(
    '--host', dest='host', type=str, action='store',
    default='', help='given a hostname, return information associated with it')
parser.add_argument(
    '--source', dest='source', type=str, action='store',
    default='', help='given a source name, return information associated '
                     'with it')
parser.add_argument(
    '--baseline_index', dest='baseline_index', type=int, action='store',
    default=-1, help='given a baseline index, return information associated '
                     'with it')
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


def baselines_from_source(source):
    rv = {}
    for ctr, baseline in enumerate(baselines):
        if source == baseline[0] or source == baseline[1]:
            rv[ctr] = baseline
    return rv


# host name
if args.host != '':
    host = args.host
    print '%s:' % host
    print '\tSources:'
    bls = {}
    srcs = utils.host_to_sources(host, config=configd)
    for ctr, source in enumerate(srcs[host]):
        print '\t\t%i: %s' % (ctr, source)
        bls.update(baselines_from_source(source))
    print '\tBaselines:'
    for bls_index in bls:
        print '\t\t%i: %s' % (bls_index, bls[bls_index])

elif args.source != '':
    source = args.source
    print '%s:' % source
    all_sources = utils.host_to_sources(fhosts, config=configd)
    source_host = None
    for host in all_sources:
        for src in all_sources[host]:
            if src == args.source:
                source_host = host
                break
    if not source_host:
        print '\tERROR: could not match source %s to system host.' % source
    else:
        print '\tMatched to host %s.' % source_host
        bls = baselines_from_source(source)
        print '\tBaselines:'
        for bls_index in bls:
            print '\t\t%i: %s' % (bls_index, bls[bls_index])

elif args.baseline_index != -1:
    print 'Baseline %i:' % args.baseline_index, baselines[args.baseline_index]

# end
