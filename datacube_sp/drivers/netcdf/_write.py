# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import logging

from . import writer as netcdf_writer
from datacube_sp.utils import DatacubeException
from datacube_sp.storage._hdf5 import HDF5_LOCK


_LOG = logging.getLogger(__name__)


def _get_units(coord):
    """
    Guess units from coordinate
    1. Value of .units if set
    2. 'seconds since 1970-01-01 00:00:00' if coord dtype is datetime
    3. '1' otherwise
    """
    units = getattr(coord, 'units', None)
    if units is not None:
        return units
    dtype = getattr(coord.values, 'dtype', None)
    if dtype is None:
        return '1'

    if dtype.kind == 'M':
        return 'seconds since 1970-01-01 00:00:00'

    return '1'


def create_netcdf_storage_unit(filename,
                               crs, coordinates, variables, variable_params, global_attributes=None,
                               netcdfparams=None):
    """
    Create a NetCDF file on disk.

    :param pathlib.Path filename: filename to write to
    :param datacube.utils.geometry.CRS crs: Datacube CRS object defining the spatial projection
    :param dict coordinates: Dict of named `datacube_sp.model.Coordinate`s to create
    :param dict variables: Dict of named `datacube_sp.model.Variable`s to create
    :param dict variable_params:
        Dict of dicts, with keys matching variable names, of extra parameters for variables
    :param dict global_attributes: named global attributes to add to output file
    :param dict netcdfparams: Extra parameters to use when creating netcdf file
    :return: open netCDF4.Dataset object, ready for writing to
    """
    filename = Path(filename)
    if filename.exists():
        raise RuntimeError('Storage Unit already exists: %s' % filename)

    try:
        filename.parent.mkdir(parents=True)
    except OSError:
        pass

    _LOG.info('Creating storage unit: %s', filename)

    nco = netcdf_writer.create_netcdf(str(filename), **(netcdfparams or {}))

    for name, coord in coordinates.items():
        if coord.values.ndim > 0:  # skip CRS coordinate
            netcdf_writer.create_coordinate(nco, name, coord.values, _get_units(coord))

    grid_mapping = netcdf_writer.DEFAULT_GRID_MAPPING
    netcdf_writer.create_grid_mapping_variable(nco, crs, name=grid_mapping)

    for name, variable in variables.items():
        has_crs = all(dim in variable.dims for dim in crs.dimensions)
        var_params = variable_params.get(name, {})
        data_var = netcdf_writer.create_variable(nco, name, variable,
                                                 grid_mapping=grid_mapping if has_crs else None,
                                                 **var_params)

        for key, value in var_params.get('attrs', {}).items():
            setattr(data_var, key, value)

    for key, value in (global_attributes or {}).items():
        setattr(nco, key, value)

    return nco


def write_dataset_to_netcdf(dataset, filename, global_attributes=None, variable_params=None,
                            netcdfparams=None):
    """
    Write a Data Cube style xarray Dataset to a NetCDF file

    Requires a spatial Dataset, with attached coordinates and global crs attribute.

    :param `xarray.Dataset` dataset:
    :param filename: Output filename
    :param global_attributes: Global file attributes. dict of attr_name: attr_value
    :param variable_params: dict of variable_name: {param_name: param_value, [...]}
                            Allows setting storage and compression options per variable.
                            See the `netCDF4.Dataset.createVariable` for available
                            parameters.
    :param netcdfparams: Optional params affecting netCDF file creation
    """
    global_attributes = global_attributes or {}
    variable_params = variable_params or {}
    filename = Path(filename)

    if not dataset.data_vars.keys():
        raise DatacubeException('Cannot save empty dataset to disk.')

    if dataset.geobox is None:
        raise DatacubeException('Dataset geobox property is None, cannot write to NetCDF file.')

    try:
        HDF5_LOCK.acquire(blocking=True)
        nco = create_netcdf_storage_unit(filename,
                                         dataset.geobox.crs,
                                         dataset.coords,
                                         dataset.data_vars,
                                         variable_params,
                                         global_attributes,
                                         netcdfparams)

        for name, variable in dataset.data_vars.items():
            nco[name][:] = netcdf_writer.netcdfy_data(variable.values)

        nco.close()
    finally:
        HDF5_LOCK.release()
