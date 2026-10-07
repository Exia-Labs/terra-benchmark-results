"""A renamed capacity weight must not acquire the country-selection threshold."""

import copy

import pytest

from terra_bench.common import Blocked
from terra_bench.heat_tasks import GRID, RADIUS_M
from terra_bench.policy import authorize, measurement_rules


def graph(task, expression="w"):
    selection = {"collectionId": "power", "itemId": "one", "assetKey": "data"}
    nodes = [
        {"id": "weight", "type": "processor", "processId": "vector-field-calculate", "inputs": {
            "source": selection, "calculations": [{"fields": {"w": "DsgAttr02"},
                "expression": expression, "outputField": "capacity", "unit": "MW"}]}},
        {"id": "valid", "type": "processor", "processId": "vector-filter", "inputs": {
            "source": {"$output": {"nodeId": "weight"}},
            "predicates": [{"field": "capacity", "operator": "gte", "value": 0}]}},
        {"id": "out", "type": "output", "source": {"nodeId": "valid"}},
    ]
    return {"valid": True, "approvalDigest": "exact", "readiness": {"status": "ready"},
            "definition": {"nodes": nodes}}, {"power_stations": selection}


@pytest.mark.parametrize("task,expression", [("911650", "w"), ("470604", "w + 0")])
def test_weight_identity_retains_nonnegative_rule(task, expression):
    manifest, inputs = graph(task, expression)
    assert measurement_rules(manifest, task, [])["valid"]["capacity"] == ("gte", 0)
    assert authorize(manifest, task, inputs)["approvalDigest"] == "exact"
    bad = copy.deepcopy(manifest)
    bad["definition"]["nodes"][1]["inputs"]["predicates"][0]["value"] = 100
    with pytest.raises(Blocked, match="threshold"):
        authorize(bad, task, inputs)


@pytest.mark.parametrize("expression", ["w*2", "abs(w)", "w+1", "0-w"])
def test_changed_weights_do_not_gain_identity_rule(expression):
    manifest, inputs = graph("911650", expression)
    assert measurement_rules(manifest, "911650", [])["valid"]["capacity"] != ("gte", 0)
    with pytest.raises(Blocked):
        authorize(manifest, "911650", inputs)


def test_country_ratio_still_keeps_its_strict_threshold():
    manifest, inputs = graph("911650", "r/t")
    calc = manifest["definition"]["nodes"][0]["inputs"]["calculations"][0]
    calc.update(fields={"r": "rural", "t": "total"}, unit="ratio")
    assert measurement_rules(manifest, "911650", [])["valid"]["capacity"] == ("gt", .5)
    with pytest.raises(Blocked):
        authorize(manifest, "911650", inputs)


def test_negative_weight_audit_cannot_feed_a_published_result():
    manifest, inputs = graph("911650")
    audit = {"id": "excluded", "type": "processor", "processId": "vector-filter", "inputs": {
        "source": {"$output": {"nodeId": "weight"}}, "combine": "any",
        "predicates": [{"field": "capacity", "operator": "is-null"},
                       {"field": "capacity", "operator": "lt", "value": 0}]}}
    manifest["definition"]["nodes"].append(audit)
    authorize(manifest, "911650", inputs)
    published = copy.deepcopy(manifest)
    published["definition"]["nodes"][2]["source"]["nodeId"] = "excluded"
    with pytest.raises(Blocked):
        authorize(published, "911650", inputs)
    missing_contract = copy.deepcopy(manifest)
    missing_contract["definition"]["nodes"].pop(2)
    with pytest.raises(Blocked):
        authorize(missing_contract, "911650", inputs)
    changed = copy.deepcopy(manifest)
    changed["definition"]["nodes"][-1]["inputs"]["predicates"][1]["value"] = 10
    with pytest.raises(Blocked):
        authorize(changed, "911650", inputs)


def test_weight_rule_survives_graph_order_and_authorized_artifact_reuse():
    manifest, inputs = graph("911650")
    manifest["definition"]["nodes"].reverse()
    assert measurement_rules(manifest, "911650", [])["valid"]["capacity"] == ("gte", 0)
    artifact = {"collectionId": "generated", "itemId": "one", "assetKey": "data",
                "measurementRules": {"capacity": ("gte", 0)}}
    node = next(n for n in manifest["definition"]["nodes"] if n["id"] == "valid")
    node["inputs"]["source"] = {k: artifact[k] for k in inputs["power_stations"]}
    assert measurement_rules(manifest, "911650", [artifact])["valid"]["capacity"] == ("gte", 0)


@pytest.mark.parametrize("expression,allowed", [("w", True), ("w+0", True), ("w*2", False)])
def test_density_accepts_only_proven_identity_weight_alias(expression, allowed):
    manifest, inputs = graph("470604", expression)
    manifest["definition"]["nodes"].append({"id": "heat", "type": "processor", "processId": "point-density",
        "inputs": {"source": {"$output": {"nodeId": "valid"}}, "weightField": "capacity",
                   "weightUnit": "MW", "grid": GRID, "radiusM": RADIUS_M}})
    if allowed:
        authorize(manifest, "470604", inputs)
    else:
        with pytest.raises(Blocked):
            authorize(manifest, "470604", inputs)


def test_join_carries_right_measurement_and_suffixes_known_collisions():
    left = {"collectionId": "left", "itemId": "one", "assetKey": "data", "measurementRules": {"left": ("gt", 5), "collision": ("gt", 5)}}
    right = {"collectionId": "right", "itemId": "one", "assetKey": "data", "measurementRules": {"forest_delta_pct": ("lt", 0), "collision": ("lt", 0)}}
    inputs = {"target": {k: left[k] for k in ("collectionId", "itemId", "assetKey")},
              "join": {k: right[k] for k in ("collectionId", "itemId", "assetKey")}, "matchMode": "first"}
    manifest = {"definition": {"nodes": [{"id": "joined", "type": "processor", "processId": "vector-spatial-join", "inputs": inputs}]}}
    rules = measurement_rules(manifest, "470604", [left, right])["joined"]
    assert rules == {"left": ("gt", 5), "forest_delta_pct": ("lt", 0),
                     "collision_target": ("gt", 5), "collision_join": ("lt", 0)}
    assert "forest_delta_pct" not in measurement_rules(manifest, "470604", [left])["joined"]
    inputs.update(matchMode="aggregate", aggregations=[{"field": "x", "operation": "count", "outputField": "n"}])
    assert "forest_delta_pct" not in measurement_rules(manifest, "470604", [left, right])["joined"]


@pytest.mark.parametrize("defect", ["unit", "field", "source", "missing", "unproven"])
def test_identity_alias_does_not_relax_weight_contract(defect):
    manifest, inputs = graph("470604")
    source = {"$output": {"nodeId": "valid"}}
    if defect == "unit":
        manifest["definition"]["nodes"][0]["inputs"]["calculations"][0]["unit"] = "kW"
    elif defect == "field":
        manifest["definition"]["nodes"][0]["inputs"]["calculations"][0]["fields"] = {"w": "not_capacity"}
    elif defect == "source":
        inputs["countries"] = {"collectionId": "countries", "itemId": "one", "assetKey": "data"}
        manifest["definition"]["nodes"][0]["inputs"]["source"] = inputs["countries"]
    elif defect == "missing":
        source = {"$output": {"nodeId": "absent"}}
    else:
        source = inputs["power_stations"]
    manifest["definition"]["nodes"].append({"id": "heat", "type": "processor", "processId": "point-density",
        "inputs": {"source": source, "weightField": "capacity", "weightUnit": "MW", "grid": GRID, "radiusM": RADIUS_M}})
    with pytest.raises(Blocked):
        authorize(manifest, "470604", inputs)


@pytest.mark.parametrize("expression,operator", [("old-new", "gt"), ("new-old", "lt")])
def test_signed_forest_difference_preserves_decline_direction(expression, operator):
    manifest, inputs = graph("470604")
    calculation = manifest["definition"]["nodes"][0]["inputs"]["calculations"][0]
    calculation.update(fields={"old": "1990", "new": "2021"}, expression=expression,
                       outputField="difference", unit="percentage points")
    predicate = manifest["definition"]["nodes"][1]["inputs"]["predicates"][0]
    predicate.update(field="difference", operator=operator)
    authorize(manifest, "470604", inputs)
    predicate["operator"] = "lt" if operator == "gt" else "gt"
    with pytest.raises(Blocked, match="threshold"):
        authorize(manifest, "470604", inputs)


@pytest.mark.parametrize("fields,expression", [({"old": "2020", "new": "2021"}, "old-new"),
                                            ({"old": "1990", "new": "2021"}, "old-new+1")])
def test_changed_year_or_offset_cannot_reverse_decline_rule(fields, expression):
    manifest, inputs = graph("470604")
    calculation = manifest["definition"]["nodes"][0]["inputs"]["calculations"][0]
    calculation.update(fields=fields, expression=expression, outputField="difference", unit="percentage points")
    manifest["definition"]["nodes"][1]["inputs"]["predicates"][0].update(field="difference", operator="gt")
    with pytest.raises(Blocked):
        authorize(manifest, "470604", inputs)
