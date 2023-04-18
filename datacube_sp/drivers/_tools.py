# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
from threading import Lock
from typing import Any

DRIVER_CACHE_LOCK = Lock()
NOT_SET_MARKER = object()


def singleton_setup(obj: object,
                    key: str,
                    factory,
                    *args,
                    **kwargs) -> Any:
    """
    Does:
      obj.key = factory(*args, **kwargs)  # but only once and in a thread safe manner
      return obj.key
    """
    v = getattr(obj, key, NOT_SET_MARKER)
    if v is not NOT_SET_MARKER:
        return v

    with DRIVER_CACHE_LOCK:
        v = getattr(obj, key, NOT_SET_MARKER)
        if v is not NOT_SET_MARKER:
            # very rare multi-thread only event.
            # Other thread did it first but after this thread's initial check above.
            # Disable test cover
            return v  # pragma: no cover
        v = factory(*args, **kwargs)
        setattr(obj, key, v)
        return v
