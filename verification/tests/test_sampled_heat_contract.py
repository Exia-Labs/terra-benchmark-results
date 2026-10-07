"""Native-cell population samples keep their meaning through a named output field."""

import copy

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from terra_bench.common import Blocked, sha
from terra_bench.heat_grading import check_heat_values
from terra_bench.heat_tasks import GRID, RADIUS_M
from terra_bench.policy import authorize


def proposal():
    inputs = {k: {"collectionId": k, "itemId": "one", "assetKey": "data"}
              for k in ("earthquakes", "us_population")}
    nodes = [
        {"id": "sample", "type": "processor", "processId": "raster-sample", "inputs": {
            "features": inputs["earthquakes"], "rasters": {"measured": inputs["us_population"]},
            "bands": {"measured": 1}, "area": {"bbox": [-180, -85, 180, 85]}}},
        {"id": "eligible", "type": "processor", "processId": "vector-filter", "inputs": {
            "source": {"$output": {"nodeId": "sample"}},
            "predicates": [{"field": "measured", "operator": "gte", "value": 0}]}},
        {"id": "heat", "type": "processor", "processId": "point-density", "inputs": {
            "source": {"$output": {"nodeId": "eligible"}}, "weightField": "measured",
            "weightUnit": "people per source cell", "grid": GRID, "radiusM": RADIUS_M}},
    ]
    return {"valid": True, "readiness": {"status": "ready"}, "approvalDigest": "exact",
            "definition": {"nodes": nodes}}, inputs


def test_full_point_extent_and_native_sample_alias_are_not_changed_scope():
    manifest, inputs = proposal()
    original = copy.deepcopy(manifest)
    result = authorize(manifest, "367674", inputs, fixture_bounds={"earthquakes": [-179, -73, 179, 83]})
    assert result["approvalDigest"] == "exact"
    assert manifest == original


def test_native_sample_alias_without_area():
    manifest, inputs = proposal()
    manifest["definition"]["nodes"][0]["inputs"].pop("area")
    authorize(manifest, "367674", inputs)


@pytest.mark.parametrize("defect", ["crop", "crs", "bounds_missing", "band", "raster", "alias", "scaled", "density_unit"])
def test_native_sampling_proof_rejects_changed_work(defect):
    manifest, inputs = proposal()
    bounds = {"earthquakes": [-179, -73, 179, 83]}
    sample, eligible, heat = manifest["definition"]["nodes"]
    if defect == "crop":
        sample["inputs"]["area"]["bbox"] = [-120, -50, 120, 50]
    elif defect == "crs":
        sample["inputs"]["area"]["crs"] = "EPSG:3857"
    elif defect == "bounds_missing":
        bounds = {}
    elif defect == "band":
        sample["inputs"]["bands"]["measured"] = 2
    elif defect == "raster":
        sample["inputs"]["rasters"]["measured"] = inputs["earthquakes"]
    elif defect == "alias":
        heat["inputs"]["weightField"] = "not_sampled"
    elif defect == "scaled":
        manifest["definition"]["nodes"].insert(2, {"id": "scaled", "type": "processor",
            "processId": "vector-field-calculate", "inputs": {"source": {"$output": {"nodeId": "eligible"}},
                "calculations": [{"outputField": "measured", "expression": "v*2", "fields": {"v": "measured"}}]}})
        heat["inputs"]["source"] = {"$output": {"nodeId": "scaled"}}
    else:
        heat["inputs"]["weightUnit"] = "people/km2"
    with pytest.raises(Blocked):
        authorize(manifest, "367674", inputs, fixture_bounds=bounds)


def test_sample_count_label_needs_native_context_and_exact_numeric_check(tmp_path):
    values = np.array([[1., 0.], [0., 2.]])
    reference = tmp_path / "reference.npz"
    np.savez_compressed(reference, values=values)
    expected = {"reference": reference.name, "referenceSha256": sha(reference),
                "grid": {"bounds": [0, 0, 2, 2], "crs": "EPSG:3857"},
                "unit": "sum of people per grid cell", "tolerance": {"absolute": 1e-7, "relative": 1e-6}}
    path = tmp_path / "result.tif"
    def save(unit="sum of people per source cell per grid cell", data=values):
        with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1,
                           dtype="float32", crs="EPSG:3857", transform=from_bounds(0, 0, 2, 2, 2, 2)) as ds:
            ds.write(data.astype("float32"), 1)
            ds.set_band_unit(1, unit)
    save()
    with pytest.raises(Blocked, match="units"):
        check_heat_values(path, expected, tmp_path)
    check_heat_values(path, expected, tmp_path, native_count_samples=True)
    save(data=values * 2)
    with pytest.raises(Blocked, match="pixel"):
        check_heat_values(path, expected, tmp_path, native_count_samples=True)
    save(unit="people/km2")
    with pytest.raises(Blocked, match="units"):
        check_heat_values(path, expected, tmp_path, native_count_samples=True)
