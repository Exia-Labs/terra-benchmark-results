"""Trace source row identity through documented, frozen processor field contracts.

This resolves column naming only. It never chooses a field by comparing its values
with the oracle, and never changes the required source identities or geometries.
"""
from __future__ import annotations

from .fixtures import ROW_ID
from .policy import effective_nodes, identity


def record_identity_field(snapshot, selection, inputs, fixtures, base):
    sources = {identity(value): key for key, value in inputs.items()}
    workflows = {w["id"]: {n["id"]: n for n in effective_nodes(w["manifest"])}
                 for w in snapshot.get("workflows", [])}
    producers = {}
    for workflow in snapshot.get("workflows", []):
        definitions = workflows[workflow["id"]]
        for node in workflow.get("nodes", []):
            nid = node.get("node_id")
            # Output aliases/source pass-throughs do not define a new schema.
            if node.get("status") != "succeeded" or definitions.get(nid, {}).get("type") != "processor":
                continue
            for output in (node.get("outputs") or {}).values():
                if isinstance(output, dict) and output.get("itemId"):
                    for asset in snapshot.get("artifacts", []):
                        if all(asset.get(k) == output.get(k) for k in ("collectionId", "itemId")):
                            producers[identity(asset)] = (workflow["id"], nid)
    visiting = set()
    cache = {}

    def dataset(value):
        key = identity(value)
        if key in sources:
            name = sources[key]
            columns = {f["name"] for f in fixtures["assets"].get(name, {}).get("fields", [])}
            if name == base:
                columns.add(ROW_ID)
            return (ROW_ID if name == base else None), columns
        if key in producers:
            return node_state(*producers[key])
        return None, set()

    def value_state(wid, value):
        if not isinstance(value, dict):
            return None, set()
        if "$output" in value:
            return node_state(wid, value["$output"]["nodeId"])
        if "value" in value:
            return value_state(wid, value["value"])
        return dataset(value)

    def joined(left, right, suffixes):
        fid, left_columns = left
        right_columns = right[1]
        common = left_columns & right_columns
        columns = {c + suffixes[0] if c in common else c for c in left_columns}
        columns |= {c + suffixes[1] if c in common else c for c in right_columns}
        return (fid + suffixes[0] if fid in common else fid), columns

    def node_state(wid, nid):
        key = (wid, nid)
        if key in cache:
            return cache[key]
        if key in visiting:
            return None, set()
        visiting.add(key)
        node = workflows.get(wid, {}).get(nid, {})
        args = node.get("inputs", {})
        kind = node.get("processId")
        result = (None, set())
        if node.get("type") == "source":
            result = dataset(node.get("selection", {}))
        elif node.get("type") == "output":
            result = node_state(wid, node.get("source", {}).get("nodeId"))
        elif kind in {"vector-filter", "vector-classify", "vector-bivariate-classify", "vector-field-calculate", "vector-measure", "vector-nearest-distance"}:
            result = value_state(wid, args.get("source"))
            if kind in {"vector-measure", "vector-nearest-distance"}:
                field = args.get('outputField', 'measurement')
                # The production measurement processor never overwrites columns.
                result = (None, set()) if field in result[1] else (result[0], result[1] | {field})
            elif kind == "vector-classify":
                result = result[0], result[1] | {args.get("outputField", "value_class")}
            elif kind == "vector-bivariate-classify":
                field = args.get("outputField", "bivariate_class")
                result = result[0], result[1] | {field, field + "_x", field + "_y"}
            elif kind == "vector-field-calculate":
                result = result[0], result[1] | {c["outputField"] for c in args.get("calculations", [])}
        elif kind == 'vector-overlay':
            fid, columns = value_state(wid, args.get('primary'))
            prefix = args.get('primary_prefix', 'primary_')
            result = (prefix + fid if fid else None), {prefix+c for c in columns}
        elif kind == "raster-sample":
            fid, columns = value_state(wid, args.get("features"))
            result = fid, columns | set(args.get("rasters", {}))
        elif kind == "vector-merge":
            branches = [value_state(wid, value) for value in args.get("sources", [])]
            remapped = []
            for index, (fid, columns) in enumerate(branches):
                mapping = (args.get("fieldMappings") or {}).get(str(index), {})
                names = [mapping.get(c, c) for c in columns]
                new_fid = mapping.get(fid, fid)
                # Match the processor's per-source rename contract, not values
                # chosen because they happen to match an expected answer. Reject
                # duplicate destinations and the synthetic overwritten index.
                if len(names) != len(set(names)) or new_fid == "blue_source_index" or "geometry" in mapping:
                    remapped.append((None, set()))
                else:
                    remapped.append((new_fid, set(names) | {"blue_source_index"}))
            branches = remapped
            if branches and branches[0][0] and all(b[0] == branches[0][0] for b in branches):
                result = branches[0][0], set.intersection(*(b[1] for b in branches))
        elif kind == "vector-spatial-join":
            if args.get("matchMode", "one-to-many") in {"one-to-many", "first"}:
                result = joined(value_state(wid, args.get("target")), value_state(wid, args.get("join")),
                                ("_target", "_join"))
            elif args.get("matchMode") == "aggregate":
                if args.get("aggregations"):
                    fid, columns = value_state(wid, args.get("target"))
                    outputs = {a["outputField"] for a in args["aggregations"]}
                    if not columns & outputs:
                        result = fid, columns | outputs
                else:
                    result = joined(value_state(wid, args.get("target")), value_state(wid, args.get("join")),
                                    ("_target", "_join"))
        elif kind == "table-attribute-join":
            left = value_state(wid, args.get("vector"))
            right = value_state(wid, args.get("table"))
            copied = set(args.get("fields") or right[1]) | {args.get("tableKey")}
            copied.discard(None)
            # Pandas retains a shared same-name join key once (without suffix).
            shared_key = args.get("vectorKey") if args.get("vectorKey") == args.get("tableKey") else None
            left_cols, right_cols = left[1] - {shared_key}, right[1] & copied - {shared_key}
            fid, columns = joined((left[0], left_cols), (right[0], right_cols), ("_x", "_y"))
            result = fid, columns | ({shared_key} if shared_key else set())
        visiting.remove(key)
        cache[key] = result
        return result

    return dataset(selection)[0]
