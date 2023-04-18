# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
"""
This module implements a simple plugin manager for storage and index drivers.
"""

from .indexes import index_driver_by_name, index_drivers
from .readers import new_datasource, reader_drivers
from .writers import storage_writer_by_name, writer_drivers

__all__ = ['new_datasource', 'storage_writer_by_name',
           'index_driver_by_name', 'index_drivers',
           'reader_drivers', 'writer_drivers']
