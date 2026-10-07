import copy

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from terra_bench.common import ROOT, Blocked, read
from terra_bench.contour_oracles import cell_segments, check_contours, contour_answer, same_segments
from terra_bench.contour_tasks import CONTOUR_TASKS
from terra_bench.policy import authorize
from terra_bench.tasks import protocol_for


def test_plane_positions_pixel_centers_masks_and_saddle_topology():
    values = np.array([[0.0, 2], [0, 2]])
    valid = np.ones((2, 2), bool)
    np.testing.assert_allclose(cell_segments(values, valid, 1), [[[1, 0.5], [1, 1.5]]])
    valid[0, 0] = False
    assert len(cell_segments(values, valid, 1)) == 0
    saddle = cell_segments(np.array([[2.0, 0], [0, 2]]), np.ones((2, 2), bool), 1)
    assert same_segments(saddle, np.array([[[1, 0.5], [0.5, 1]], [[1.5, 1], [1, 1.5]]]))
    assert len(cell_segments(np.ones((2, 2)), np.ones((2, 2), bool), 1)) == 0


def test_geometry_check_allows_order_orientation_densification_but_no_loss_or_duplicates():
    expected = np.array([[[0.0, 0], [1, 0]], [[1, 0], [2, 0]], [[2, 0], [2, 1]]])
    assert same_segments(expected[::-1, ::-1], expected)
    assert same_segments(np.array([[[0.0, 0], [2, 0]], [[2, 0], [2, 0.5]], [[2, 0.5], [2, 1]]]), expected)
    assert not same_segments(expected[:-1], expected)
    assert not same_segments(np.concatenate([expected, expected[:1]]), expected)
    assert not same_segments(expected + [0, 0.001], expected)
    assert not same_segments(np.array([[[0.0, 0], [2, 1]]]), expected)
    assert same_segments(np.empty((0, 2, 2)), np.empty((0, 2, 2)))


def test_saved_reference_and_grade_reject_wrong_level_mask_and_checksums(tmp_path, monkeypatch):
    from terra_bench import contour_oracles

    spec = {"raster": "grid", "levels": [1.0, 3.0], "unit": "inches"}
    monkeypatch.setitem(contour_oracles.CONTOUR_TASKS, "test", spec)
    transform = from_origin(10, 20, 2, 2)
    with rasterio.open(
        tmp_path / "grid.tif",
        "w",
        driver="GTiff",
        count=1,
        dtype="float64",
        width=2,
        height=2,
        crs="EPSG:4326",
        transform=transform,
        nodata=-999,
    ) as out:
        out.write(np.array([[0.0, 2], [0, 2]]), 1)
    expected = contour_answer(tmp_path, "test", {"grid": {"path": "grid.tif"}})
    assert expected["count"] == 1 and expected["unknownCount"] == 0
    frame = gpd.GeoDataFrame(
        {"level": [1.0]}, geometry=[LineString([transform * (1, 0.5), transform * (1, 1.5)])], crs=4326
    )
    claim = {"level_field": "level", "feature_count": 1, "count": 1, "unknown_count": 0}
    check_contours(frame, claim, expected, tmp_path)
    with pytest.raises(Blocked, match="missing-pixel"):
        check_contours(frame, {**claim, "unknown_count": 1}, expected, tmp_path)
    with pytest.raises(Blocked, match="levels"):
        check_contours(frame.assign(level=2.0), claim, expected, tmp_path)
    with pytest.raises(Blocked, match="reference changed"):
        check_contours(frame, claim, {**expected, "referenceSha256": "wrong"}, tmp_path)


def test_protocol_matches_original_questions_and_policy_refuses_changed_levels():
    originals = {
        t["task_ID"].rsplit("_", 1)[-1]: t["task_text"]
        for t in read(ROOT / "data/upstream/benchmark_set/tasks_and_reference_solutions.json")["tasks"]
    }
    for task, spec in CONTOUR_TASKS.items():
        assert protocol_for([task])["tasks"][task]["question"] == originals[task]
        inputs = {spec["raster"]: {"collectionId": "source", "itemId": "item", "assetKey": "data"}}
        node = {
            "id": "contour",
            "type": "processor",
            "processId": "raster-contours",
            "inputs": {
                "source": inputs[spec["raster"]],
                "levels": spec["levels"],
                "unit": spec["unit"],
                "band": 1,
            },
        }
        manifest = {
            "valid": True,
            "approvalDigest": "unchanged",
            "readiness": {"status": "ready"},
            "definition": {"nodes": [node]},
        }
        if spec.get("floodMask"):
            inputs[spec["floodMask"]] = {"collectionId": "flood", "itemId": "item", "assetKey": "data"}
            mask = {"id": "mask", "type": "processor", "processId": "raster-map-algebra", "inputs": {"sources": {"population": inputs[spec["raster"]], "flood": inputs[spec["floodMask"]]}, "expression": "where(flood == 1, population, -9999)"}}
            node["inputs"]["source"] = {"$output": {"nodeId": "mask"}}
            manifest["definition"]["nodes"].append(mask)
        assert authorize(manifest, task, inputs)["approvalDigest"] == "unchanged"
        bad = copy.deepcopy(manifest)
        bad["definition"]["nodes"][0]["inputs"]["levels"] = [1]
        with pytest.raises(Blocked, match="levels"):
            authorize(bad, task, inputs)


def test_overlay_sampling_is_allowed_only_for_declared_raster_and_band():
    task = "251255"
    spec = CONTOUR_TASKS[task]
    inputs = {
        k: {"collectionId": k, "itemId": "one", "assetKey": "data"} for k in (spec["raster"], spec["overlay"])
    }
    settings = {
        "features": inputs[spec["overlay"]],
        "rasters": {"value": inputs[spec["raster"]]},
        "bands": {"value": 1},
    }
    manifest = {
        "valid": True,
        "approvalDigest": "exact",
        "readiness": {"status": "ready"},
        "definition": {
            "nodes": [{"id": "sample", "type": "processor", "processId": "raster-sample", "inputs": settings}]
        },
    }
    authorize(manifest, task, inputs)
    settings["bands"]["value"] = 2
    with pytest.raises(Blocked, match="declared band"):
        authorize(manifest, task, inputs)
