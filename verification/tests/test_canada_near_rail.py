import copy

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, Point

from terra_bench.common import Blocked
from terra_bench.fixtures import ROW_ID
from terra_bench.heat_oracles import heat_selection
from terra_bench.heat_tasks import HEAT_TASKS
from terra_bench.policy import authorize
from terra_bench.tasks import protocol_for


def test_independent_rail_eligibility_counts_negative_magnitude_not_as_weight(monkeypatch):
    spec = {**HEAT_TASKS["968087"], "distanceCrs": "EPSG:3857"}
    monkeypatch.setitem(HEAT_TASKS, "968087", spec)
    points = gpd.GeoDataFrame(
        {ROW_ID: ["near", "outside", "us", "missing", "zero"], "mag": [-1, 2, 3, 4, 0]},
        geometry=[Point(5, 9999), Point(5, 10001), Point(50000, 0), None, Point(5, 0)],
        crs=3857,
    )
    rails = gpd.GeoDataFrame(
        {"COUNTRY": ["CA", "US"]},
        geometry=[LineString([(0, 0), (10, 0)]), LineString([(50000, -10), (50000, 10)])],
        crs=3857,
    )
    selected, weights, unknown, unlocated = heat_selection("968087", points, None, {}, lines=rails)
    assert selected[ROW_ID].tolist() == ["near", "zero"]
    np.testing.assert_array_equal(weights, [1, 1])
    assert unknown == unlocated == ["missing"]
    with pytest.raises(Blocked, match="precision"):
        heat_selection(
            "968087",
            points.assign(geometry=[Point(5, 10000), Point(5, 10001), Point(50000, 0), None, Point(5, 0)]),
            None,
            {},
            lines=rails,
        )


def test_policy_nearest_source_projection_and_strict_threshold():
    inputs = {
        k: {"collectionId": k, "itemId": "one", "assetKey": "data"} for k in ["earthquakes", "na_railways"]
    }
    nodes = [
        {
            "id": "ca",
            "type": "processor",
            "processId": "vector-filter",
            "inputs": {
                "source": inputs["na_railways"],
                "predicates": [{"field": "COUNTRY", "operator": "eq", "value": "CA"}],
            },
        },
        {
            "id": "distance",
            "type": "processor",
            "processId": "vector-nearest-distance",
            "inputs": {
                "source": inputs["earthquakes"],
                "targets": {"$output": {"nodeId": "ca"}},
                "distanceCrs": "EPSG:3978",
                "outputField": "rail_m",
            },
        },
        {
            "id": "near",
            "type": "processor",
            "processId": "vector-filter",
            "inputs": {
                "source": {"$output": {"nodeId": "distance"}},
                "predicates": [{"field": "rail_m", "operator": "lt", "value": 10000}],
            },
        },
    ]
    proposal = {
        "valid": True,
        "approvalDigest": "exact",
        "readiness": {"status": "ready"},
        "definition": {"nodes": nodes},
    }
    authorize(proposal, "968087", inputs)
    for mutate in [
        lambda n: n[0]["inputs"]["predicates"][0].update(value="US"),
        lambda n: n[1]["inputs"].update(distanceCrs="EPSG:3857"),
        lambda n: n[1]["inputs"].update(targets=inputs["earthquakes"]),
        lambda n: n[2]["inputs"]["predicates"][0].update(operator="lte"),
    ]:
        bad = copy.deepcopy(proposal)
        mutate(bad["definition"]["nodes"])
        with pytest.raises(Blocked):
            authorize(bad, "968087", inputs)
    protocol = protocol_for(["968087"])["tasks"]["968087"]
    assert "10,000" in protocol["clarification"] and "negative magnitudes" in protocol["clarification"]
