# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Access methods for indexing datasets & products.
"""

import logging

from datacube_sp.config import LocalConfig
from datacube_sp.index.abstract import AbstractIndex

_LOG = logging.getLogger(__name__)


def index_connect(local_config: LocalConfig = None,
                  application_name: str = None,
                  validate_connection: bool = True) -> AbstractIndex:
    """
    Create a Data Cube Index (as per config)

    It contains all the required connection parameters, but doesn't actually
    check that the server is available.

    :param application_name: A short, alphanumeric name to identify this application.
    :param local_config: Config object to use. (optional)
    :param validate_connection: Validate database connection and schema immediately
    :raises datacube_sp.index.Exceptions.IndexSetupError:
    """
    from datacube_sp.drivers import index_driver_by_name, index_drivers

    if local_config is None:
        local_config = LocalConfig.find()

    driver_name = local_config.get('index_driver', 'default')
    index_driver = index_driver_by_name(driver_name)
    if not index_driver:
        raise RuntimeError(
            "No index driver found for %r. %s available: %s" % (
                driver_name, len(index_drivers()), ', '.join(index_drivers())
            )
        )

    return index_driver.connect_to_index(local_config,
                                         application_name=application_name,
                                         validate_connection=validate_connection)
