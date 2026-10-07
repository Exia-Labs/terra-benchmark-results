import copy

import geopandas as gpd
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import LineString, MultiLineString
from test_population import write_raster

from terra_bench.common import Blocked
from terra_bench.policy import authorize
from terra_bench.population_oracles import quadrature_areas
from terra_bench.projected_population_oracle import projected_answer, segment_distances, segments


def test_segment_oracle_exact_boundaries_duplicates_and_exhaustive_random_check():
    lines = segments([MultiLineString([[(0, -2), (0, 2)], [(8, 1), (9, 2)]]), LineString([(0, -2), (0, 2)])])
    points = np.array([[0, 0], [1, 0], [2, 3], [9, 2]])
    np.testing.assert_allclose(segment_distances(points, lines), [0, 1, np.sqrt(5), 0])
    rng = np.random.default_rng(2725)
    lines = rng.normal(size=(150, 2, 2)) * 100
    points = rng.normal(size=(90, 2)) * 100
    actual = segment_distances(points, lines)
    brute = []
    for point in points:
        distances = []
        for a, b in lines:
            d = b - a
            t = np.clip(np.dot(point - a, d) / np.dot(d, d), 0, 1)
            distances.append(np.linalg.norm(point - a - t * d))
        brute.append(min(distances))
    np.testing.assert_allclose(actual, brute, rtol=1e-12, atol=1e-10)
    np.testing.assert_allclose(actual, segment_distances(points, lines[::-1]))


def test_density_to_people_and_corridor_area_not_unweighted_cell_average(tmp_path):
    transform = Affine(0.02, 0, 89.99, 0, -0.01, 24.005)
    write_raster(tmp_path / "density.tif", np.array([[1000.0, 1000.0, 0.0, np.nan]]), transform)
    gpd.GeoDataFrame(
        {"benchmark_row_id": ["rail1", "duplicate"]},
        geometry=[LineString([(90, 23), (90, 25)])] * 2,
        crs=4326,
    ).to_parquet(tmp_path / "rail.parquet")
    assets = {"bangladesh_density": {"path": "density.tif"}, "bangladesh_railways": {"path": "rail.parquet"}}
    expected = projected_answer(tmp_path, "618282", assets)
    area = quadrature_areas(transform, 1, 4326)[0]
    assert expected["count"] == 1 and expected["unknownCount"] == 1
    assert expected["metrics"]["selected_people"] == pytest.approx(1000 * area)
    assert expected["metrics"]["total_people"] == pytest.approx(2000 * area)
    comparison = projected_answer(tmp_path, "208110", assets)
    assert comparison["metrics"]["total_area_km2"] == pytest.approx(3 * area)
    assert comparison["metrics"]["national_density"] == pytest.approx(2000 / 3)
    assert comparison["metrics"]["corridor_density"] == pytest.approx(2000 / 3)


def test_projected_policy_fixes_source_projection_and_grid_but_allows_full_statistics():
    inputs = {
        k: {"collectionId": k, "itemId": "one", "assetKey": "data"}
        for k in ["bangladesh_density", "bangladesh_railways"]
    }
    args = {
        "source": inputs["bangladesh_railways"],
        "match": inputs["bangladesh_density"],
        "method": "projected-features",
        "distanceCrs": "EPSG:32646",
    }
    manifest = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [
                {"id": "distance", "type": "processor", "processId": "distance-surface", "inputs": args},
                {
                    "id": "summary",
                    "type": "processor",
                    "processId": "raster-statistics",
                    "inputs": {"source": inputs["bangladesh_density"]},
                },
            ]
        },
    }
    authorize(manifest, "618282", inputs)
    for field, value in [
        ("method", "rasterized"),
        ("distanceCrs", "EPSG:3857"),
        ("match", inputs["bangladesh_railways"]),
    ]:
        changed = copy.deepcopy(manifest)
        changed["definition"]["nodes"][0]["inputs"][field] = value
        with pytest.raises(Blocked, match="proximity"):
            authorize(changed, "618282", inputs)


def test_invalid_railway_geometry_is_not_missing_population():
    with pytest.raises(Blocked):
        segments([None])
