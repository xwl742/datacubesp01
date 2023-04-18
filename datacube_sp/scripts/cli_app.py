#!/usr/bin/env python

# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Datacube command-line interface
"""


from datacube_sp.ui.click import cli
import datacube_sp.scripts.dataset   # noqa: F401
import datacube_sp.scripts.ingest    # noqa: F401
import datacube_sp.scripts.product   # noqa: F401
import datacube_sp.scripts.metadata  # noqa: F401
import datacube_sp.scripts.system    # noqa: F401
import datacube_sp.scripts.user      # noqa: F401


if __name__ == '__main__':
    cli()
