import copy

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from terra_bench.common import Blocked
from terra_bench.county_heat_oracles import county_heat_answer, polygon_centroid
from terra_bench.county_tasks import COUNTY_GRID, COUNTY_RADIUS
from terra_bench.fixtures import ROW_ID
from terra_bench.policy import authorize


def test_independent_centroid_moments_holes_multipart_and_shift():
    from shapely.affinity import translate

    geometry = MultiPolygon(
        [
            Polygon([(0, 0), (6, 0), (6, 6), (0, 6)], holes=[[(1, 1), (3, 1), (3, 3), (1, 3)]]),
            box(8, 0, 10, 2),
        ]
    )
    for g in [geometry, translate(geometry, xoff=2000000, yoff=2000000)]:
        assert polygon_centroid(g).distance(g.centroid) < 1e-7


def test_county_heatmap_state_disambiguation_totals_null_rows_zero_and_missing(tmp_path):
    counties = gpd.GeoDataFrame(
        {
            ROW_ID: ["ma", "ny", "zero", "missing"],
            "STATEFP": ["25", "36", "36", "36"],
            "NAME": ["Essex", "Essex", "Zero", "Absent"],
        },
        geometry=[box(1000000 + i * 10000, 1500000, 1000001 + i * 10000, 1500001) for i in range(4)],
        crs=5070,
    )
    counties.to_parquet(tmp_path / "counties.parquet")
    pd.DataFrame(
        {"County": ["Essex", "TOTAL", None, None], "Number of Cases": [2.0, 100.0, None, None]}
    ).to_parquet(tmp_path / "tb_ma.parquet")
    pd.DataFrame(
        {"County": ["Essex", "Zero", "TOTAL", None, None], "2023 cases": [7.0, 0.0, 100.0, None, None]}
    ).to_parquet(tmp_path / "tb_ny.parquet")
    assets = {k: {"path": f"{k}.parquet"} for k in ["counties", "tb_ma", "tb_ny"]}
    answer = county_heat_answer(tmp_path, "695398", assets)
    assert answer["ids"] == ["ma", "ny", "zero"] and answer["unknownIds"] == ["missing"]
    assert answer["totalCases"] == 9 and answer["values"] == {"ma": 2, "ny": 7, "zero": 0}


def test_county_heat_approval_exact_method_and_grid_with_source_and_output_nodes():
    inputs = {"counties": {"collectionId": "blue-generated--fixture", "itemId": "one", "assetKey": "data"}}
    nodes = [
        {"id": "s", "type": "source", "selection": inputs["counties"]},
        {
            "id": "c",
            "type": "processor",
            "processId": "vector-centroids",
            "inputs": {
                "source": {"$output": {"nodeId": "s"}},
                "mode": "centroid",
                "centroidCrs": "EPSG:5070",
            },
        },
        {
            "id": "d",
            "type": "processor",
            "processId": "point-density",
            "inputs": {
                "source": {"$output": {"nodeId": "c"}},
                "grid": copy.deepcopy(COUNTY_GRID),
                "radiusM": COUNTY_RADIUS,
                "weightField": "case_count",
                "weightUnit": "cases",
            },
        },
        {"id": "o", "type": "output", "source": {"nodeId": "d"}, "delivery": "map"},
    ]
    manifest = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {"nodes": nodes},
    }
    authorize(manifest, "695398", inputs)
    for field, value in [("centroidCrs", "EPSG:3857"), ("mode", "representative-point")]:
        wrong = copy.deepcopy(manifest)
        wrong["definition"]["nodes"][1]["inputs"][field] = value
        with pytest.raises(Blocked):
            authorize(wrong, "695398", inputs)
