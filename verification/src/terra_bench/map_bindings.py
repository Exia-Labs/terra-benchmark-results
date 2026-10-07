"""Verify saved, authenticated map records, including direct artifact publication."""

from .common import Blocked, timestamp


def bind_evaluation_context(snapshot, scope, attempt):
    """Use the saved authenticated scope and attempt deadline; never invent receipts."""
    saved = snapshot.get("scope") or {}
    if not scope.get("mapId") or not scope.get("sessionId"):
        raise Blocked("Saved evaluation context lacks its authenticated map/session scope.")
    for key in ("mapId", "sessionId"):
        if saved.get(key) is not None and saved[key] != scope[key]:
            raise Blocked("Saved evaluation context conflicts with the authenticated scope receipt.")
    if snapshot.get("run", {}).get("session_id") not in (None, scope["sessionId"]):
        raise Blocked("Saved evaluation context belongs to a different agent session.")
    if snapshot.get("evaluationDeadline") not in (None, attempt["deadline"]):
        raise Blocked("Saved evaluation context conflicts with the immutable attempt deadline.")
    return {**snapshot, "scope": {"mapId": scope["mapId"], "sessionId": scope["sessionId"]},
            "evaluationDeadline": attempt["deadline"]}


def display_layer_ids(snapshot):
    """Bound collection to the current map; never follow arbitrary artifact URLs."""
    scope = snapshot.get("scope", {})
    layers = snapshot.get("layers")
    records = layers.get("map_layers", []) if isinstance(layers, dict) else []
    ids = {
        row["id"]
        for row in records
        if row.get("id")
        and row.get("map_id") == scope.get("mapId")
        and not row.get("deleted_at")
        and row.get("availability") == "available"
    }
    for workflow in snapshot.get("workflows", []):
        for node in workflow.get("nodes", []):
            value = (node.get("outputs") or {}).get("result") or {}
            layer = value.get("mapReceipt", {}).get("layerId")
            if layer:
                ids.add(layer)
    if len(ids) > 200:
        raise Blocked("Map display collection exceeds its 200-layer evidence bound.")
    return sorted(ids)


def verify_map_binding(snapshot, artifact, layer_id):
    if not isinstance(layer_id, str) or not layer_id:
        raise Blocked("Delivered map layer identity is missing.")
    keys = ("collectionId", "itemId", "assetKey")
    if not all(artifact.get(k) for k in keys):
        raise Blocked("Graded map artifact identity is incomplete.")
    layers = snapshot.get("layers")
    if isinstance(layers, dict) and isinstance(layers.get("map_layers"), list):
        matches = [r for r in layers["map_layers"] if r.get("id") == layer_id]
        if len(matches) != 1:
            raise Blocked("Delivered layer is absent or duplicated in the authenticated map.")
        row = matches[0]
        scope = snapshot.get("scope", {})
        binding = row.get("json_data") or {}
        if (
            not scope.get("mapId")
            or row.get("map_id") != scope["mapId"]
            or row.get("deleted_at")
            or row.get("availability") != "available"
            or binding.get("provider") != "blue-stac"
            or any(binding.get(k) != artifact[k] for k in keys)
        ):
            raise Blocked("Delivered map binding differs from the graded artifact or authorized map.")
        deadline = snapshot.get("evaluationDeadline")
        if deadline is not None and (not row.get("created_at") or timestamp(row["created_at"]) > deadline):
            raise Blocked("Map layer has no verified pre-deadline publication time.")
        return
    if snapshot.get("scope"):
        raise Blocked("Authenticated map records could not be collected.")
    # Workflow receipts remain useful for synthetic tests and diagnostic snapshots
    # without a map response. Live collection always supplies the authoritative map.
    for workflow in snapshot.get("workflows", []):
        for node in workflow.get("nodes", []):
            value = (node.get("outputs") or {}).get("result", {})
            if (
                value.get("mapReceipt", {}).get("layerId") == layer_id
                and all(value.get(k) == artifact[k] for k in keys)
                and workflow.get("verifiedMapOutputs", {}).get(node["node_id"]) is True
            ):
                return
    raise Blocked("Map has no verified binding to the graded artifact.")
