# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
from datacube_sp.storage import BandInfo
from datacube_sp.testutils import mk_sample_dataset
from datacube_sp.storage._base import _get_band_and_layer


def test_band_layer():
    def t(band=None, layer=None):
        return _get_band_and_layer(dict(band=band, layer=layer))

    assert t() == (None, None)
    assert t(1) == (1, None)
    assert t(None, 3) == (3, None)
    assert t(1, 'foo') == (1, 'foo')
    assert t(None, 'foo') == (None, 'foo')

    bad_inputs = [('string', None),  # band has to be int|None
                  (None, {}),  # layer has to be int|str|None
                  (1, 3)]  # if band is set layer should be str|None

    for bad in bad_inputs:
        with pytest.raises(ValueError):
            t(*bad)


def test_band_info():
    bands = [dict(name=n,
                  dtype='uint8',
                  units='K',
                  nodata=33,
                  path=n+'.tiff')
             for n in 'a b c'.split(' ')]

    ds = mk_sample_dataset(bands,
                           uri='file:///tmp/datataset.yml',
                           format='GeoTIFF')

    binfo = BandInfo(ds, 'b')
    assert binfo.name == 'b'
    assert binfo.band is None
    assert binfo.layer is None
    assert binfo.dtype == 'uint8'
    assert binfo.transform is None
    assert binfo.crs is None
    assert binfo.units == 'K'
    assert binfo.nodata == 33
    assert binfo.uri == 'file:///tmp/b.tiff'
    assert binfo.format == ds.format
    assert binfo.driver_data is None
    assert binfo.uri_scheme == 'file'

    with pytest.raises(ValueError):
        BandInfo(ds, 'no_such_band')

    # Check case where dataset is missing band that is present in the product
    del ds.metadata_doc['image']['bands']['c']
    with pytest.raises(ValueError):
        BandInfo(ds, 'c')

    ds.uris = []
    with pytest.raises(ValueError):
        BandInfo(ds, 'a')

    ds.uris = None
    with pytest.raises(ValueError):
        BandInfo(ds, 'a')

    ds_none_fmt = mk_sample_dataset(bands,
                                    uri='file:///tmp/datataset.yml',
                                    format=None)
    assert ds_none_fmt.format is None
    assert BandInfo(ds_none_fmt, 'a').format == ''

    ds = mk_sample_dataset(bands, uri='/not/a/uri')
    band = BandInfo(ds, 'a')
    assert band.uri_scheme is ''  # noqa: F632


def test_band_info_with_url_mangling():
    def url_mangler(raw):
        return raw.replace("tmp", "tmp/mangled")

    bands = [dict(name=n,
                  dtype='uint8',
                  units='K',
                  nodata=33,
                  path=n+'.tiff')
             for n in 'a b c'.split(' ')]

    ds = mk_sample_dataset(bands,
                           uri='file:///tmp/datataset.yml',
                           format='GeoTIFF')

    binfo = BandInfo(ds, 'b', patch_url=url_mangler)
    assert binfo.name == 'b'
    assert binfo.uri == 'file:///tmp/mangled/b.tiff'
