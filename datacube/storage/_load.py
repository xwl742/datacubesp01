# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Important functions are:

* :func:`reproject_and_fuse`

"""
import logging
from collections import OrderedDict
import numpy as np
from xarray.core.dataarray import DataArray as XrDataArray, DataArrayCoordinates
from xarray.core.dataset import Dataset as XrDataset
from typing import (
    Union, Optional, Callable,
    List, Any, Iterator, Iterable, Mapping, Tuple, Hashable, cast
)

from datacube.utils import ignore_exceptions_if
from datacube.utils.math import invalid_mask
from datacube.utils.geometry import GeoBox, roi_is_empty
from datacube.model import Measurement
from datacube.drivers._types import ReaderDriver
from ..drivers.datasource import DataSource
from ._base import BandInfo
from ._rio import RasterDataSourceforGDAL

_LOG = logging.getLogger(__name__)

FuserFunction = Callable[[np.ndarray, np.ndarray], Any]  # pylint: disable=invalid-name
ProgressFunction = Callable[[int, int], Any]  # pylint: disable=invalid-name


def _default_fuser(dst: np.ndarray, src: np.ndarray, dst_nodata) -> None:
    """ Overwrite only those pixels in `dst` with `src` that are "not valid"

        For every pixel in dst that equals to dst_nodata replace it with pixel
        from src.
    """
    np.copyto(dst, src, where=invalid_mask(dst, dst_nodata))


def reproject_and_fuse(datasources: List[DataSource],
                       destination: np.ndarray,
                       dst_gbox: GeoBox,
                       dst_nodata: Optional[Union[int, float]],
                       resampling: str = 'nearest',
                       fuse_func: Optional[FuserFunction] = None,
                       skip_broken_datasets: bool = False,
                       progress_cbk: Optional[ProgressFunction] = None,
                       extra_dim_index: Optional[int] = None):
    """
    Reproject and fuse `sources` into a 2D numpy array `destination`.

    :param datasources: Data sources to open and read from
    :param destination: ndarray of appropriate size to read data into
    :param dst_gbox: GeoBox defining destination region
    :param skip_broken_datasets: Carry on in the face of adversity and failing reads.
    :param progress_cbk: If supplied will be called with 2 integers `Items processed, Total Items`
                         after reading each file.
    """
    # pylint: disable=too-many-locals
    from ._read import read_time_slice, read_time_slice_sp
    assert len(destination.shape) == 2

    def copyto_fuser(dest: np.ndarray, src: np.ndarray) -> None:
        _default_fuser(dest, src, dst_nodata)

    fuse_func = fuse_func or copyto_fuser

    destination.fill(dst_nodata)
    if len(datasources) == 0:
        return destination
    elif len(datasources) == 1:
        with ignore_exceptions_if(skip_broken_datasets):
            if isinstance(datasources[0], RasterDataSourceforGDAL):
                read_time_slice_sp(datasources[0], destination, dst_gbox, resampling, dst_nodata, extra_dim_index)
            else:
                with datasources[0].open() as rdr:
                    read_time_slice(rdr, destination, dst_gbox, resampling, dst_nodata, extra_dim_index)

        if progress_cbk:
            progress_cbk(1, 1)

        return destination
    else:
        # Multiple sources, we need to fuse them together into a single array
        buffer_ = np.full(destination.shape, dst_nodata, dtype=destination.dtype)
        for n_so_far, source in enumerate(datasources, 1):
            with ignore_exceptions_if(skip_broken_datasets):
                with source.open() as rdr:
                    roi = read_time_slice(rdr, buffer_, dst_gbox, resampling, dst_nodata, extra_dim_index)

                if not roi_is_empty(roi):
                    fuse_func(destination[roi], buffer_[roi])
                    buffer_[roi] = dst_nodata  # clean up for next read

            if progress_cbk:
                progress_cbk(n_so_far, len(datasources))

        return destination


def _mk_empty_ds(coords: DataArrayCoordinates, geobox: GeoBox) -> XrDataset:
    cc = OrderedDict(coords.items())
    cc.update(geobox.xr_coords())
    return XrDataset(coords=cast(Mapping[Hashable, Any], cc), attrs={'crs': geobox.crs})


def _allocate_storage(coords: DataArrayCoordinates,
                      geobox: GeoBox,
                      measurements: Iterable[Measurement]) -> XrDataset:
    xx = _mk_empty_ds(coords, geobox)
    dims = list(xx.coords.keys())
    shape = tuple(xx.sizes[k] for k in dims)

    for m in measurements:
        name, dtype, attrs = m.name, m.dtype, m.dataarray_attrs()
        attrs['crs'] = geobox.crs
        data = np.empty(shape, dtype=dtype)
        xx[name] = XrDataArray(data, coords=xx.coords, dims=dims, name=name, attrs=attrs)

    return xx


def xr_load(sources: XrDataArray,
            geobox: GeoBox,
            measurements: List[Measurement],
            driver: ReaderDriver,
            driver_ctx_prev: Optional[Any] = None,
            skip_broken_datasets: bool = False) -> Tuple[XrDataset, Any]:
    # pylint: disable=too-many-locals
    from ._read import read_time_slice_v2

    out = _allocate_storage(sources.coords, geobox, measurements)

    def all_groups() -> Iterator[Tuple[Measurement, Tuple[int, ...], List[BandInfo]]]:
        for idx, dss in np.ndenumerate(sources.values):
            for m in measurements:
                bbi = [BandInfo(ds, m.name) for ds in dss]
                yield (m, idx, bbi)

    def just_bands(groups) -> Iterator[BandInfo]:
        for _, _, bbi in groups:
            yield from bbi

    groups = list(all_groups())
    ctx = driver.new_load_context(just_bands(groups), driver_ctx_prev)

    # TODO: run upto N concurrently
    for m, idx, bbi in groups:
        dst = out.data_vars[m.name].values[idx]
        dst[:] = m.nodata
        resampling = m.get('resampling_method', 'nearest')
        fuse_func = m.get('fuser', None)

        for band in bbi:
            rdr = driver.open(band, ctx).result()

            pix, roi = read_time_slice_v2(rdr, geobox, resampling, m.nodata)

            if pix is not None:
                if fuse_func:
                    fuse_func(dst[roi], pix)
                else:
                    _default_fuser(dst[roi], pix, m.nodata)

    return out, ctx
