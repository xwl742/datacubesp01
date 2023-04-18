# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Create netCDF4 Storage Units and write data to them
"""

import logging
import numbers
from datetime import datetime
from collections import namedtuple
import numpy

from datacube_sp.utils.masking import describe_flags_def
from datacube_sp.utils import geometry, data_resolution_and_offset
from ._safestrings import SafeStringsDataset as Dataset

from datacube_sp import __version__

Variable = namedtuple('Variable', ('dtype', 'nodata', 'dims', 'units'))
_LOG = logging.getLogger(__name__)
DEFAULT_GRID_MAPPING = 'spatial_ref'

_STANDARD_COORDINATES = {
    'longitude': {
        'standard_name': 'longitude',
        'long_name': 'longitude',
        'axis': 'X'
    },
    'latitude': {
        'standard_name': 'latitude',
        'long_name': 'latitude',
        'axis': 'Y'
    },
    'x': {
        'standard_name': 'projection_x_coordinate',
        'long_name': 'x coordinate of projection',
        # 'axis': 'X'  # this makes gdal (2.0.0) think x is longitude and it does bad things to it (subtract 360)
    },
    'y': {
        'standard_name': 'projection_y_coordinate',
        'long_name': 'y coordinate of projection',
        # 'axis': 'Y'  # see x's axis comment above
    },
    'time': {
        'standard_name': 'time',
        'long_name': 'Time, unix time-stamp',
        'axis': 'T',
        'calendar': 'standard'
    }
}


def create_netcdf(netcdf_path, **kwargs):
    """
    Create and return an empty NetCDF file

    :param netcdf_path: File path to write to
    :param kwargs: See :class:`Dataset` for more information
    :return: open NetCDF Dataset
    """
    nco = Dataset(netcdf_path, 'w', **kwargs)
    nco.date_created = datetime.today().isoformat()
    nco.setncattr('Conventions', 'CF-1.6, ACDD-1.3')
    nco.history = ("NetCDF-CF file created by "
                   "datacube_sp version '{}' at {:%Y%m%d}."
                   .format(__version__, datetime.utcnow()))
    return nco


def append_netcdf(netcdf_path):
    """
    Open a NetCDF file in append mode

    :param netcdf_path:
    :return: open NetCDF Dataset
    """
    return Dataset(netcdf_path, 'a')


def create_coordinate(nco, name, labels, units):
    """
    :type nco: netCDF4.Dataset
    :type name: str
    :type labels: numpy.array
    :type units: str
    :rtype: netCDF4.Variable
    """
    labels = netcdfy_coord(labels)

    nco.createDimension(name, labels.size)
    var = nco.createVariable(name, labels.dtype, name)
    var[:] = labels

    var.units = units
    for key, value in _STANDARD_COORDINATES.get(name, {}).items():
        setattr(var, key, value)

    return var


def create_variable(nco, name, var, grid_mapping=None, attrs=None, **kwargs):
    """
    :param nco:
    :param name:
    :param datacube_sp.model.Variable var:
    :param kwargs:
    :return:
    """
    assert var.dtype.kind != 'U'  # Creates Non CF-Compliant NetCDF File

    def clamp_chunksizes(chunksizes, dim_names):
        if chunksizes is None:
            return None

        maxsizes = [len(nco.dimensions[dim]) for dim in dim_names]

        # pad chunksizes to new dimension length if too short
        chunksizes = tuple(chunksizes) + tuple(maxsizes[len(chunksizes):])

        # clamp
        return [min(sz, maxsz) for sz, maxsz in zip(chunksizes, maxsizes)]

    if var.dtype.kind == 'S' and var.dtype.itemsize > 1:
        new_dim_name = name + '_nchar'
        nco.createDimension(new_dim_name, size=var.dtype.itemsize)

        dims = tuple(var.dims) + (new_dim_name,)
        datatype = numpy.dtype('S1')
    else:
        dims = var.dims
        datatype = var.dtype

    chunksizes = clamp_chunksizes(kwargs.pop('chunksizes', None), dims)

    data_var = nco.createVariable(varname=name,
                                  datatype=datatype,
                                  dimensions=dims,
                                  fill_value=getattr(var, 'nodata', None),
                                  chunksizes=chunksizes,
                                  **kwargs)
    if grid_mapping is not None:
        data_var.grid_mapping = grid_mapping
    if getattr(var, 'units', None):
        data_var.units = var.units
    data_var.set_auto_maskandscale(False)
    return data_var


def _create_latlon_grid_mapping_variable(nco, crs, name=DEFAULT_GRID_MAPPING):
    crs_var = nco.createVariable(name, 'i4')
    crs_var.long_name = crs._crs.name  # "Lon/Lat Coords in WGS84"

    # also available as crs._crs.to_cf()['grid_mapping_name']
    crs_var.grid_mapping_name = 'latitude_longitude'

    crs_var.longitude_of_prime_meridian = 0.0
    return crs_var


def _write_albers_params(crs_var, crs):
    # http://spatialreference.org/ref/epsg/gda94-australian-albers/html/
    # http://cfconventions.org/Data/cf-conventions/cf-conventions-1.7/build/cf-conventions.html#appendix-grid-mappings
    cf = crs._crs.to_cf()

    crs_var.grid_mapping_name = cf['grid_mapping_name']
    crs_var.standard_parallel = tuple(cf['standard_parallel'])
    crs_var.longitude_of_central_meridian = cf['longitude_of_central_meridian']
    crs_var.latitude_of_projection_origin = cf['latitude_of_projection_origin']


def _write_sinusoidal_params(crs_var, crs):
    cf = crs._crs.to_cf()

    crs_var.grid_mapping_name = cf['grid_mapping_name']
    crs_var.longitude_of_central_meridian = cf['longitude_of_projection_origin']


def _write_transverse_mercator_params(crs_var, crs):
    cf = crs._crs.to_cf()

    # http://spatialreference.org/ref/epsg/wgs-84-utm-zone-54s/
    crs_var.grid_mapping_name = cf['grid_mapping_name']
    crs_var.scale_factor_at_central_meridian = cf['scale_factor_at_central_meridian']
    crs_var.longitude_of_central_meridian = cf['longitude_of_central_meridian']
    crs_var.latitude_of_projection_origin = cf['latitude_of_projection_origin']


def _write_lcc2_params(crs_var, crs):
    cf = crs._crs.to_cf()

    # e.g. http://spatialreference.org/ref/sr-org/mexico-inegi-lambert-conformal-conic/
    crs_var.grid_mapping_name = cf['grid_mapping_name']
    crs_var.standard_parallel = cf['standard_parallel']
    crs_var.latitude_of_projection_origin = cf['latitude_of_projection_origin']
    crs_var.longitude_of_central_meridian = cf['longitude_of_central_meridian']
    crs_var.false_easting = cf['false_easting']
    crs_var.false_northing = cf['false_northing']
    crs_var.semi_major_axis = crs.semi_major_axis
    crs_var.semi_minor_axis = crs.semi_minor_axis


CRS_PARAM_WRITERS = {
    'albers_conic_equal_area': _write_albers_params,
    'albers_conical_equal_area': _write_albers_params,
    'sinusoidal': _write_sinusoidal_params,
    'transverse_mercator': _write_transverse_mercator_params,
    'lambert_conformal_conic_2sp': _write_lcc2_params,
    'lambert_conformal_conic': _write_lcc2_params,
}


def _create_projected_grid_mapping_variable(nco, crs, name=DEFAULT_GRID_MAPPING):
    cf = crs._crs.to_cf()
    grid_mapping_name = cf['grid_mapping_name']
    if grid_mapping_name not in CRS_PARAM_WRITERS:
        raise ValueError('{} CRS is not supported'.format(grid_mapping_name))

    crs_var = nco.createVariable(name, 'i4')
    CRS_PARAM_WRITERS[grid_mapping_name](crs_var, crs)

    crs_var.false_easting = cf['false_easting']
    crs_var.false_northing = cf['false_northing']
    crs_var.long_name = crs._crs.name

    return crs_var


def _write_geographical_extents_attributes(nco, extent):
    geo_extents = extent.to_crs(geometry.CRS("EPSG:4326"))
    nco.geospatial_bounds = geo_extents.wkt
    nco.geospatial_bounds_crs = "EPSG:4326"

    geo_bounds = geo_extents.boundingbox
    nco.geospatial_lat_min = geo_bounds.bottom
    nco.geospatial_lat_max = geo_bounds.top
    nco.geospatial_lat_units = "degrees_north"
    nco.geospatial_lon_min = geo_bounds.left
    nco.geospatial_lon_max = geo_bounds.right
    nco.geospatial_lon_units = "degrees_east"

    # TODO: broken anyway...
    # nco.geospatial_lat_resolution = "{} degrees".format(abs(geobox.affine.e))
    # nco.geospatial_lon_resolution = "{} degrees".format(abs(geobox.affine.a))


def create_grid_mapping_variable(nco, crs, name=DEFAULT_GRID_MAPPING):
    if crs.geographic:
        crs_var = _create_latlon_grid_mapping_variable(nco, crs, name)
    elif crs.projected:
        crs_var = _create_projected_grid_mapping_variable(nco, crs, name)
    else:
        raise ValueError('Unknown CRS')

    # mark crs variable as a coordinate
    coords = getattr(nco, 'coordinates', None)
    coords = [] if coords is None else coords.split(',')
    if name not in coords:
        coords.append(name)
    nco.coordinates = ','.join(coords)

    crs_var.semi_major_axis = crs.semi_major_axis
    crs_var.semi_minor_axis = crs.semi_minor_axis
    crs_var.inverse_flattening = crs.inverse_flattening
    crs_var.crs_wkt = crs.wkt

    crs_var.spatial_ref = crs.wkt

    dims = crs.dimensions
    xres, xoff = data_resolution_and_offset(nco[dims[1]])
    yres, yoff = data_resolution_and_offset(nco[dims[0]])
    crs_var.GeoTransform = [xoff, xres, 0.0, yoff, 0.0, yres]

    left, right = nco[dims[1]][0] - 0.5 * xres, nco[dims[1]][-1] + 0.5 * xres
    bottom, top = nco[dims[0]][0] - 0.5 * yres, nco[dims[0]][-1] + 0.5 * yres
    _write_geographical_extents_attributes(nco, geometry.box(left, bottom, right, top, crs=crs))

    return crs_var


def write_flag_definition(variable, flags_definition):
    # write bitflag info
    # Functions for this are stored in Measurements
    variable.QA_index = describe_flags_def(flags_def=flags_definition)
    variable.flag_masks, variable.valid_range, variable.flag_meanings = flag_mask_meanings(flags_def=flags_definition)


def netcdfy_coord(data):
    return netcdfy_data(data)


def netcdfy_data(data):
    # NetCDF/CF Conventions only seem to allow storing ascii, not unicode
    if data.dtype.kind == 'S' and data.dtype.itemsize > 1:
        return data.view('S1').reshape(data.shape + (-1,))
    if data.dtype.kind == 'M':
        return data.astype('<M8[s]').astype('double')
    else:
        return data


def flag_mask_meanings(flags_def):
    # Filter out any multi-bit mask values since we can't handle them yet
    flags_def = {k: v for k, v in flags_def.items() if isinstance(v['bits'], numbers.Integral)}
    max_bit = max([bit_def['bits'] for bit_def in flags_def.values()])

    if max_bit >= 32:
        # GDAL upto and including 2.0 can't support int64 attributes...
        raise RuntimeError('Bit index too high: %s' % max_bit)

    valid_range = numpy.array([0, (2 ** max_bit - 1) + 2 ** max_bit], dtype='int32')

    masks = []
    meanings = []

    def by_bits(i):
        _, v = i
        return v['bits']

    for name, bitdef in sorted(flags_def.items(), key=by_bits):
        try:
            true_value = bitdef['values'][1]

            if true_value is True:
                meaning = name
            elif true_value is False:
                meaning = 'no_' + name
            else:
                meaning = true_value

            masks.append(2 ** bitdef['bits'])
            meanings.append(str(meaning))
        except KeyError:
            continue

    return numpy.array(masks, dtype='int32'), valid_range, ' '.join(meanings)
