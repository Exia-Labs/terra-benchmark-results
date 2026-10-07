"""Regression cases for ordinary adapter defects, not analytical substitutions."""

import copy

import pytest

from terra_bench.common import Blocked
from terra_bench.policy import authorize


def series_graph(area):
    inputs = {k: {"collectionId": k, "itemId": "fixture", "assetKey": "data"}
              for k in ("countries", "co2", "ghg")}
    graph = {"valid": True, "approvalDigest": "exact", "readiness": {"status": "ready"},
             "definition": {"nodes": [{"id": "join", "type": "processor", "processId": "table-attribute-join",
                                       "inputs": {"vector": inputs["countries"], "table": inputs["co2"],
                                                  "vectorKey": "NAME_EN", "tableKey": "Country name",
                                                  "fields": ["Country name", "1990"], "joinType": "left",
                                                  "area": area}}]}}
    return graph, inputs


def test_map_series_accepts_proven_non_cropping_extent_without_changing_approval():
    bounds = [-179.9999999999, -59.47, 180.0000000001, 83.64]
    graph, inputs = series_graph({"bbox": [-180, -59.47, 180, 83.64], "crs": "OGC:CRS84"})
    before = copy.deepcopy(graph)
    assert authorize(graph, "438953", inputs, fixture_bounds={"countries": bounds})["approvalDigest"] == "exact"
    assert graph == before


@pytest.mark.parametrize("area", [
    {"bbox": [-179, -59.47, 180, 83.64]},
    {"bbox": [-180, -58, 180, 83.64]},
    {"bbox": [-180, -90, 180, 90], "crs": "EPSG:3857"},
    {"bbox": [-180, -90, 180, 90], "unexpected": True},
])
def test_map_series_still_rejects_actual_clipping_or_unproven_area(area):
    graph, inputs = series_graph(area)
    with pytest.raises(Blocked, match="clipping"):
        authorize(graph, "438953", inputs, fixture_bounds={"countries": [-180, -59.47, 180, 83.64]})


def test_map_series_requires_extent_evidence_and_keeps_year_policy():
    graph, inputs = series_graph({"bbox": [-180, -90, 180, 90]})
    with pytest.raises(Blocked, match="clipping"):
        authorize(graph, "438953", inputs)
    graph["definition"]["nodes"][0]["inputs"]["fields"] = ["Country name", "2023"]
    with pytest.raises(Blocked):
        authorize(graph, "438953", inputs, fixture_bounds={"countries": [-180, -59, 180, 84]})
