# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Serialise function used in YAML output
"""

import math
from collections import OrderedDict
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

import numpy
import yaml

from datacube_sp.utils.documents import transform_object_tree
from datacube_sp.model._base import Range


class SafeDatacubeDumper(yaml.SafeDumper):  # pylint: disable=too-many-ancestors
    pass


def _dict_representer(dumper: SafeDatacubeDumper, data: OrderedDict) -> yaml.Node:
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())


def _reduced_accuracy_decimal_representer(dumper: SafeDatacubeDumper, data: Decimal) -> yaml.Node:
    return dumper.represent_float(float(data))


def _range_representer(dumper: SafeDatacubeDumper, data: Range) -> yaml.Node:
    begin, end = data

    # pyyaml doesn't output timestamps in flow style as timestamps(?)
    if isinstance(begin, datetime):
        begin = begin.isoformat()
    if isinstance(end, datetime):
        end = end.isoformat()

    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        (('begin', begin), ('end', end)),
        flow_style=True
    )


SafeDatacubeDumper.add_representer(OrderedDict, _dict_representer)
SafeDatacubeDumper.add_representer(Decimal, _reduced_accuracy_decimal_representer)
SafeDatacubeDumper.add_representer(Range, _range_representer)


def jsonify_document(doc):
    """
    Make a document ready for serialisation as JSON.

    Returns the new document, leaving the original unmodified.

    """

    def fixup_value(v):
        if isinstance(v, float):
            if math.isfinite(v):
                return v
            if math.isnan(v):
                return "NaN"
            return "-Infinity" if v < 0 else "Infinity"
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        if isinstance(v, numpy.dtype):
            return v.name
        if isinstance(v, UUID):
            return str(v)
        if isinstance(v, Decimal):
            return str(v)
        return v

    return transform_object_tree(fixup_value, doc, key_transform=str)
