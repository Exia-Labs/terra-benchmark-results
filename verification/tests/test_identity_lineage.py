from copy import deepcopy

import geopandas as gpd
from shapely.geometry import Point, box

from terra_bench.fixtures import ROW_ID
from terra_bench.grading import check_membership
from terra_bench.lineage import record_identity_field


def example():
    inputs = {k: {"collectionId": "blue-generated--" + k, "itemId": k, "assetKey": "data"}
              for k in ("facilities", "countries", "migration")}
    fixtures = {"assets": {k: {"fields": [{"name": ROW_ID}, {"name": "code"}, {"name": "2023"}]}
                           for k in inputs}}
    output = {"collectionId": "blue-generated--selected", "itemId": "selected", "assetKey": "data"}
    nodes = [{"id": k, "type": "source", "selection": v} for k, v in inputs.items()]
    nodes.append({"id": "join", "type": "processor", "processId": "vector-spatial-join", "inputs": {
        "target": {"$output": {"nodeId": "facilities"}}, "join": {"$output": {"nodeId": "countries"}},
        "predicate": "within", "matchMode": "one-to-many"}})
    snapshot = {"workflows": [{"id": "wf", "manifest": {"definition": {"nodes": nodes}},
        "nodes": [{"node_id": "join", "status": "succeeded", "outputs": {"result": output}}]}],
        "artifacts": [output]}
    return snapshot, output, inputs, fixtures


def test_spatial_join_suffix_preserves_exact_original_feature_identity():
    snapshot, selection, inputs, fixtures = example()
    field = record_identity_field(snapshot, selection, inputs, fixtures, "facilities")
    assert field == ROW_ID + "_target"
    facilities = gpd.GeoDataFrame({ROW_ID: ["facilities:1"]}, geometry=[Point(1, 1)], crs=4326)
    countries = gpd.GeoDataFrame({ROW_ID: ["countries:9"]}, geometry=[box(0, 0, 2, 2)], crs=4326)
    actual = gpd.sjoin(facilities, countries, predicate="within", lsuffix="target", rsuffix="join")
    assert actual[field].tolist() == facilities[ROW_ID].tolist()
    assert check_membership(actual[field], facilities[ROW_ID])["pass"]
    assert not check_membership(actual[ROW_ID + "_join"], facilities[ROW_ID])["pass"]
    assert actual.geometry.iloc[0].equals(facilities.geometry.iloc[0])


def test_bivariate_classification_preserves_source_identity():
    snapshot, selection, inputs, fixtures = example()
    node = snapshot["workflows"][0]["manifest"]["definition"]["nodes"][-1]
    node.update(processId="vector-bivariate-classify", inputs={"source": {"$output": {"nodeId": "facilities"}}})
    assert record_identity_field(snapshot, selection, inputs, fixtures, "facilities") == ROW_ID


def test_measurement_preserves_original_geometry_identity_and_rejects_overwrite():
    snapshot, selection, inputs, fixtures = example()
    node = snapshot['workflows'][0]['manifest']['definition']['nodes'][-1]
    node.update(processId='vector-measure', inputs={'source': {'$output': {'nodeId':'facilities'}},
        'measure':'area','unit':'km2','outputField':'country_area'})
    assert record_identity_field(snapshot, selection, inputs, fixtures, 'facilities') == ROW_ID
    node['inputs']['outputField'] = ROW_ID
    assert record_identity_field(snapshot, selection, inputs, fixtures, 'facilities') is None


def test_nearest_distance_tracks_source_not_target_identity_and_no_overwrite():
    snapshot, selection, inputs, fixtures = example()
    node = snapshot['workflows'][0]['manifest']['definition']['nodes'][-1]
    node.update(processId='vector-nearest-distance', inputs={
        'source': {'$output': {'nodeId': 'facilities'}},
        'targets': {'$output': {'nodeId': 'countries'}},
        'distanceCrs': 'EPSG:3857', 'outputField': 'distance_m'})
    assert record_identity_field(snapshot, selection, inputs, fixtures, 'facilities') == ROW_ID
    assert record_identity_field(snapshot, selection, inputs, fixtures, 'countries') is None
    node['inputs']['outputField'] = ROW_ID
    assert record_identity_field(snapshot, selection, inputs, fixtures, 'facilities') is None


def test_identity_is_not_borrowed_from_wrong_geometry_side():
    snapshot, selection, inputs, fixtures = example()
    args = snapshot["workflows"][0]["manifest"]["definition"]["nodes"][-1]["inputs"]
    args["target"], args["join"] = args["join"], args["target"]
    assert record_identity_field(snapshot, selection, inputs, fixtures, "facilities") is None


def test_identity_suffix_survives_immutable_artifact_reuse():
    snapshot, selection, inputs, fixtures = example()
    final = {**selection, "itemId": "filtered"}
    snapshot["artifacts"].append(final)
    snapshot["workflows"].append({"id": "second", "manifest": {"definition": {"nodes": [
        {"id": "s", "type": "source", "selection": selection},
        {"id": "p", "type": "processor", "processId": "vector-filter", "inputs": {"source": {"$output": {"nodeId": "s"}}}},
    ]}}, "nodes": [{"node_id": "p", "status": "succeeded", "outputs": {"result": final}}]})
    assert record_identity_field(snapshot, final, inputs, fixtures, "facilities") == ROW_ID + "_target"
    broken = deepcopy(snapshot)
    broken["workflows"][1]["manifest"]["definition"]["nodes"][0]["selection"] = {
        **selection, "itemId": "unknown",
    }
    assert record_identity_field(broken, final, inputs, fixtures, "facilities") is None


def test_attribute_join_copies_only_declared_fields():
    snapshot, selection, inputs, fixtures = example()
    node = snapshot["workflows"][0]["manifest"]["definition"]["nodes"][-1]
    node["processId"] = "table-attribute-join"
    node["inputs"] = {"vector": {"$output": {"nodeId": "facilities"}}, "table": {"$output": {"nodeId": "migration"}},
                      "vectorKey": "code", "tableKey": "code", "fields": ["2023"]}
    assert record_identity_field(snapshot, selection, inputs, fixtures, "facilities") == ROW_ID
    node["inputs"]["fields"].append(ROW_ID)
    assert record_identity_field(snapshot, selection, inputs, fixtures, "facilities") == ROW_ID + "_x"


def test_aggregate_spatial_join_retains_target_identity_not_join_identity():
    snapshot, selection, inputs, fixtures = example()
    args = snapshot["workflows"][0]["manifest"]["definition"]["nodes"][-1]["inputs"]
    args.update(matchMode="aggregate", aggregations=[{"field": "code", "operation": "count", "outputField": "matches"}])
    assert record_identity_field(snapshot, selection, inputs, fixtures, "facilities") == ROW_ID
    args["aggregations"][0]["outputField"] = ROW_ID
    assert record_identity_field(snapshot, selection, inputs, fixtures, "facilities") is None


def test_empty_aggregate_list_retains_join_suffix_contract():
    snapshot, selection, inputs, fixtures = example()
    snapshot["workflows"][0]["manifest"]["definition"]["nodes"][-1]["inputs"].update(matchMode="aggregate", aggregations=[])
    assert record_identity_field(snapshot, selection, inputs, fixtures, "facilities") == ROW_ID + "_target"


def test_merge_remapping_tracks_original_identity_and_rejects_collisions():
    snapshot, selection, inputs, fixtures = example()
    final = {**selection, "itemId": "renamed"}
    snapshot["artifacts"].append(final)
    args = {"sources": [selection, selection], "fieldMappings": {
        "0": {ROW_ID + "_target": ROW_ID}, "1": {ROW_ID + "_target": ROW_ID}}}
    snapshot["workflows"].append({"id": "second", "manifest": {"definition": {"nodes": [
        {"id": "merge", "type": "processor", "processId": "vector-merge", "inputs": args}]}},
        "nodes": [{"node_id": "merge", "status": "succeeded", "outputs": {"result": final}}]})
    assert record_identity_field(snapshot, final, inputs, fixtures, "facilities") == ROW_ID
    # Omitting one branch's rename cannot establish a consistent identity field.
    args["fieldMappings"].pop("1")
    assert record_identity_field(snapshot, final, inputs, fixtures, "facilities") is None
    args["fieldMappings"]["1"] = {ROW_ID + "_target": ROW_ID}
    args["fieldMappings"]["0"]["code_target"] = ROW_ID
    assert record_identity_field(snapshot, final, inputs, fixtures, "facilities") is None
    args["fieldMappings"]["0"] = {ROW_ID + "_target": "blue_source_index"}
    assert record_identity_field(snapshot, final, inputs, fixtures, "facilities") is None
