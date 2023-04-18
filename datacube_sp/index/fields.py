# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Common datatypes for DB drivers.
"""

from datetime import date, datetime, time
from dateutil.tz import tz
from typing import List

from datacube_sp.model import Range
from datacube_sp.model.fields import Expression, Field

__all__ = ['Field',
           'Expression',
           'OrExpression',
           'UnknownFieldError',
           'to_expressions',
           'as_expression']


class UnknownFieldError(Exception):
    pass


class OrExpression(Expression):
    def __init__(self, *exprs):
        super(OrExpression, self).__init__()
        self.exprs = exprs
        # Or expressions built by dc.load are always made up of simple expressions that share the same field.
        self.field = exprs[0].field

    def evaluate(self, ctx):
        return any(expr.evaluate(ctx) for expr in self.exprs)


def as_expression(field: Field, value) -> Expression:
    """
    Convert a single field/value to expression, following the "simple" convensions.
    """
    if isinstance(value, Range):
        return field.between(value.begin, value.end)
    elif isinstance(value, list):
        return OrExpression(*(as_expression(field, val) for val in value))
    # Treat a date (day) as a time range.
    elif isinstance(value, date) and not isinstance(value, datetime):
        return as_expression(
            field,
            Range(
                datetime.combine(value, time.min.replace(tzinfo=tz.tzutc())),
                datetime.combine(value, time.max.replace(tzinfo=tz.tzutc()))
            )
        )
    return field == value


def _to_expression(get_field, name: str, value) -> Expression:
    field = get_field(name)
    if field is None:
        raise UnknownFieldError('Unknown field %r' % name)

    return as_expression(field, value)


def to_expressions(get_field, **query) -> List[Expression]:
    """
    Convert a simple query (dict of param names and values) to expression objects.
    :type get_field: (str) -> Field
    :type query: dict[str,str|float|datacube.model.Range]
    """
    return [_to_expression(get_field, name, value) for name, value in query.items()]
