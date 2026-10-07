import copy
import math

import geopandas as gpd
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import Point
from test_population import write_raster

from terra_bench.common import Blocked
from terra_bench.geodesic_oracle import nearest_distances, vincenty_metres
from terra_bench.policy import authorize
from terra_bench.population_distance_oracles import distance_answer


def test_independent_vincenty_equator_meridian_coincidence_and_wrap():
    distance = vincenty_metres(
        np.array([0.0, 0.0, 179.0]),
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, 1.0, -179.0]),
        np.array([0.0, 0.0, 0.0]),
    )
    np.testing.assert_allclose(distance, [0, 6378137 * math.pi / 180, 2 * 6378137 * math.pi / 180], atol=1e-6)
    assert vincenty_metres(0.0, 0.0, 0.0, 1.0) == pytest.approx(110574.38855779878, abs=1e-5)
    first = nearest_distances([0.0, 2.0], [0.0, 0.0], [(0, 0), (3, 0)])
    second = nearest_distances([0.0, 2.0], [0.0, 0.0], [(3, 0), (0, 0), (0, 0)])
    np.testing.assert_equal(first, second)
    with pytest.raises(Blocked):
        vincenty_metres(0.0, 0.0, 180.0, 0.0)


def test_population_near_points_sums_original_counts_once_and_preserves_missing(tmp_path):
    grid = Affine(0.1, 0, -0.05, 0, -0.1, 0.05)
    write_raster(tmp_path / "pop.tif", np.array([[100.0, 200.0, 300.0, 0.0, np.nan]]), grid)
    gpd.GeoDataFrame(
        {"Country": ["Angola", "Angola", "Other"], "benchmark_row_id": ["one", "duplicate", "excluded"]},
        geometry=[Point(0, 0), Point(0, 0), Point(0.2, 0)],
        crs=4326,
    ).to_parquet(tmp_path / "points.parquet")
    expected = distance_answer(
        tmp_path,
        "785163",
        {"angola_population": {"path": "pop.tif"}, "facilities": {"path": "points.parquet"}},
    )
    assert expected["count"] == 2 and expected["unknownCount"] == 1
    assert expected["metrics"] == {"selected_people": 300.0, "total_people": 600.0, "percentage": 50.0}
    assert expected["pointIds"] == ["duplicate", "one"]
    with np.load(tmp_path / expected["reference"]) as values:
        np.testing.assert_allclose(values["selected"][0, :4], [100, 200, 0, 0])
        assert np.isnan(values["distance"][0, 4])


def test_policy_does_not_confuse_source_alias_with_spatial_clipping():
    source = {"collectionId": "fixture", "itemId": "one", "assetKey": "data"}
    manifest = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [
                {
                    "id": "calc",
                    "type": "processor",
                    "processId": "raster-map-algebra",
                    "inputs": {
                        "sources": {"area": source, "geometry": source, "bbox": source},
                        "expression": "area / bbox",
                    },
                }
            ]
        },
    }
    authorize(manifest, "551060", {"angola_population": source})
    bad = copy.deepcopy(manifest)
    bad["definition"]["nodes"][0]["inputs"]["area"] = {"bbox": [0, 0, 1, 1]}
    with pytest.raises(Blocked, match="clipping"):
        authorize(bad, "551060", {"angola_population": source})


def test_proximity_approval_requires_frozen_geodesic_grid_and_country():
    inputs = {
        k: {"collectionId": k, "itemId": "one", "assetKey": "data"}
        for k in ["angola_population", "facilities"]
    }
    settings = {
        "source": inputs["facilities"],
        "match": inputs["angola_population"],
        "method": "geodesic-points",
    }
    manifest = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [
                {"id": "distance", "type": "processor", "processId": "distance-surface", "inputs": settings}
            ]
        },
    }
    authorize(manifest, "785163", inputs)
    for key, value in [
        ("method", "rasterized"),
        ("maximumDistanceM", 20000),
        ("match", inputs["facilities"]),
    ]:
        bad = copy.deepcopy(manifest)
        bad["definition"]["nodes"][0]["inputs"][key] = value
        with pytest.raises(Blocked, match="proximity"):
            authorize(bad, "785163", inputs)
    manifest["definition"]["nodes"] = [
        {
            "id": "filter",
            "type": "processor",
            "processId": "vector-filter",
            "inputs": {
                "source": inputs["facilities"],
                "predicates": [{"field": "Country", "operator": "eq", "value": "Angola"}],
            },
        }
    ]
    authorize(manifest, "785163", inputs)
    manifest["definition"]["nodes"][0]["inputs"]["predicates"][0]["value"] = "Peru"
    with pytest.raises(Blocked):
        authorize(manifest, "785163", inputs)
