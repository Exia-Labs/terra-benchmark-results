from copy import deepcopy

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import LineString

from terra_bench.common import Blocked
from terra_bench.snow_rail import answer, grade, split_segment


def test_strict_boundary_nodata_and_edge_convention():
    values = np.array([[37, 36, 99], [0, 0, 0]], dtype=float)
    valid = np.array([[True, True, False], [True, True, True]])
    pieces, missing = split_segment(
        np.array([-0.5, 0.5]), np.array([3.5, 0.5]), Affine.identity(), values, valid
    )
    assert missing and len(pieces) == 1
    np.testing.assert_allclose(pieces[0], [[0, 0.5], [1, 0.5]])
    # A segment on a closed qualifying pixel boundary is included once.
    pieces, missing = split_segment(np.array([0.1, 1]), np.array([0.9, 1]), Affine.identity(), values, valid)
    assert len(pieces) == 1 and not missing


def test_oracle_and_grader_reject_whole_lines_duplicate_wrong_total(tmp_path):
    from geographiclib.geodesic import Geodesic

    values = np.array([[37, 36, 50], [37, 36, 50]], dtype="float64")
    with rasterio.open(
        tmp_path / "snow.tif",
        "w",
        driver="GTiff",
        width=3,
        height=2,
        count=1,
        dtype="float64",
        crs=4326,
        transform=Affine(1, 0, 0, 0, -1, 2),
    ) as ds:
        ds.write(values, 1)
    source = gpd.GeoDataFrame(
        {"benchmark_row_id": ["a", "b", "non-US"], "COUNTRY": ["US", "US", "CA"]},
        geometry=[
            LineString([(-0.5, 0.5), (3.5, 0.5)]),
            LineString([(1.1, 0.5), (1.9, 0.5)]),
            LineString([(0, 1), (1, 1)]),
        ],
        crs=4326,
    )
    source.to_parquet(tmp_path / "rails.parquet")
    expected = answer(tmp_path, {"na_railways": {"path": "rails.parquet"}, "snow": {"path": "snow.tif"}})
    assert expected["count"] == 1 and expected["unknownCount"] == 1
    reference = gpd.read_parquet(tmp_path / expected["reference"])
    length = 2 * Geodesic.WGS84.Inverse(0.5, 0, 0.5, 1)["s12"] / 1000
    assert expected["metrics"]["length_km"] == pytest.approx(length, rel=1e-12)
    claim = {"count": 1, "unknown_count": 1, "metrics": expected["metrics"]}
    grade(reference, claim, expected, tmp_path, "benchmark_row_id")
    with pytest.raises(Blocked, match="exactly"):
        grade(source.iloc[:1], claim, expected, tmp_path, "benchmark_row_id")
    import pandas as pd

    with pytest.raises(Blocked, match="Duplicated"):
        grade(pd.concat([reference, reference]), claim, expected, tmp_path, "benchmark_row_id")
    bad = deepcopy(claim)
    bad["metrics"]["length_km"] += 1
    with pytest.raises(Blocked, match="incorrect"):
        grade(reference, bad, expected, tmp_path, "benchmark_row_id")


def test_clipped_identity_and_policy():
    from terra_bench.lineage import record_identity_field
    from terra_bench.policy import authorize

    sources = {
        k: {"collectionId": k, "itemId": "frozen", "assetKey": "data"} for k in ["na_railways", "snow"]
    }
    graph = {
        "valid": True,
        "approvalDigest": "digest",
        "readiness": {"status": "ready"},
        "definition": {
            "nodes": [
                {
                    "id": "us",
                    "type": "processor",
                    "processId": "vector-filter",
                    "inputs": {
                        "source": sources["na_railways"],
                        "predicates": [{"field": "COUNTRY", "operator": "eq", "value": "US"}],
                    },
                },
                {
                    "id": "mask",
                    "type": "processor",
                    "processId": "raster-map-algebra",
                    "inputs": {"sources": {"s": sources["snow"]}, "expression": "where(s > 36, 1, 0)"},
                },
                {
                    "id": "polys",
                    "type": "processor",
                    "processId": "raster-polygonize",
                    "inputs": {"source": {"$output": {"nodeId": "mask"}}, "values": [1]},
                },
                {
                    "id": "clipped",
                    "type": "processor",
                    "processId": "vector-overlay",
                    "inputs": {
                        "primary": {"$output": {"nodeId": "us"}},
                        "overlay": {"$output": {"nodeId": "polys"}},
                        "operation": "intersection",
                    },
                },
            ]
        },
    }
    authorize(graph, "310610", sources)
    selection = {"collectionId": "output", "itemId": "new", "assetKey": "data"}
    snapshot = {
        "workflows": [
            {
                "id": "w",
                "manifest": graph,
                "nodes": [{"node_id": "clipped", "status": "succeeded", "outputs": {"result": selection}}],
            }
        ],
        "artifacts": [selection],
    }
    fixtures = {
        "assets": {"na_railways": {"fields": [{"name": "benchmark_row_id"}, {"name": "COUNTRY"}]}, "snow": {}}
    }
    assert (
        record_identity_field(snapshot, selection, sources, fixtures, "na_railways")
        == "primary_benchmark_row_id"
    )
    graph["definition"]["nodes"][0]["inputs"]["predicates"][0]["value"] = "CA"
    with pytest.raises(Blocked):
        authorize(graph, "310610", sources)
