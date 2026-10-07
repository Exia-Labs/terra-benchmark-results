from copy import deepcopy

import pytest

from terra_bench.common import Blocked
from terra_bench.fixtures import ROW_ID
from terra_bench.lineage import record_identity_field
from terra_bench.policy import authorize, identity, trusted_reuse


def tiled():
    inputs = {k: {"collectionId": "blue-generated--" + k, "itemId": k, "assetKey": "data"}
              for k in ("towns", "snow")}
    nodes = [{"id": k, "type": "source", "selection": v} for k, v in inputs.items()]
    for i in range(2):
        nodes += [
            {"id": f"f{i}", "type": "processor", "processId": "vector-filter", "inputs": {
                "source": {"$output": {"nodeId": "towns"}}, "area": {"bbox": [i, 0, i + 1, 1]},
                "predicates": [{"field": "pop_2010", "operator": "gt", "value": 5000}]}},
            {"id": f"s{i}", "type": "processor", "processId": "raster-sample", "inputs": {
                "features": {"$output": {"nodeId": f"f{i}"}},
                "rasters": {"snow_inches": {"$output": {"nodeId": "snow"}}}}},
        ]
    nodes += [
        {"id": "merge", "type": "processor", "processId": "vector-merge", "inputs": {
            "sources": [{"$output": {"nodeId": f"s{i}"}} for i in range(2)]}},
        {"id": "qualifying", "type": "processor", "processId": "vector-filter", "inputs": {
            "source": {"$output": {"nodeId": "merge"}},
            "predicates": [{"field": "snow_inches", "operator": "gt", "value": 36}]}},
    ]
    selected = {"collectionId": "blue-generated--result", "itemId": "selected", "assetKey": "data"}
    manifest = {"valid": True, "readiness": {"status": "ready"}, "approvalDigest": "digest",
                "definition": {"nodes": nodes}}
    snapshot = {"workflows": [{"id": "w", "manifest": manifest, "nodes": [
        {"node_id": "qualifying", "status": "succeeded", "outputs": {"result": selected}},
    ]}], "artifacts": [selected]}
    fixtures = {"assets": {"towns": {"fields": [{"name": ROW_ID}, {"name": "pop_2010"}]}, "snow": {}}}
    return snapshot, inputs, selected, fixtures


def test_completed_tiling_has_provenance_without_granting_execution_permission():
    snapshot, inputs, selected, fixtures = tiled()
    manifest = snapshot["workflows"][0]["manifest"]
    with pytest.raises(Blocked):
        authorize(manifest, "333321", inputs)
    assert not trusted_reuse(snapshot, "333321", inputs)
    assert identity(selected) in {identity(v) for v in trusted_reuse(snapshot, "333321", inputs, for_grading=True)}
    assert record_identity_field(snapshot, selected, inputs, fixtures, "towns") == ROW_ID


@pytest.mark.parametrize("mutation", ["untrusted_source", "threshold", "remapping", "unsupported_processor"])
def test_grading_lineage_does_not_trust_unrelated_sources_or_rewritten_measurements(mutation):
    snapshot, inputs, selected, fixtures = tiled()
    snapshot = deepcopy(snapshot)
    nodes = snapshot["workflows"][0]["manifest"]["definition"]["nodes"]
    if mutation == "untrusted_source":
        nodes[0]["selection"]["itemId"] = "unknown"
    elif mutation == "threshold":
        nodes[-1]["inputs"]["predicates"][0]["value"] = 35
    elif mutation == "remapping":
        nodes[-2]["inputs"]["fieldMappings"] = {"0": {ROW_ID: "different"}}
    else:
        nodes[-2]["processId"] = "unrecognized"
    if mutation == "remapping":
        # Authentic inputs are insufficient: inconsistent per-branch names fail
        # the separate identity check before exact feature grading can pass.
        assert record_identity_field(snapshot, selected, inputs, fixtures, "towns") is None
    else:
        assert not trusted_reuse(snapshot, "333321", inputs, for_grading=True)
