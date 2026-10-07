import copy

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from affine import Affine
from shapely.geometry import box

from terra_bench.common import Blocked
from terra_bench.county_density import BBOX, counties_with_cases, reference_grid
from terra_bench.policy import authorize


def test_state_qualified_positive_cases_missing_zero_and_totals():
    frame = gpd.GeoDataFrame(
        {
            "benchmark_row_id": ["ma", "ny", "zero", "missing", "outside"],
            "STATEFP": ["25", "36", "36", "25", "06"],
            "NAME": ["Essex", "Essex", "Zero", "Absent", "Essex"],
        },
        geometry=[box(0, 0, 1, 1)] * 5,
        crs=4326,
    )
    tables = {
        "tb_ma": pd.DataFrame(
            {"County": ["Essex", "TOTAL", None, None], "Number of Cases": [2, 999, None, None]}
        ),
        "tb_ny": pd.DataFrame({"County": ["Essex", "Zero"], "2023 cases": [8, 0]}),
    }
    selected, unknown = counties_with_cases(frame, tables)
    assert dict(zip(selected.benchmark_row_id, selected.case_count)) == {"ma": 2, "ny": 8}
    assert unknown == ["missing"]
    tables["tb_ny"].loc[1, "2023 cases"] = -1
    with pytest.raises(Blocked, match="Invalid"):
        counties_with_cases(frame, tables)
    tables["tb_ny"] = pd.concat([tables["tb_ny"].iloc[:1]] * 2)
    with pytest.raises(Blocked, match="Ambiguous"):
        counties_with_cases(frame, tables)


def test_native_density_keeps_valid_zero_and_does_not_fill_unknown(tmp_path):
    path = tmp_path / "population.tif"
    data = np.array([[0, 200, 400], [1000, -9999, 500]], dtype="float64")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=3,
        count=1,
        dtype="float64",
        crs=4326,
        transform=Affine(1, 0, 0, 0, -1, 2),
        nodata=-9999,
    ) as out:
        out.write(data, 1)
    counties = gpd.GeoDataFrame(geometry=[box(-0.1, -0.1, 1.9, 2.1)], crs=4326)
    with rasterio.open(path) as src:
        values, t = reference_grid(src, counties, [0, 0, 3, 2])
        assert values[0, 0] == 0 and np.isfinite(values[0, 1]) and np.isfinite(values[1, 0])
        assert np.isnan(values[:, 2]).all() and np.isnan(values[1, 1])
        # Independently bound physical area at the equator (~12,300 km2).
        assert 0.08 < values[1, 0] < 0.082
        with pytest.raises(Blocked, match="aligned"):
            reference_grid(src, counties, [0.1, 0, 3, 2])
        counties.geometry = [box(-0.1, -0.1, 0.5, 2.1)]
        with pytest.raises(Blocked, match="boundary"):
            reference_grid(src, counties, [0, 0, 3, 2])


def test_approval_native_crop_exact_scope_and_centre_mask():
    inputs = {
        k: {"collectionId": k, "itemId": "fixture", "assetKey": "data"} for k in ["counties", "us_population"]
    }
    manifest = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [
                {
                    "id": "c",
                    "type": "processor",
                    "processId": "spatial-clip",
                    "inputs": {"source": inputs["us_population"], "area": {"bbox": BBOX}},
                },
                {
                    "id": "v",
                    "type": "processor",
                    "processId": "vector-rasterize",
                    "inputs": {
                        "source": inputs["counties"],
                        "match": {"$output": {"nodeId": "c"}},
                        "allTouched": False,
                    },
                },
                {
                    "id": "f",
                    "type": "processor",
                    "processId": "vector-filter",
                    "inputs": {
                        "source": inputs["counties"],
                        "predicates": [{"field": "STATEFP", "operator": "in", "value": ["25", "36"]}],
                    },
                },
            ]
        },
    }
    authorize(manifest, "419069", inputs)
    assert manifest["definition"]["nodes"][0]["inputs"]["area"] == {"bbox": BBOX}
    manifest["definition"]["nodes"][0]["inputs"]["area"]["crs"] = "OGC:CRS84"
    authorize(manifest, "419069", inputs)
    for change in ["bounds", "touched", "state", "crs"]:
        bad = copy.deepcopy(manifest)
        if change == "bounds":
            bad["definition"]["nodes"][0]["inputs"]["area"]["bbox"][0] += 0.1
        elif change == "touched":
            bad["definition"]["nodes"][1]["inputs"]["allTouched"] = True
        elif change == "state":
            bad["definition"]["nodes"][2]["inputs"]["predicates"][0]["value"] = ["06"]
        else:
            bad["definition"]["nodes"][0]["inputs"]["area"]["crs"] = "EPSG:3857"
        with pytest.raises(Blocked):
            authorize(bad, "419069", inputs)


def test_zero_case_quality_check_cannot_feed_a_deliverable():
    inputs = {key: {"collectionId": key, "itemId": "fixture", "assetKey": "data"}
              for key in ("counties", "us_population")}
    manifest = {"valid": True, "readiness": {"status": "ready"}, "approvalDigest": "exact",
                "definition": {"nodes": [
                    {"id": "positive", "type": "processor", "processId": "vector-filter", "inputs": {
                        "source": inputs["counties"], "predicates": [{"field": "case_count", "operator": "gt", "value": 0}]}},
                    {"id": "zero", "type": "processor", "processId": "vector-filter", "inputs": {
                        "source": inputs["counties"], "predicates": [{"field": "case_count", "operator": "eq", "value": 0}]}},
                    {"id": "answer", "type": "output", "source": {"nodeId": "positive"}, "delivery": "artifact"},
                ]}}
    authorize(manifest, "419069", inputs)
    diagnostic = {"id": "coverage_check", "type": "processor", "processId": "zonal-statistics",
                  "inputs": {"zones": {"$output": {"nodeId": "positive"}},
                             "raster": inputs["us_population"], "statistics": ["count"],
                             "allTouched": False, "zoneIdField": "benchmark_row_id"}}
    manifest["definition"]["nodes"].insert(-1, diagnostic)
    authorize(manifest, "419069", inputs)
    for change in ("published", "statistic", "touches", "identity"):
        bad = copy.deepcopy(manifest)
        nodes = bad["definition"]["nodes"]
        if change == "published":
            nodes[-1]["source"]["nodeId"] = "coverage_check"
        elif change == "statistic":
            nodes[-2]["inputs"]["statistics"] = ["sum"]
        elif change == "touches":
            nodes[-2]["inputs"]["allTouched"] = True
        else:
            nodes[-2]["inputs"]["zoneIdField"] = "wrong_identity"
        with pytest.raises(Blocked):
            authorize(bad, "419069", inputs)
    for change in ("direct", "indirect", "no_contract", "different_threshold"):
        bad = copy.deepcopy(manifest)
        nodes = bad["definition"]["nodes"]
        if change == "direct":
            nodes[-1]["source"]["nodeId"] = "zero"
        elif change == "indirect":
            nodes[0]["inputs"]["source"] = {"$output": {"nodeId": "zero"}}
        elif change == "no_contract":
            nodes.pop()
        else:
            nodes[1]["inputs"]["predicates"][0]["value"] = 5
        with pytest.raises(Blocked):
            authorize(bad, "419069", inputs)
