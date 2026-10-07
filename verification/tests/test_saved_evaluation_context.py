"""Reconcile independently saved execution context without inventing map evidence."""

import copy

import pytest

from terra_bench.common import Blocked, timestamp
from terra_bench.map_bindings import bind_evaluation_context, verify_map_binding


def fixture():
    artifact = {"collectionId": "collection", "itemId": "item", "assetKey": "data"}
    scope = {"mapId": "map", "sessionId": "session"}
    attempt = {"deadline": timestamp("2026-01-01T00:01:00Z")}
    snapshot = {
        "run": {"session_id": "session"},
        "layers": {
            "map_layers": [
                {
                    "id": "layer",
                    "map_id": "map",
                    "availability": "available",
                    "deleted_at": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "json_data": {"provider": "blue-stac", **artifact},
                }
            ]
        },
    }
    return artifact, scope, attempt, snapshot


def test_saved_scope_and_deadline_complete_context_without_changing_receipts():
    artifact, scope, attempt, snapshot = fixture()
    before = copy.deepcopy(snapshot)
    complete = bind_evaluation_context(snapshot, scope, attempt)
    verify_map_binding(complete, artifact, "layer")
    assert snapshot == before
    assert complete["layers"] == snapshot["layers"]
    assert "mapDisplays" not in complete


@pytest.mark.parametrize("kind", ["map", "session", "run_session", "deadline"])
def test_conflicting_context_is_not_repaired_away(kind):
    _, scope, attempt, snapshot = fixture()
    snapshot["scope"] = dict(scope)
    if kind == "map":
        snapshot["scope"]["mapId"] = "foreign"
    if kind == "session":
        snapshot["scope"]["sessionId"] = "foreign"
    if kind == "run_session":
        snapshot["run"]["session_id"] = "foreign"
    if kind == "deadline":
        snapshot["evaluationDeadline"] = attempt["deadline"] + 20
    with pytest.raises(Blocked, match="context"):
        bind_evaluation_context(snapshot, scope, attempt)


@pytest.mark.parametrize("kind", ["missing", "late", "wrong_artifact"])
def test_context_does_not_manufacture_timely_output(kind):
    artifact, scope, attempt, snapshot = fixture()
    row = snapshot["layers"]["map_layers"][0]
    if kind == "missing":
        snapshot["layers"]["map_layers"] = []
    if kind == "late":
        row["created_at"] = "2026-01-01T00:02:00Z"
    if kind == "wrong_artifact":
        row["json_data"]["itemId"] = "other"
    with pytest.raises(Blocked):
        verify_map_binding(bind_evaluation_context(snapshot, scope, attempt), artifact, "layer")
