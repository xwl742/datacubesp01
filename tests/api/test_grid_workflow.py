# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
import numpy
from datacube_sp.api.grid_workflow import GridWorkflow
from datacube_sp.model import GridSpec
from datacube_sp.utils import geometry
from unittest.mock import MagicMock
from datacube_sp.testutils import mk_sample_product
import datetime
import uuid


class PickableMock(MagicMock):
    def __reduce__(self):
        return (MagicMock, ())


def mk_fake_index(products, datasets):
    fakeindex = PickableMock()
    fakeindex._db = None

    fakeindex.products.get_by_name = lambda name: products.get(name, None)

    fakeindex.datasets.get_field_names.return_value = ["time"]  # permit query on time
    fakeindex.datasets.search_eager.return_value = datasets

    return fakeindex


@pytest.fixture(scope="session")
def fake_index():
    return mk_fake_index(
        products=dict(
            with_gs=mk_sample_product("with_gs", with_grid_spec=True),
            without_gs=mk_sample_product("without_gs", with_grid_spec=False),
        ),
        datasets=[],
    )


def test_create_gridworkflow_init_failures(fake_index):
    index = fake_index

    # need product or grispec
    with pytest.raises(ValueError):
        GridWorkflow(index)

    # test missing product
    with pytest.raises(ValueError):
        GridWorkflow(index, product="no-such-product")

    # test missing product
    assert fake_index.products.get_by_name("without_gs") is not None
    assert fake_index.products.get_by_name("without_gs").grid_spec is None

    with pytest.raises(ValueError):
        GridWorkflow(index, product="without_gs")

    product = fake_index.products.get_by_name("with_gs")
    assert product is not None
    assert product.grid_spec is not None
    gw = GridWorkflow(index, product="with_gs")
    assert gw.grid_spec is product.grid_spec


def test_gridworkflow():
    """Test GridWorkflow with padding option."""

    # ----- fake a datacube_sp -----
    # e.g. let there be a dataset that coincides with a grid cell

    fakecrs = geometry.CRS("EPSG:4326")

    grid = 100  # spatial frequency in crs units
    pixel = 10  # square pixel linear dimension in crs units
    # if cell(0,0) has lower left corner at grid origin,
    # and cell indices increase toward upper right,
    # then this will be cell(1,-2).
    gridspec = GridSpec(
        crs=fakecrs, tile_size=(grid, grid), resolution=(-pixel, pixel)
    )  # e.g. product gridspec

    fakedataset = MagicMock()
    fakedataset.extent = geometry.box(
        left=grid, bottom=-grid, right=2 * grid, top=-2 * grid, crs=fakecrs
    )
    fakedataset.center_time = t = datetime.datetime(2001, 2, 15)
    fakedataset.id = uuid.uuid4()

    fakeindex = PickableMock()
    fakeindex._db = None
    fakeindex.datasets.get_field_names.return_value = ["time"]  # permit query on time
    fakeindex.datasets.search_eager.return_value = [fakedataset]

    # ------ test without padding ----

    gw = GridWorkflow(fakeindex, gridspec)

    # smoke test str/repr
    assert len(str(gw)) > 0
    assert len(repr(gw)) > 0

    # Need to force the fake index otherwise the driver manager will
    # only take its _db
    gw.index = fakeindex
    query = dict(
        product="fake_product_name", time=("2001-1-1 00:00:00", "2001-3-31 23:59:59")
    )

    # test backend : that it finds the expected cell/dataset
    assert list(gw.cell_observations(**query).keys()) == [(1, -2)]

    # again but with geopolygon
    assert list(
        gw.cell_observations(
            **query, geopolygon=gridspec.tile_geobox((1, -2)).extent
        ).keys()
    ) == [(1, -2)]

    with pytest.raises(ValueError) as e:
        list(
            gw.cell_observations(
                **query,
                tile_buffer=(1, 1),
                geopolygon=gridspec.tile_geobox((1, -2)).extent
            ).keys()
        )
    assert str(e.value) == "Cannot process tile_buffering and geopolygon together."

    # test frontend
    assert len(gw.list_tiles(**query)) == 1

    # ------ introduce padding --------

    assert len(gw.list_tiles(tile_buffer=(20, 20), **query)) == 9

    # ------ add another dataset (to test grouping) -----

    # consider cell (2,-2)
    fakedataset2 = MagicMock()
    fakedataset2.extent = geometry.box(
        left=2 * grid, bottom=-grid, right=3 * grid, top=-2 * grid, crs=fakecrs
    )
    fakedataset2.center_time = t
    fakedataset2.id = uuid.uuid4()

    def search_eager(lat=None, lon=None, **kwargs):
        return [fakedataset, fakedataset2]

    fakeindex.datasets.search_eager = search_eager

    # unpadded
    assert len(gw.list_tiles(**query)) == 2
    ti = numpy.datetime64(t, "ns")
    assert set(gw.list_tiles(**query).keys()) == {(1, -2, ti), (2, -2, ti)}

    # padded
    assert (
        len(gw.list_tiles(tile_buffer=(20, 20), **query)) == 12
    )  # not 18=2*9 because of grouping

    # -------- inspect particular returned tile objects --------

    # check the array shape

    tile = gw.list_tiles(**query)[1, -2, ti]  # unpadded example
    assert grid / pixel == 10
    assert tile.shape == (1, 10, 10)

    # smoke test str/repr
    assert len(str(tile)) > 0
    assert len(repr(tile)) > 0

    padded_tile = gw.list_tiles(tile_buffer=(20, 20), **query)[
        1, -2, ti
    ]  # padded example
    # assert grid/pixel + 2*gw2.grid_spec.padding == 14  # GREG: understand this
    assert padded_tile.shape == (1, 14, 14)

    # count the sources

    assert len(tile.sources.isel(time=0).item()) == 1
    assert len(padded_tile.sources.isel(time=0).item()) == 2

    # check the geocoding

    assert tile.geobox.alignment == padded_tile.geobox.alignment
    assert tile.geobox.affine * (0, 0) == padded_tile.geobox.affine * (2, 2)
    assert tile.geobox.affine * (10, 10) == padded_tile.geobox.affine * (10 + 2, 10 + 2)

    # ------- check loading --------
    # GridWorkflow accesses the load_data API
    # to ultimately convert geobox,sources,measurements to xarray,
    # so only thing to check here is the call interface.

    measurement = dict(nodata=0, dtype=numpy.int)
    fakedataset.product.lookup_measurements.return_value = {"dummy": measurement}
    fakedataset2.product = fakedataset.product

    from unittest.mock import patch

    with patch("datacube_sp.api.core.Datacube.load_data") as loader:

        data = GridWorkflow.load(tile)
        data2 = GridWorkflow.load(padded_tile)
        # Note, could also test Datacube.load for consistency (but may require more patching)

    assert data is data2 is loader.return_value
    assert loader.call_count == 2

    # Note, use of positional arguments here is not robust, could spec mock etc.
    for (args, kwargs), loadable in zip(loader.call_args_list, [tile, padded_tile]):
        args = list(args)
        assert args[0] is loadable.sources
        assert args[1] is loadable.geobox
        assert list(args[2].values())[0] is measurement
        assert "resampling" in kwargs

    # ------- check single cell index extract -------
    tile = gw.list_tiles(cell_index=(1, -2), **query)
    assert len(tile) == 1
    assert tile[1, -2, ti].shape == (1, 10, 10)
    assert len(tile[1, -2, ti].sources.values[0]) == 1

    padded_tile = gw.list_tiles(cell_index=(1, -2), tile_buffer=(20, 20), **query)
    assert len(padded_tile) == 1
    assert padded_tile[1, -2, ti].shape == (1, 14, 14)
    assert len(padded_tile[1, -2, ti].sources.values[0]) == 2

    # query without product is not allowed
    with pytest.raises(RuntimeError):
        gw.list_cells(cell_index=(1, -2), time=query["time"])


def test_gridworkflow_with_time_depth():
    """Test GridWorkflow with time series.
    Also test `Tile` methods `split` and `split_by_time`
    """
    fakecrs = geometry.CRS("EPSG:4326")

    grid = 100  # spatial frequency in crs units
    pixel = 10  # square pixel linear dimension in crs units
    # if cell(0,0) has lower left corner at grid origin,
    # and cell indices increase toward upper right,
    # then this will be cell(1,-2).
    gridspec = GridSpec(
        crs=fakecrs, tile_size=(grid, grid), resolution=(-pixel, pixel)
    )  # e.g. product gridspec

    def make_fake_datasets(num_datasets):
        start_time = datetime.datetime(2001, 2, 15)
        delta = datetime.timedelta(days=16)
        for i in range(num_datasets):
            fakedataset = MagicMock()
            fakedataset.extent = geometry.box(
                left=grid, bottom=-grid, right=2 * grid, top=-2 * grid, crs=fakecrs
            )
            fakedataset.center_time = start_time + (delta * i)
            yield fakedataset

    fakeindex = PickableMock()
    fakeindex.datasets.get_field_names.return_value = ["time"]  # permit query on time
    fakeindex.datasets.search_eager.return_value = list(make_fake_datasets(100))

    # ------ test with time dimension ----

    gw = GridWorkflow(fakeindex, gridspec)
    query = dict(product="fake_product_name")

    cells = gw.list_cells(**query)
    for cell_index, cell in cells.items():

        #  test Tile.split()
        for label, tile in cell.split("time"):
            assert tile.shape == (1, 10, 10)

        #  test Tile.split_by_time()
        for year, year_cell in cell.split_by_time(freq="A"):
            for t in year_cell.sources.time.values:
                assert str(t)[:4] == year
