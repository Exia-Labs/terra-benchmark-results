import copy

import pytest

from terra_bench.common import Blocked
from terra_bench.policy import authorize
from terra_bench.population_tasks import POPULATION_TASKS


def graph(task):
    key = POPULATION_TASKS[task]["raster"]
    source = {"collectionId": key, "itemId": "fixture", "assetKey": "data"}
    proposal = {"valid": True, "readiness": {"status": "ready"}, "approvalDigest": "exact",
                "definition": {"nodes": [{"id": "density", "type": "processor", "processId": "raster-count-density",
                    "inputs": {"source": source, "band": 1, "countUnit": "people"}}]}}
    return proposal, {key: source}


@pytest.mark.parametrize("task", ["551060", "819657"])
def test_equivalent_fused_count_density_is_allowed(task):
    proposal, inputs = graph(task)
    original = copy.deepcopy(proposal)
    assert authorize(proposal, task, inputs)["approvalDigest"] == "exact"
    assert proposal == original


@pytest.mark.parametrize("change", ["band", "unit", "foreign", "derived", "crop"])
def test_fused_path_still_requires_original_count_source(change):
    proposal, inputs = graph("551060")
    args = proposal["definition"]["nodes"][0]["inputs"]
    if change == "band":
        args["band"] = 2
    elif change == "unit":
        args["countUnit"] = "events"
    elif change == "foreign":
        args["source"] = {"collectionId": "elsewhere", "itemId": "fixture", "assetKey": "data"}
    elif change == "derived":
        # A permitted unrelated fixture is still not the original population input.
        inputs["other"] = {"collectionId": "other", "itemId": "one", "assetKey": "data"}
        args["source"] = inputs["other"]
    else:
        args["area"] = {"bbox": [10, -10, 15, -5]}
    with pytest.raises(Blocked):
        authorize(proposal, "551060", inputs)
