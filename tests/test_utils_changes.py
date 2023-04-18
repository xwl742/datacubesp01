# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
from datacube_sp.utils.changes import (
    contains,
    classify_changes,
    allow_any,
    allow_removal,
    allow_addition,
    allow_extension,
    allow_truncation,
    MISSING,
)


def test_changes_contains():
    assert contains("bob", "BOB") is True
    assert contains("bob", "BOB", case_sensitive=True) is False
    assert contains(1, 1) is True
    assert contains(1, {}) is False
    # same as above, but with None interpreted as {}
    assert contains(1, None) is False
    assert contains({}, 1) is False
    assert contains(None, 1) is False
    assert contains({}, {}) is True
    assert contains({}, None) is True

    # this one is arguable...
    assert contains(None, {}) is False
    assert contains(None, None) is True
    assert contains({"a": 1, "b": 2}, {"a": 1}) is True
    assert contains({"a": {"b": "BOB"}}, {"a": {"b": "bob"}}) is True
    assert (
        contains({"a": {"b": "BOB"}}, {"a": {"b": "bob"}}, case_sensitive=True) is False
    )
    assert contains("bob", "alice") is False
    assert contains({"a": 1}, {"a": 1, "b": 2}) is False
    assert contains({"a": {"b": 1}}, {"a": {}}) is True
    assert contains({"a": {"b": 1}}, {"a": None}) is True


def test_classify_changes():
    assert classify_changes([], {}) == ([], [])
    assert classify_changes([(('a',), 1, 2)], {}) == ([], [(('a',), 1, 2)])
    assert classify_changes([(('a',), 1, 2)], {('a',): allow_any}) == ([(('a',), 1, 2)], [])

    changes = [(('a2',), {'b1': 1}, MISSING)]  # {'a1': 1, 'a2': {'b1': 1}} → {'a1': 1}
    good_change = (changes, [])
    bad_change = ([], changes)
    assert classify_changes(changes, {}) == bad_change
    assert classify_changes(changes, {tuple(): allow_any}) == good_change
    assert classify_changes(changes, {tuple(): allow_removal}) == bad_change
    assert classify_changes(changes, {tuple(): allow_addition}) == bad_change
    assert classify_changes(changes, {tuple(): allow_truncation}) == good_change
    assert classify_changes(changes, {tuple(): allow_extension}) == bad_change
    assert classify_changes(changes, {('a1', ): allow_any}) == bad_change
    assert classify_changes(changes, {('a1', ): allow_removal}) == bad_change
    assert classify_changes(changes, {('a1', ): allow_addition}) == bad_change
    assert classify_changes(changes, {('a1', ): allow_truncation}) == bad_change
    assert classify_changes(changes, {('a1', ): allow_extension}) == bad_change
    assert classify_changes(changes, {('a2', ): allow_any}) == good_change
    assert classify_changes(changes, {('a2', ): allow_removal}) == good_change
    assert classify_changes(changes, {('a2', ): allow_addition}) == bad_change
    assert classify_changes(changes, {('a2', ): allow_truncation}) == bad_change
    assert classify_changes(changes, {('a2', ): allow_extension}) == bad_change

    with pytest.raises(RuntimeError):
        classify_changes(changes, {('a2', ): object()})

    assert str(MISSING) == repr(MISSING)
