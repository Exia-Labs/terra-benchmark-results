import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from terra_bench.common import Blocked
from terra_bench.family_oracles import HIGH_INCOME, LOW_INCOME, country_stat, snow_stations
from terra_bench.fixtures import ROW_ID
from terra_bench.grading import check_extra_results
from terra_bench.policy import authorize
from terra_bench.tasks import protocol_for


def countries():
    return gpd.GeoDataFrame({ROW_ID: ["a", "b", "c", "d"], "ISO_A3": ["AAA", "BBB", "CCC", "DDD"],
        "NAME_EN": ["A", "B", "C", "D"], "CONTINENT": ["Africa"] * 4,
        "INCOME_GRP": [*HIGH_INCOME, LOW_INCOME, LOW_INCOME]},
        geometry=[box(i * 3, 0, i * 3 + 2, 2) for i in range(4)], crs=4326)


def test_country_stat_strict_geometry_once_per_country_missing_and_real_zero():
    points = gpd.GeoDataFrame(geometry=[Point(1, 1), Point(1, 1), Point(4, 1),
                                       Point(7, 1), Point(9, 1)], crs=4326)
    table = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC", "DDD"], "2021": [100., 0., None, 500.]})
    result = country_stat(countries(), table, "2021", points=points, africa=True)
    assert result["ids"] == ["a", "b"]
    assert result["metrics"] == {"mean": 50.}
    assert result["unknownIds"] == ["c"]
    assert result["stationCounts"] == {"a": 2, "b": 1, "c": 1, "d": 0}
    assert country_stat(countries(), table, "2021", points=points, minimum=2)["ids"] == ["a"]
    with pytest.raises(Blocked, match="ambiguous"):
        country_stat(countries(), pd.concat([table, table]), "2021")


def test_income_means_combine_high_groups_not_population_weighted():
    table = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC", "DDD"], "2022": [1., 3., 6., None]})
    result = country_stat(countries(), table, "2022", income=True)
    assert result["metrics"] == {"high_income": 2., "low_income": 6.}
    assert result["unknownIds"] == ["d"]
    frame = countries().iloc[:3].copy()
    frame["fertility"] = [1., 3., 6.]
    claim = {"metrics": result["metrics"], "value_field": "fertility"}
    check_extra_results(frame, ROW_ID, claim, result)
    with pytest.raises(Blocked, match="statistic"):
        check_extra_results(frame, ROW_ID, {**claim, "metrics": {"high_income": 3., "low_income": 6.}}, result)
    frame["fertility"] = [2., 2., 6.]  # correct mean, wrong contributing values still fails
    with pytest.raises(Blocked, match="measurement"):
        check_extra_results(frame, ROW_ID, claim, result)


def test_snow_state_groups_threshold_missing_and_outside_question(tmp_path):
    path = tmp_path / "snow.tif"
    with rasterio.open(path, "w", driver="GTiff", height=1, width=4, count=1, dtype="float32",
                       crs=4326, transform=from_origin(0, 1, 1, 1), nodata=-9999) as raster:
        raster.write(np.array([[13, 12, 0, -9999]], dtype="float32"), 1)
    frame = gpd.GeoDataFrame({ROW_ID: ["a", "b", "c", "d", "e", "f", "g"],
        "State": ["NY", "NY", "CA", "WI", "ON", "DC", "VT"]},
        geometry=[Point(.5, .5), Point(1.5, .5), Point(2.5, .5), Point(3.5, .5),
                  Point(.5, .5), Point(.5, .5), Point(5, .5)], crs=4326)
    result = snow_stations(frame, path)
    assert result["ids"] == ["a"] and result["groups"] == {"NY": 1}
    assert result["unknownIds"] == ["d", "g"]
    out = frame.iloc[:1].copy()
    out["snow"] = 13.
    check_extra_results(out, ROW_ID, {"groups": {"NY": 1}, "value_field": "snow"}, result)
    with pytest.raises(Blocked, match="state counts"):
        check_extra_results(out, ROW_ID, {"groups": {"WI": 1}, "value_field": "snow"}, result)


def test_new_policy_exact_year_country_predicate_and_count_threshold():
    inputs = {key: {"collectionId": key, "itemId": "one", "assetKey": "data"}
              for key in ["countries", "power_stations", "water_withdrawal"]}
    nodes = [{"id": "counts", "type": "processor", "processId": "vector-spatial-join",
              "inputs": {"target": inputs["countries"], "join": inputs["power_stations"],
                         "predicate": "contains", "matchMode": "aggregate", "aggregations": [
                             {"field": ROW_ID, "operation": "count", "outputField": "n"}]}},
             {"id": "filter", "type": "processor", "processId": "vector-filter", "inputs": {
                 "source": {"$output": {"nodeId": "counts"}}, "predicates": [{"field": "n", "operator": "gt", "value": 5}]}},
             {"id": "join", "type": "processor", "processId": "table-attribute-join", "inputs": {
                 "vector": {"$output": {"nodeId": "filter"}}, "table": inputs["water_withdrawal"], "fields": ["2021"]}}]
    manifest = {"valid": True, "readiness": {"status": "ready"}, "approvalDigest": "exact", "definition": {"nodes": nodes}}
    authorize(manifest, "806525", inputs)
    nodes[-1]["inputs"]["fields"] = ["2020"]
    with pytest.raises(Blocked, match="year"):
        authorize(manifest, "806525", inputs)
    nodes[-1]["inputs"]["fields"] = ["2021"]
    nodes[0]["inputs"]["predicate"] = "intersects"
    with pytest.raises(Blocked, match="relationship"):
        authorize(manifest, "806525", inputs)
    nodes[0]["inputs"]["predicate"] = "contains"
    nodes[1]["inputs"]["predicates"][0]["value"] = 4
    with pytest.raises(Blocked, match="threshold"):
        authorize(manifest, "806525", inputs)


def test_five_new_tasks_have_explicit_frozen_contracts():
    for task, value in protocol_for(["883928", "806525", "429627", "918547", "977524"])["tasks"].items():
        assert value["outputContract"] and "value_field" in value["outputContract"]
        assert value["clarification"] and value["question"]


def test_missing_point_coverage_cannot_silently_disappear():
    frame = countries().iloc[:1].copy()
    frame["v"] = 2.
    expected = {"values": {"a": 2.}, "metrics": {"mean": 2.}, "unlocatedPointIds": ["p"]}
    claim = {"value_field": "v", "metrics": {"mean": 2.}}
    with pytest.raises(Blocked, match="unlocated"):
        check_extra_results(frame, ROW_ID, claim, expected)
    check_extra_results(frame, ROW_ID, {**claim, "unlocated_count": 1}, expected)
