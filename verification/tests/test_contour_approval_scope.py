import copy

import pytest

from terra_bench.common import Blocked
from terra_bench.policy import authorize


def test_inner_join_envelope_prefilter_is_not_clipping_or_new_selection():
    inputs = {
        k: {"collectionId": k, "itemId": "fixture", "assetKey": "data"}
        for k in ["sa_rivers", "peru_provinces"]
    }
    args = {
        "target": inputs["sa_rivers"],
        "join": inputs["peru_provinces"],
        "joinType": "inner",
        "predicate": "within",
        "area": {"bbox": [-82, -19, -68, 1]},
    }
    manifest = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [{"id": "r", "type": "processor", "processId": "vector-spatial-join", "inputs": args}]
        },
    }
    bounds = {"peru_provinces": [-81.3, -18.4, -68.6, -0.03]}
    authorize(manifest, "655059", inputs, fixture_bounds=bounds)
    assert args["area"] == {"bbox": [-82, -19, -68, 1]}
    for kind in ["smaller", "left", "unknown"]:
        bad = copy.deepcopy(manifest)
        if kind == "smaller":
            bad["definition"]["nodes"][0]["inputs"]["area"]["bbox"][0] = -80
        if kind == "left":
            bad["definition"]["nodes"][0]["inputs"]["joinType"] = "left"
        with pytest.raises(Blocked):
            authorize(bad, "655059", inputs, fixture_bounds={} if kind == "unknown" else bounds)


def test_declared_country_envelope_does_not_use_global_guess():
    inputs = {
        k: {"collectionId": k, "itemId": "fixture", "assetKey": "data"} for k in ["sa_rivers", "countries"]
    }
    graph = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [
                {
                    "id": "country",
                    "type": "processor",
                    "processId": "vector-filter",
                    "inputs": {
                        "source": inputs["countries"],
                        "predicates": [{"field": "NAME_EN", "operator": "eq", "value": "Chile"}],
                    },
                },
                {
                    "id": "join",
                    "type": "processor",
                    "processId": "vector-spatial-join",
                    "inputs": {
                        "target": inputs["sa_rivers"],
                        "join": {"$output": {"nodeId": "country"}},
                        "joinType": "inner",
                        "predicate": "intersects",
                        "area": {"bbox": [-110, -57, -65, -17]},
                    },
                },
            ]
        },
    }
    authorize(
        graph, "763412", inputs, fixture_bounds={"countries:NAME_EN:Chile": [-109.46, -55.99, -66.4, -17.5]}
    )
    with pytest.raises(Blocked):
        authorize(graph, "763412", inputs, fixture_bounds={"countries": [-180, -90, 180, 90]})
    proof = {"safe-inner-area:intersects:sa_rivers:countries:NAME_EN:Chile": [-100, -50, -70, -20]}
    graph["definition"]["nodes"][1]["inputs"]["area"] = {"bbox": [-100, -50, -70, -20]}
    authorize(graph, "763412", inputs, fixture_bounds=proof)
    for field, value in [
        ("joinType", "left"),
        ("predicate", "within"),
        ("area", {"bbox": [-99, -49, -71, -21]}),
    ]:
        bad = copy.deepcopy(graph)
        bad["definition"]["nodes"][1]["inputs"][field] = value
        with pytest.raises(Blocked):
            authorize(bad, "763412", inputs, fixture_bounds=proof)


def test_measured_zero_length_diagnostic_uses_field_lineage_not_name():
    inputs = {"na_railways": {"collectionId": "rail", "itemId": "fixture", "assetKey": "data"}}
    graph = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [
                {
                    "id": "m",
                    "type": "processor",
                    "processId": "vector-measure",
                    "inputs": {
                        "source": inputs["na_railways"],
                        "measure": "length",
                        "unit": "km",
                        "outputField": "unknown_km",
                    },
                },
                {
                    "id": "f",
                    "type": "processor",
                    "processId": "vector-filter",
                    "inputs": {
                        "source": {"$output": {"nodeId": "m"}},
                        "predicates": [{"field": "unknown_km", "operator": "gt", "value": 0}],
                    },
                },
            ]
        },
    }
    authorize(graph, "310610", inputs)
    bad = copy.deepcopy(graph)
    bad["definition"]["nodes"][1]["inputs"]["predicates"][0]["value"] = 1
    with pytest.raises(Blocked):
        authorize(bad, "310610", inputs)
    bad = copy.deepcopy(graph)
    bad["definition"]["nodes"][1]["inputs"]["source"] = inputs["na_railways"]
    with pytest.raises(Blocked):
        authorize(bad, "310610", inputs)
