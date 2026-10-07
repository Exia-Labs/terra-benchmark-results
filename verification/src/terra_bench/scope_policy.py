"""Execution permission, deliberately independent of expected numerical answers."""

from .common import Blocked


def authorize_scope(manifest, inputs, reused=(), *, processors=None, provenance_only=False):
    from .policy import effective_nodes, identity, walk

    if manifest.get("valid") is not True:
        raise Blocked("Approval policy: workflow is not validated.")
    if not provenance_only and manifest.get("readiness", {}).get("status") != "ready":
        raise Blocked("Approval policy: explicit reduced or unavailable work is not preauthorized.")
    nodes = list(effective_nodes(manifest))
    if not nodes or len(nodes) > 1000:
        raise Blocked("Approval policy: missing or unbounded graph.")
    allowed = {identity(v) for v in inputs.values()} | {identity(v) for v in reused}
    ids = {n["id"] for n in nodes}
    for node in nodes:
        if node.get("type") not in {"source", "processor", "output", "review"}:
            raise Blocked("Approval policy: unknown executable node type.")
        if (
            node.get("type") == "processor"
            and processors is not None
            and node.get("processId") not in processors
        ):
            raise Blocked("Approval policy: processor is not available to the evaluated profile.")
        for value in walk(node):
            if not isinstance(value, dict):
                continue
            if value.get("sourceType") == "catalog-query" or any(k in value for k in ("url", "href")):
                raise Blocked("Approval policy: external sources are not permitted.")
            if isinstance(value.get("features"), list):
                raise Blocked("Approval policy: injected feature data is not permitted.")
            if "collectionId" in value and identity(value) not in allowed:
                raise Blocked("Approval policy: input is not a fixture or verified task-owned derivative.")
            if "$output" in value and value["$output"].get("nodeId") not in ids:
                raise Blocked("Approval policy: dangling output reference.")
        if node.get("type") == "source" and identity(node.get("selection", {})) not in allowed:
            raise Blocked("Approval policy: source does not name an exact allowed asset.")
    digest = manifest.get("approvalDigest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise Blocked("Approval policy: exact approval digest is missing.")
    return {"decision": "approve", "approvalDigest": digest, "acceptScopeChanges": False}
