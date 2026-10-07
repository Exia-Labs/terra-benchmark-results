import copy

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from terra_bench.common import ROOT, Blocked, read
from terra_bench.fixtures import ROW_ID, TASK_ASSETS
from terra_bench.policy import authorize
from terra_bench.series_grading import check_series_structure
from terra_bench.series_oracles import series_answer
from terra_bench.series_tasks import SERIES_TASKS
from terra_bench.tasks import protocol_for


def test_series_oracle_years_zero_unknown_and_region():
    countries = gpd.GeoDataFrame(
        {
            ROW_ID: ["a", "b", "c"],
            "ISO_A3": ["AAA", "BBB", "CCC"],
            "SUBREGION": ["Southern Asia", "Southern Asia", "Europe"],
        },
        geometry=[box(i, 0, i + 1, 1) for i in range(3)],
        crs=4326,
    )
    table = pd.DataFrame(
        {
            "Country Code": ["AAA", "BBB", "CCC"],
            "2005": [0.0, 20.0, 99.0],
            "2015": [5.0, None, 99.0],
            "2021": [10.0, 30.0, 99.0],
        }
    )
    expected = series_answer("702872", countries, table)
    assert expected["count"] == 3 and expected["unknownIds"] == ["2015:b"]
    assert expected["panels"]["2005"]["values"] == {"a": 0.0, "b": 20.0}
    panels = [
        {
            "year": year,
            "map_layer_id": year,
            "selection": {"collectionId": "c", "itemId": year, "assetKey": "data"},
        }
        for year in expected["panels"]
    ]
    claim = {"count": 3, "unknown_count": 1, "panels": panels, "selection": panels[0]["selection"]}
    assert check_series_structure(claim, expected) == panels
    for changed in [
        {**claim, "count": 2},
        {**claim, "unknown_count": 0},
        {**claim, "panels": panels[:2]},
        {**claim, "panels": [panels[0], panels[0], panels[2]]},
        {**claim, "panels": [{**p, "map_layer_id": "same"} for p in panels]},
        {**claim, "selection": panels[1]["selection"]},
    ]:
        with pytest.raises(Blocked):
            check_series_structure(changed, expected)
    with pytest.raises(Blocked, match="ambiguous"):
        series_answer("702872", countries, pd.concat([table, table]))


def test_original_series_and_policy_reject_wrong_year_or_units():
    original = {
        t["task_ID"].rsplit("_", 1)[-1]: t["task_text"]
        for t in read(ROOT / "data/upstream/benchmark_set/tasks_and_reference_solutions.json")["tasks"]
    }
    assert protocol_for(["702872"])["tasks"]["702872"]["question"] == original["702872"]
    assert TASK_ASSETS["702872"] == tuple(SERIES_TASKS["702872"]["assets"])
    inputs = {k: {"collectionId": k, "itemId": "one", "assetKey": "data"} for k in TASK_ASSETS["702872"]}
    nodes = [
        {"id": "source", "type": "source", "selection": inputs["countries"]},
        {
            "id": "class",
            "type": "processor",
            "processId": "vector-classify",
            "inputs": {
                "source": {"$output": {"nodeId": "source"}},
                "field": "2005",
                "unit": "% of land area",
                "method": "quantile",
                "classes": 5,
            },
        },
    ]
    manifest = {
        "valid": True,
        "approvalDigest": "exact",
        "readiness": {"status": "ready"},
        "definition": {"nodes": nodes},
    }
    authorize(manifest, "702872", inputs)
    for field, value in [("field", "2023"), ("unit", "people"), ("method", "equal-interval")]:
        wrong = copy.deepcopy(manifest)
        wrong["definition"]["nodes"][1]["inputs"][field] = value
        with pytest.raises(Blocked, match="year, classification"):
            authorize(wrong, "702872", inputs)


def test_bivariate_series_preserves_distinct_names_years_paired_missing_and_negatives():
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import box

    from terra_bench.fixtures import ROW_ID
    from terra_bench.series_oracles import series_answer

    frame = gpd.GeoDataFrame(
        {ROW_ID: ["a", "b", "c"], "NAME_EN": ["A", "B", "Unknown"]},
        geometry=[box(i, 0, i + 1, 1) for i in range(3)],
        crs=4326,
    )
    tables = {
        "co2": pd.DataFrame({"Country name": ["A", "B"], "1990": [-1.0, 0.0], "2020": [2.0, 3.0]}),
        "ghg": pd.DataFrame({"Country Name": ["A", "B"], "1990": [2.0, None], "2020": [4.0, 5.0]}),
    }
    result = series_answer("438953", frame, tables)
    assert result["count"] == 2
    assert result["panels"]["1990"]["count"] == 1 and result["panels"]["2020"]["count"] == 2
    assert result["panels"]["1990"]["values"]["a"] == -1
    assert result["panels"]["1990"]["classes"]["b"] == 0
    assert len(result["unknownIds"]) == 3
