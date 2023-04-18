# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
""" reader
"""
from typing import (
    List, Optional, Union, Any, Iterable,
    Tuple, NamedTuple, TypeVar
)
import numpy as np
from affine import Affine
from concurrent.futures import ThreadPoolExecutor
import rasterio                         # type: ignore[import]
from rasterio.io import DatasetReader   # type: ignore[import]
import rasterio.crs                     # type: ignore[import]

from datacube_sp.storage import BandInfo
from datacube_sp.utils.geometry import CRS
from datacube_sp.utils import (
    uri_to_local_path,
    get_part_from_uri,
)
from datacube_sp.drivers._types import (
    ReaderDriverEntry,
    ReaderDriver,
    GeoRasterReader,
    FutureGeoRasterReader,
    FutureNdarray,
    RasterShape,
    RasterWindow,
)

Overrides = NamedTuple('Overrides', [('crs', Optional[CRS]),
                                     ('transform', Optional[Affine]),
                                     ('nodata', Optional[Union[float, int]])])

RioWindow = Tuple[Tuple[int, int], Tuple[int, int]]  # pylint: disable=invalid-name
T = TypeVar('T')


def pick(a: Optional[T], b: Optional[T]) -> Optional[T]:
    """ Return first non-None value or None if all are None
    """
    return b if a is None else a


def _is_netcdf(fmt: str) -> bool:
    return fmt == 'NetCDF'


def _roi_to_window(roi: Optional[RasterWindow], shape: RasterShape) -> Optional[RioWindow]:
    if roi is None:
        return None

    def s2t(s: slice, n: int) -> Tuple[int, int]:
        _in = 0 if s.start is None else s.start
        _out = n if s.stop is None else s.stop

        if _in < 0:
            _in += n
        if _out < 0:
            _out += n

        return (_in, _out)

    s1, s2 = (s2t(s, n)
              for s, n in zip(roi, shape))
    return (s1, s2)


def _dc_crs(crs: Optional[rasterio.crs.CRS]) -> Optional[CRS]:
    """ Convert RIO version of CRS to datacube_sp
    """
    if crs is None:
        return None

    if not crs.is_valid:
        return None

    if crs.is_epsg_code:
        return CRS('epsg:{}'.format(crs.to_epsg()))
    return CRS(crs.wkt)


def _read(src: DatasetReader,
          bidx: int,
          window: Optional[RasterWindow],
          out_shape: Optional[RasterShape]) -> np.ndarray:
    return src.read(bidx,
                    window=_roi_to_window(window, src.shape),
                    out_shape=out_shape)


def _rio_uri(band: BandInfo) -> str:
    """
    - file uris are converted to file names
       - if also netcdf wrap in NETCDF:"${filename}":${layer}
    - All other protocols go through unmodified
    """
    if band.uri_scheme == 'file':
        fname = str(uri_to_local_path(band.uri))

        if _is_netcdf(band.format):
            fname = 'NETCDF:"{}":{}'.format(fname, band.layer)

        return fname

    return band.uri


def _rio_band_idx(band: BandInfo, src: DatasetReader) -> int:
    if band.band is not None:
        return band.band

    if not _is_netcdf(band.format):
        return 1

    bidx = get_part_from_uri(band.uri)
    if bidx is not None:
        return bidx

    if src.count == 1:  # Single-slice netcdf file
        return 1

    raise DeprecationWarning("Stacked netcdf without explicit time index is not supported anymore")


class RIOReader(GeoRasterReader):
    def __init__(self,
                 src: DatasetReader,
                 band_idx: int,
                 pool: ThreadPoolExecutor,
                 overrides: Overrides = Overrides(None, None, None)):

        transform = pick(overrides.transform, src.transform)
        if transform is not None and transform.is_identity:
            transform = None

        self._src = src
        self._crs = overrides.crs or _dc_crs(src.crs)
        self._transform = transform
        self._nodata = pick(overrides.nodata, src.nodatavals[band_idx-1])
        self._band_idx = band_idx
        self._dtype = src.dtypes[band_idx-1]
        self._pool = pool

    @property
    def crs(self) -> Optional[CRS]:
        return self._crs

    @property
    def transform(self) -> Optional[Affine]:
        return self._transform

    @property
    def dtype(self) -> np.dtype:
        return np.dtype(self._dtype)

    @property
    def shape(self) -> RasterShape:
        return self._src.shape

    @property
    def nodata(self) -> Optional[Union[int, float]]:
        return self._nodata

    def read(self,
             window: Optional[RasterWindow] = None,
             out_shape: Optional[RasterShape] = None) -> FutureNdarray:
        return self._pool.submit(_read, self._src, self._band_idx, window, out_shape)


def _compute_overrides(src: DatasetReader, bi: BandInfo) -> Overrides:
    """ If dataset is missing nodata, crs or transform.
    """
    crs, transform, nodata = None, None, None

    if src.crs is None or not src.crs.is_valid:
        crs = bi.crs

    if src.transform.is_identity:
        transform = bi.transform

    if src.nodata is None:
        nodata = bi.nodata

    return Overrides(crs=crs, transform=transform, nodata=nodata)


def _rdr_open(band: BandInfo, ctx: Any, pool: ThreadPoolExecutor) -> RIOReader:
    """ Open file pointed by BandInfo and return RIOReader instance.

        raises Exception on failure

        TODO: start using ctx for handle cache
    """
    normalised_uri = _rio_uri(band)
    src = rasterio.open(normalised_uri, 'r')
    bidx = _rio_band_idx(band, src)

    return RIOReader(src, bidx, pool, _compute_overrides(src, band))


class RIORdrDriver(ReaderDriver):
    def __init__(self, pool: ThreadPoolExecutor, cfg: dict):
        self._pool = pool
        self._cfg = cfg

    def new_load_context(self,
                         bands: Iterable[BandInfo],
                         old_ctx: Optional[Any]) -> Any:
        return None  # TODO: implement file handle cache with this

    def open(self, band: BandInfo, ctx: Any) -> FutureGeoRasterReader:
        return self._pool.submit(_rdr_open, band, ctx, self._pool)


class RDEntry(ReaderDriverEntry):
    PROTOCOLS = ['file', 'http', 'https', 's3', 'ftp', 'zip']
    FORMATS = ['GeoTIFF', 'NetCDF', 'JPEG2000']

    @property
    def protocols(self) -> List[str]:
        return RDEntry.PROTOCOLS

    @property
    def formats(self) -> List[str]:
        return RDEntry.FORMATS

    def supports(self, protocol: str, fmt: str) -> bool:
        # TODO: might need better support matrix structures

        if fmt == 'NetCDF':
            return protocol == 'file'

        return True

    def new_instance(self, cfg: dict) -> ReaderDriver:
        cfg = cfg.copy()
        pool = cfg.pop('pool', None)
        if pool is None:
            max_workers = cfg.pop('max_workers', 1)
            pool = ThreadPoolExecutor(max_workers=max_workers)
        elif not isinstance(pool, ThreadPoolExecutor):
            if not cfg.pop('allow_custom_pool', False):
                raise ValueError("External `pool` should be a `ThreadPoolExecutor`")

        return RIORdrDriver(pool, cfg)
