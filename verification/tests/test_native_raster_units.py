"""Unit labels inherit only from independently verified unchanged native values."""

import copy

import numpy as np
import pytest
import rasterio
from test_population import fixture, write_raster
from test_source_overlay import raster

from terra_bench.common import Blocked, sha
from terra_bench.overlay_grading import check_overlay_raster
from terra_bench.policy import authorize
from terra_bench.population_grading import check_population_raster


def test_people_is_a_count_unit_on_the_exact_original_grid(tmp_path):
    expected, _, grid = fixture(tmp_path)
    with np.load(tmp_path / expected["reference"]) as reference:
        selected = reference["selected"]
    path = tmp_path / "selected.tif"
    write_raster(path, selected, grid, unit="people")
    check_population_raster(path, selected, expected, "people per cell")
    for unit in ["people/km2", "thousand people", "percent"]:
        write_raster(path, selected, grid, unit=unit)
        with pytest.raises(Blocked):
            check_population_raster(path, selected, expected, "people per cell")


def test_unitless_lossless_overlay_copy_inherits_fixture_density_contract(tmp_path):
    source, actual = tmp_path / "source.tif", tmp_path / "actual.tif"
    raster(source)
    with rasterio.open(source, "r+") as ds:
        ds.set_band_unit(1, "")
    with rasterio.open(source) as ds:
        profile, values = ds.profile, ds.read(1)
    with rasterio.open(actual, "w", **{**profile, "compress": "deflate"}) as ds:
        ds.write(values, 1)
    assert sha(actual) != sha(source)
    check_overlay_raster(actual, source)
    with rasterio.open(actual, "r+") as ds:
        values[0, 1] += .00003  # Within ordinary comparison tolerance, but not a lossless copy.
        ds.write(values, 1)
    with pytest.raises(Blocked):
        check_overlay_raster(actual, source)


def test_overlay_band_copy_requires_declared_source_and_band():
    selection = {"collectionId": "density", "itemId": "one", "assetKey": "data"}
    inputs = {"bangladesh_density": selection,
              "bangladesh_railways": {"collectionId": "rail", "itemId": "one", "assetKey": "data"}}
    manifest = {"valid": True, "approvalDigest": "exact", "readiness": {"status": "ready"},
        "definition": {"nodes": [{"id": "band", "type": "processor", "processId": "raster-extract-band",
                                  "inputs": {"source": selection, "band": 1}}]}}
    authorize(manifest, "281727", inputs)
    for field, value in [("band", 2), ("source", inputs["bangladesh_railways"]),
                         ("area", {"bbox": [0, 0, 1, 1]})]:
        changed = copy.deepcopy(manifest)
        changed["definition"]["nodes"][0]["inputs"][field] = value
        with pytest.raises(Blocked):
            authorize(changed, "281727", inputs)
