# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
import csv
import json
import logging
import sys
from typing import List

import click
import signal
import pandas as pd
import yaml
import yaml.resolver
from click import echo, style

from datacube_sp.index import Index
from datacube_sp.ui import click as ui
from datacube_sp.ui.click import cli, print_help_msg, exit_on_empty_file
from datacube_sp.utils import read_documents, InvalidDocException
from datacube_sp.utils.serialise import SafeDatacubeDumper

_LOG = logging.getLogger('datacube_sp-product')


@cli.group(name='product', help='Product commands')
def product_cli():
    pass


@product_cli.command('add')
@click.option('--allow-exclusive-lock/--forbid-exclusive-lock', is_flag=True, default=False,
              help='Allow index to be locked from other users while updating (default: false)')
@click.argument('files',
                type=str,
                nargs=-1)
@ui.pass_index()
def add_products(index, allow_exclusive_lock, files):
    # type: (Index, bool, list) -> None
    """
    Add or update products in the generic index.
    """
    if not files:
        print_help_msg(add_products)
        sys.exit(1)

    def on_ctrlc(sig, frame):
        echo('''Can not abort `product add` without leaving database in bad state.

This operation requires constructing a bunch of indexes and this takes time, the
bigger your database the longer it will take. Just wait a bit.''')

    signal.signal(signal.SIGINT, on_ctrlc)

    exit_on_empty_file(list(read_documents(*files)))

    for descriptor_path, parsed_doc in read_documents(*files):
        try:
            type_ = index.products.from_doc(parsed_doc)
            echo(f'Adding "{type_.name}" (this might take a while)', nl=False)
            index.products.add(type_, allow_table_lock=allow_exclusive_lock)
            echo(' DONE')
        except InvalidDocException as e:
            _LOG.exception(e)
            _LOG.error('Invalid product definition: %s', descriptor_path)
            sys.exit(1)


@product_cli.command('update')
@click.option(
    '--allow-unsafe/--forbid-unsafe', is_flag=True, default=False,
    help="Allow unsafe updates (default: false)"
)
@click.option('--allow-exclusive-lock/--forbid-exclusive-lock', is_flag=True, default=False,
              help='Allow index to be locked from other users while updating (default: false)')
@click.option('--dry-run', '-d', is_flag=True, default=False,
              help='Check if everything is ok')
@click.argument('files', type=str, nargs=-1)
@ui.pass_index()
def update_products(index: Index, allow_unsafe: bool, allow_exclusive_lock: bool, dry_run: bool, files: List):
    """
    Update existing products.

    An error will be thrown if a change is potentially unsafe.

    (An unsafe change is anything that may potentially make the product
    incompatible with existing datasets of that type)
    """
    if not files:
        print_help_msg(update_products)
        sys.exit(1)

    exit_on_empty_file(list(read_documents(*files)))

    failures = 0
    for descriptor_path, parsed_doc in read_documents(*files):
        try:
            type_ = index.products.from_doc(parsed_doc)
        except InvalidDocException as e:
            _LOG.exception(e)
            _LOG.error('Invalid product definition: %s', descriptor_path)
            failures += 1
            continue

        if not dry_run:
            try:
                index.products.update(
                    type_,
                    allow_unsafe_updates=allow_unsafe,
                    allow_table_lock=allow_exclusive_lock,
                )
                echo('Updated "%s"' % type_.name)
            except ValueError as e:
                echo('Failed to update "%s": %s' % (type_.name, e))
                failures += 1
        else:
            can_update, safe_changes, unsafe_changes = index.products.can_update(
                type_,
                allow_unsafe_updates=allow_unsafe
            )

            if can_update:
                echo('Can update "%s": %s unsafe changes, %s safe changes' % (type_.name,
                                                                              len(list(unsafe_changes)),
                                                                              len(list(safe_changes))))
            else:
                echo('Cannot update "%s": %s unsafe changes, %s safe changes' % (type_.name,
                                                                                 len(list(unsafe_changes)),
                                                                                 len(list(safe_changes))))
    sys.exit(failures)


def _write_csv(products):
    product_dicts = [prod.to_dict() for prod in products]
    writer = csv.DictWriter(sys.stdout, ['id', 'name', 'description',
                                         'ancillary_quality', 'latgqa_cep90', 'product_type',
                                         'gqa_abs_iterative_mean_xy', 'gqa_ref_source', 'sat_path',
                                         'gqa_iterative_stddev_xy', 'time', 'sat_row', 'orbit', 'gqa',
                                         'instrument', 'gqa_abs_xy', 'crs', 'resolution', 'tile_size',
                                         'spatial_dimensions'], extrasaction='ignore')
    writer.writeheader()
    writer.writerows(product_dicts)


def _write_yaml(products):
    """
    Dump yaml data with support for OrderedDicts.

    Allows for better human-readability of output: such as dataset ID field first, sources last.

    (Ordered dicts are output identically to normal yaml dicts: their order is purely for readability)
    """
    product_dicts = [prod.to_dict() for prod in products]

    return yaml.dump_all(product_dicts, sys.stdout, Dumper=SafeDatacubeDumper, default_flow_style=False, indent=4)


def _write_tab(products):
    df = pd.DataFrame(prod.to_dict() for prod in products)

    if df.empty:
        echo('No products discovered :(')
        return

    output_columns = ('id', 'name', 'description', 'ancillary_quality',
                      'product_type', 'gqa_abs_iterative_mean_xy',
                      'gqa_ref_source', 'sat_path',
                      'gqa_iterative_stddev_xy', 'time', 'sat_row',
                      'orbit', 'gqa', 'instrument', 'gqa_abs_xy', 'crs',
                      'resolution', 'tile_size', 'spatial_dimensions')
    # If the intersection of desired columns with available columns is empty, just use whatever IS in df
    output_columns = tuple(col for col in output_columns if col in df.columns) or df.columns
    echo(df.to_string(columns=output_columns, justify='left', index=False))


def _default_lister(products):
    products = list(products)
    if len(products) == 0:
        return

    max_w = max(len(p.name) for p in products)

    for prod in products:
        name = '{s:<{n}}'.format(s=prod.name, n=max_w)
        echo(style(name, fg='green') + '  ' + prod.definition.get('description', ''))


LIST_OUTPUT_WRITERS = {
    'default': _default_lister,
    'csv': _write_csv,
    'yaml': _write_yaml,
    'tab': _write_tab,
}


@product_cli.command('list')
@click.option('-f', 'output_format', help='Output format',
              type=click.Choice(list(LIST_OUTPUT_WRITERS)), default='default', show_default=True)
@ui.pass_datacube()
def list_products(dc, output_format):
    """
    List products that are defined in the generic index.
    """
    products = dc.index.products.search()

    writer = LIST_OUTPUT_WRITERS[output_format]

    writer(products)


@product_cli.command('show')
@click.option('-f', 'output_format', help='Output format',
              type=click.Choice(['yaml', 'json']), default='yaml', show_default=True)
@click.argument('product_name', nargs=-1)
@ui.pass_datacube()
def show_product(dc, product_name, output_format):
    """
    Show details about a product in the generic index.
    """

    if len(product_name) == 0:
        products = list(dc.index.products.get_all())
    else:
        products = []
        for name in product_name:
            p = dc.index.products.get_by_name(name)
            if p is None:
                echo('No such product: {!r}'.format(name), err=True)
                sys.exit(1)
            else:
                products.append(p)

    if len(products) == 0:
        echo('No products', err=True)
        sys.exit(1)

    if output_format == 'yaml':
        yaml.dump_all((p.definition for p in products),
                      sys.stdout,
                      Dumper=SafeDatacubeDumper,
                      default_flow_style=False,
                      indent=4)
    elif output_format == 'json':
        if len(products) > 1:
            echo('Can not output more than 1 product in json format', err=True)
            sys.exit(1)
        product, *_ = products
        click.echo_via_pager(json.dumps(product.definition, indent=4))
