import copy

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from terra_bench.change_oracles import change_answer
from terra_bench.change_tasks import CHANGE_TASKS
from terra_bench.common import ROOT, Blocked, read
from terra_bench.fixtures import ROW_ID, TASK_ASSETS
from terra_bench.grading import check_extra_results, check_membership
from terra_bench.policy import authorize


def example():
    countries = gpd.GeoDataFrame(
        {ROW_ID: ["a", "b", "c", "d"], "ISO_A3": ["AAA", "BBB", "CCC", "DDD"], "CONTINENT": ["Africa"] * 4},
        geometry=[box(i, 0, i + 1, 1) for i in range(4)],
        crs=4326,
    )
    points = gpd.GeoDataFrame(
        {ROW_ID: ["one", "two", "three", "four", "boundary", "absent", "outside"]},
        geometry=[Point(i + 0.5, 0.5) for i in range(4)] + [Point(1, 0.5), None, Point(9, 9)],
        crs=4326,
    )
    return countries, points


def test_forest_strict_threshold_null_location_and_boundary():
    countries, points = example()
    table = pd.DataFrame(
        {
            "Country Code": ["AAA", "BBB", "CCC", "DDD"],
            "1990": [100.0, 100.0, 0, 100.0],
            "2021": [78.0, 79.0, 10, None],
        }
    )
    result = change_answer("932053", points, countries, {"forest_area": table})
    assert result["ids"] == ["one"]
    assert result["unknownIds"] == ["absent", "four", "three"]
    assert result["outsideGeometryIds"] == ["boundary", "outside"]
    assert not check_membership(["one", "one"], result["ids"])["pass"]
    assert not check_membership(["two"], result["ids"])["pass"]
    with pytest.raises(Blocked, match="unlocated"):
        check_extra_results(None, None, {}, result)


def test_urbanization_ratio_zeros_missing_and_exact_years():
    countries, points = example()
    pop = pd.DataFrame(
        {
            "Country Code": ["AAA", "BBB", "CCC", "DDD"],
            "2013": [100.0, 100.0, 0, 100.0],
            "2023": [100.0, 100.0, 100.0, None],
        }
    )
    rural = pd.DataFrame(
        {
            "Country Code": ["AAA", "BBB", "CCC", "DDD"],
            "2013": [50.0, 0.0, 20.0, 10.0],
            "2023": [40.0, 0.0, 10.0, 0.0],
        }
    )
    result = change_answer("710732", points, countries, {"population": pop, "rural": rural})
    assert result["ids"] == ["one"] and result["countryValues"]["b"] == 0
    assert result["unknownIds"] == ["absent", "four", "three"]
    assert result["countryValues"]["a"] == pytest.approx(-0.1)
    with pytest.raises(Blocked, match="duplicate"):
        change_answer("710732", points, countries, {"population": pd.concat([pop, pop]), "rural": rural})


def test_original_questions_and_allowed_years_thresholds():
    original = {
        t["task_ID"].rsplit("_", 1)[-1]: t["task_text"]
        for t in read(ROOT / "data/upstream/benchmark_set/tasks_and_reference_solutions.json")["tasks"]
    }
    for task, spec in CHANGE_TASKS.items():
        assert spec["question"] == original[task]
        assert TASK_ASSETS[task] == tuple(spec["assets"])
    inputs = {
        key: {"collectionId": key, "itemId": "one", "assetKey": "data"} for key in TASK_ASSETS["932053"]
    }
    nodes = [
        {"id": "source", "type": "source", "selection": inputs["countries"]},
        {
            "id": "calc",
            "type": "processor",
            "processId": "vector-field-calculate",
            "inputs": {
                "source": {"$output": {"nodeId": "source"}},
                "calculations": [
                    {"outputField": "ratio", "expression": "b/a", "fields": {"a": "1990", "b": "2021"}}
                ],
            },
        },
        {
            "id": "filter",
            "type": "processor",
            "processId": "vector-filter",
            "inputs": {
                "source": {"$output": {"nodeId": "calc"}},
                "predicates": [{"field": "ratio", "operator": "lt", "value": 0.79}],
            },
        },
    ]
    manifest = {
        "valid": True,
        "approvalDigest": "exact",
        "readiness": {"status": "ready"},
        "definition": {"nodes": nodes},
    }
    authorize(manifest, "932053", inputs)
    wrong = copy.deepcopy(manifest)
    wrong["definition"]["nodes"][-1]["inputs"]["predicates"][0]["value"] = 0.9
    with pytest.raises(Blocked, match="threshold"):
        authorize(wrong, "932053", inputs)


def test_seaport_growth_filters_region_and_preserves_strict_threshold():
    countries, points = example()
    countries["SUBREGION"] = ["South America", "Caribbean", "Central America", "Europe"]
    table = pd.DataFrame(
        {
            "Country Code": ["AAA", "BBB", "CCC", "DDD"],
            "2013": [100.0, 100.0, 0, 100.0],
            "2023": [120.0, 110.0, 300.0, 200.0],
        }
    )
    result = change_answer("104119", points, countries, {"population": table})
    assert result["ids"] == ["one"]
    assert result["unknownIds"] == ["absent", "three"]
    assert result["count"] == 1
