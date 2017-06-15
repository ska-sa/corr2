#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Issue spead metadata for a data product.

BE CAREFUL WITH THIS! Much metadata will change as the instrument is
set up and used. These changes WILL NOT REFLECT in a base instrument created
from the config file, which is what this will give you.

It is recommended that you use ?capture-meta against your running instrument!

@author: paulp
"""
import argparse
import os

from corr2 import fxcorrelator

parser = argparse.ArgumentParser(
    description='Issue SPEAD metadata for a data product on this instrument.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '-product', dest='product', action='store', default='',
    help='the name of the product on which to act')
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

prod_list = []

if args.product == '':
    prod_list = c.data_products.values()
else:
    if args.product not in c.data_products:
        print('ERROR: %s not in data products for this '
              'instrument.' % args.product)
    else:
        prod_list = [c.data_products[args.product]]

if args.listproducts or (len(prod_list) == 0):
    print('Available products:')
    for prod in c.data_products.values():
        print('\t%s' % prod)
    import sys
    sys.exit()

for prod in prod_list:
    prod.meta_issue()

if args.ipython:
    import IPython
    IPython.embed()

# end
