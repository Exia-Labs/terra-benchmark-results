import json
from copy import deepcopy

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from terra_bench.common import Blocked, sha
from terra_bench.overlay_grading import check_overlay_raster, grade_overlay, overlay_answer
from terra_bench.tasks import protocol_for


def raster(path, values=None, unit="people/km²"):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(89, 26, 0.01, 0.01),
        nodata=-9999,
    ) as ds:
        ds.write(np.array(values if values is not None else [[0, 500], [-9999, 20]], dtype="float32"), 1)
        ds.set_band_unit(1, unit)


def test_raster_values_masks_zeros_and_units(tmp_path):
    source = tmp_path / "source.tif"
    actual = tmp_path / "actual.tif"
    raster(source)
    raster(actual)
    check_overlay_raster(actual, source)
    for values, unit in [
        ([[0, 500], [0, 20]], "people/km²"),
        ([[0, 501], [-9999, 20]], "people/km²"),
        (None, "people per cell"),
    ]:
        raster(actual, values, unit)
        with pytest.raises(Blocked):
            check_overlay_raster(actual, source)


def test_full_overlay_requires_both_authorized_map_bindings(tmp_path):
    raster(tmp_path / "density.tif")
    frame = gpd.GeoDataFrame(
        {"benchmark_row_id": ["rail:1", "rail:2"]},
        geometry=[LineString([(89, 25), (90, 26)]), LineString([(90, 25), (91, 26)])],
        crs=4326,
    )
    frame.to_parquet(tmp_path / "rail.parquet")
    assets = {
        k: {"path": p, "sha256": sha(tmp_path / p)}
        for k, p in [("bangladesh_density", "density.tif"), ("bangladesh_railways", "rail.parquet")]
    }
    (tmp_path / "fixtures.json").write_text(json.dumps({"assets": assets}))
    expected = overlay_answer(tmp_path, "281727", assets)
    assert expected["count"] == 2 and expected["unknownCount"] == 1
    inputs = {key: {"collectionId": key, "itemId": "i", "assetKey": "data"} for key in assets}
    claim = {
        "count": 2,
        "unknown_count": 1,
        "selection": inputs["bangladesh_density"],
        "map_layer_id": "density-layer",
        "overlay": {"selection": inputs["bangladesh_railways"], "map_layer_id": "rail-layer"},
    }
    snapshot = {
        "scope": {"mapId": "map"},
        "evaluationDeadline": 100,
        "workflows": [],
        "layers": {
            "map_layers": [
                {
                    "id": layer,
                    "map_id": "map",
                    "availability": "available",
                    "created_at": "1970-01-01T00:00:01Z",
                    "json_data": {"provider": "blue-stac", **inputs[key]},
                }
                for key, layer in [
                    ("bangladesh_density", "density-layer"),
                    ("bangladesh_railways", "rail-layer"),
                ]
            ]
        },
        "mapDisplays": {
            "density-layer": {
                "tilesets": [{"dataType": "coverage", "blue:display_style": "continuous-default"}]
            },
            "rail-layer": {"tilesets": [{"dataType": "vector"}]},
        },
    }
    args = (
        "281727",
        claim,
        expected,
        snapshot,
        {"fixtureDirectory": str(tmp_path)},
        {"inputs": inputs},
        tmp_path,
        100,
    )
    grade_overlay(*args)
    broken = deepcopy(snapshot)
    broken["layers"]["map_layers"][1]["map_id"] = "another-map"
    with pytest.raises(Blocked):
        grade_overlay(*args[:3], broken, *args[4:])
    broken = deepcopy(snapshot)
    broken["mapDisplays"]["density-layer"]["tilesets"][0]["blue:display_style"] = "categorical"
    with pytest.raises(Blocked):
        grade_overlay(*args[:3], broken, *args[4:])
    with pytest.raises(Blocked):
        grade_overlay("281727", {**claim, "count": 3}, *args[2:])


def test_original_question_and_no_reference_refusal_in_agent_protocol():
    task = protocol_for(["281727"])["tasks"]["281727"]
    assert (
        task["question"]
        == "Map the distribution of railway networks in relation to population density in Bangladesh."
    )
    assert "reject_task" not in json.dumps(task)
    assert "people/km²" in task["clarification"]
