#!/usr/bin/env python

"""
Start and stop data products.

It is recommended that you use ?capture-[start/stop] against your
running instrument!

@author: paulp
"""

import argparse
import os

from corr2 import fxcorrelator

parser = argparse.ArgumentParser(
    description='Start or stop a data product.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '-product', dest='product', action='store', default='all',
    help='the name of the product on which to act, default is ALL of them')
parser.add_argument(
    '--start', dest='start', action='store_true', default=False,
    help='start TX')
parser.add_argument(
    '--stop', dest='stop', action='store_true', default=False,
    help='stop TX')
parser.add_argument(
    '--listproducts', dest='listproducts', action='store_true', default=False,
    help='list available products and exit')
parser.add_argument(
    '--config', dest='config', type=str, action='store',
    default='', help='corr2 config file')
parser.add_argument(
    '--ipython', dest='ipython', action='store_true', default=False,
    help='start an ipython session after completion/error')
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

if not (args.stop or args.start or args.listproducts):
    print 'Cowardly refusing to do nothing!'
    import sys
    sys.exit()

if 'CORR2INI' in os.environ.keys() and args.config == '':
    args.config = os.environ['CORR2INI']

c = fxcorrelator.FxCorrelator('correlator',
                              config_source=args.config)
c.standard_log_config(log_level=eval('logging.%s' % log_level))
c.initialise(program=False, qdr_cal=False)

if (args.product != '') and (args.product != 'all') and \
        (args.product not in c.data_products):
    print 'ERROR: %s not in data products for this instrument.' % args.product
    args.listproducts = True

if args.listproducts:
    print 'Available products:'
    for prod in c.data_products.values():
        print '\t', prod
    import sys
    sys.exit()

if args.product == 'all':
    prods = c.data_products.keys()
else:
    prods = args.product.split(',')

if args.start:
    for prod in prods:
        c.data_products[prod].tx_enable()
elif args.stop:
    for prod in prods:
        c.data_products[prod].tx_disable()

if args.ipython:
    import IPython
    IPython.embed()

# end
