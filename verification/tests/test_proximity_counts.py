import copy

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point

from terra_bench.common import Blocked
from terra_bench.fixtures import ROW_ID
from terra_bench.policy import authorize
from terra_bench.proximity_tasks import PROXIMITY_TASKS, proximity_answer


def test_independent_line_distance_deduplicates_targets_and_preserves_unknown(monkeypatch):
    monkeypatch.setitem(PROXIMITY_TASKS, "418513", {**PROXIMITY_TASKS["418513"], "distanceCrs": "EPSG:3857"})
    points = gpd.GeoDataFrame(
        {ROW_ID: ["inside", "outside", "unknown", "zero"]},
        geometry=[Point(5, 9999), Point(5, 10001), None, Point(5, 0)],
        crs=3857,
    )
    lines = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (10, 0)])] * 2, crs=3857)
    result = proximity_answer(points, lines)
    assert (
        result["count"] == 2 and result["ids"] == ["inside", "zero"] and result["unknownIds"] == ["unknown"]
    )
    points.loc[0, "geometry"] = Point(5, 10000)
    with pytest.raises(Blocked, match="precision"):
        proximity_answer(points, lines)


def test_proximity_policy_requires_full_source_and_declared_projection():
    inputs = {
        k: {"collectionId": k, "itemId": "one", "assetKey": "data"}
        for k in ["power_stations", "africa_railways"]
    }
    proposal = {
        "valid": True,
        "approvalDigest": "exact",
        "readiness": {"status": "ready"},
        "definition": {
            "nodes": [
                {
                    "id": "d",
                    "type": "processor",
                    "processId": "vector-nearest-distance",
                    "inputs": {
                        "source": inputs["power_stations"],
                        "targets": inputs["africa_railways"],
                        "distanceCrs": "ESRI:102022",
                        "outputField": "rail_m",
                    },
                },
                {
                    "id": "near",
                    "type": "processor",
                    "processId": "vector-filter",
                    "inputs": {
                        "source": {"$output": {"nodeId": "d"}},
                        "predicates": [{"field": "rail_m", "operator": "lt", "value": 10000}],
                    },
                },
            ]
        },
    }
    authorize(proposal, "418513", inputs)
    for path, value in [("distanceCrs", "EPSG:3857"), ("targets", inputs["power_stations"])]:
        bad = copy.deepcopy(proposal)
        bad["definition"]["nodes"][0]["inputs"][path] = value
        with pytest.raises(Blocked):
            authorize(bad, "418513", inputs)
    bad = copy.deepcopy(proposal)
    bad["definition"]["nodes"][1]["inputs"]["predicates"][0]["value"] = 20000
    with pytest.raises(Blocked):
        authorize(bad, "418513", inputs)
