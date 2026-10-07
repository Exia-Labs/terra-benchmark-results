"""Conservative mechanical approval policy, frozen before any model result is observed.

This does not solve a task. It rejects out-of-scope execution; correctness is graded later.
"""

from __future__ import annotations

import math
from copy import deepcopy

from .bivariate_tasks import BIVARIATE_TASKS
from .change_tasks import CHANGE_TASKS
from .common import Blocked
from .contour_tasks import CONTOUR_TASKS
from .control_tasks import CONTROL_TASKS
from .county_tasks import COUNTY_GRID, COUNTY_HEAT_TASKS, COUNTY_RADIUS, COUNTY_TASKS
from .flood_tasks import FLOOD_TASKS
from .heat_tasks import GRID, HEAT_TASKS, RADIUS_M
from .map_tasks import INDICATORS, MAP_TASKS
from .overlay_tasks import OVERLAY_TASKS
from .population_tasks import POPULATION_TASKS
from .proximity_tasks import PROXIMITY_TASKS
from .regional_tasks import DERIVED, GROUP_COMPARISONS, REGIONAL, YEAR_OVERRIDES, unit_for, years_for
from .series_tasks import SERIES_TASKS
from .units import same_unit
from .water_tasks import DISTANCE_CRS, FIVE_MILES_M, WATER_SELECTIONS

ALLOWED_PROCESSORS = {
    "150069": {"raster-map-algebra", "raster-reclassify", "raster-polygonize", "vector-nearest-distance", "vector-filter", "table-group-statistics", "raster-statistics", "vector-dissolve"},
    "645898": {"vector-filter", "vector-spatial-join", "vector-dissolve", "table-group-statistics"},
    "154613": {"vector-nearest-distance", "vector-filter", "table-group-statistics"},
    "129699": {"vector-nearest-distance", "vector-filter", "vector-dissolve", "table-group-statistics"},
    "955741": {"vector-filter", "vector-spatial-join", "table-group-statistics"},
    "365343": {
        "vector-filter",
        "vector-measure",
        "table-attribute-join",
        "vector-spatial-join",
        "table-group-statistics",
    },
    "333321": {"vector-filter", "raster-sample", "table-group-statistics"},
    "130168": {"vector-filter", "table-attribute-join", "vector-spatial-join", "table-group-statistics"},
    "332083": {"vector-filter", "raster-sample", "table-group-statistics"},
    "417961": {"vector-filter", "vector-spatial-join", "table-group-statistics"},
}
for _task in PROXIMITY_TASKS:
    ALLOWED_PROCESSORS[_task] = {"vector-nearest-distance", "vector-filter", "table-group-statistics"}
for _task in FLOOD_TASKS:
    ALLOWED_PROCESSORS[_task] = {"raster-extract-band", "raster-align", "raster-map-algebra", "raster-cell-area", "raster-count-density", "raster-statistics", "raster-reclassify"}
COUNTRY_TASK_YEARS = {"806525": "2021", "429627": "2014", "918547": "2020", "977524": "2022"}
for _task in CONTROL_TASKS:
    ALLOWED_PROCESSORS[_task] = set()
for _task in OVERLAY_TASKS:
    ALLOWED_PROCESSORS[_task] = {"vector-filter", "raster-map-algebra", "raster-extract-band"}
    if OVERLAY_TASKS[_task].get("deriveDensity"):
        ALLOWED_PROCESSORS[_task] |= {"raster-count-density", "raster-cell-area"}
for _task in POPULATION_TASKS:
    ALLOWED_PROCESSORS[_task] = {"raster-cell-area", "raster-map-algebra", "raster-reclassify"}
    if POPULATION_TASKS[_task].get("points"):
        ALLOWED_PROCESSORS[_task] = {
            "distance-surface",
            "vector-filter",
            "raster-map-algebra",
            "raster-reclassify",
        }
    ALLOWED_PROCESSORS[_task].add("raster-statistics")
    if POPULATION_TASKS[_task].get("sourceQuantity") == "density":
        ALLOWED_PROCESSORS[_task].add("raster-cell-area")
    elif not POPULATION_TASKS[_task].get("points"):
        ALLOWED_PROCESSORS[_task].add("raster-count-density")
for _task in SERIES_TASKS:
    ALLOWED_PROCESSORS[_task] = {
        "table-attribute-join",
        "vector-filter",
        "vector-classify",
        "table-group-statistics",
    }
    if SERIES_TASKS[_task].get("bivariate"):
        ALLOWED_PROCESSORS[_task].add("vector-bivariate-classify")
for _task in COUNTY_TASKS:
    ALLOWED_PROCESSORS[_task] = {
        "table-attribute-join",
        "vector-filter",
        "vector-classify",
        "table-group-statistics",
    }
for _task in COUNTY_HEAT_TASKS:
    ALLOWED_PROCESSORS[_task] = {
        "table-attribute-join",
        "vector-filter",
        "vector-field-calculate",
        "vector-centroids",
        "vector-merge",
        "point-density",
        "table-group-statistics",
    }
for _task in COUNTRY_TASK_YEARS:
    ALLOWED_PROCESSORS[_task] = {
        "vector-filter",
        "table-attribute-join",
        "vector-spatial-join",
        "table-group-statistics",
        "vector-merge",
    }
ALLOWED_PROCESSORS["883928"] = {"vector-filter", "raster-sample", "table-group-statistics", "vector-merge"}
for _task in CONTOUR_TASKS:
    ALLOWED_PROCESSORS[_task] = {
        "raster-contours",
        "vector-filter",
        "table-group-statistics",
        "raster-statistics",
        "vector-dissolve",
    }
    if CONTOUR_TASKS[_task].get("deriveDensity"):
        ALLOWED_PROCESSORS[_task] |= {"raster-count-density", "raster-cell-area", "raster-map-algebra"}
    if CONTOUR_TASKS[_task].get("overlay"):
        ALLOWED_PROCESSORS[_task].add("raster-sample")
    if CONTOUR_TASKS[_task].get("overlaySelector"):
        ALLOWED_PROCESSORS[_task] |= {"vector-spatial-join", "table-attribute-join"}
    ALLOWED_PROCESSORS[_task].add("vector-classify")
    if CONTOUR_TASKS[_task].get("floodMask"):
        ALLOWED_PROCESSORS[_task] |= {"raster-extract-band", "raster-align", "raster-map-algebra", "raster-cell-area"}
ALLOWED_PROCESSORS["310610"] = {
    "vector-filter",
    "vector-overlay",
    "vector-dissolve",
    "vector-measure",
    "raster-map-algebra",
    "raster-reclassify",
    "raster-polygonize",
    "raster-statistics",
    "table-group-statistics",
}
ALLOWED_PROCESSORS["586288"] = {
    "vector-filter",
    "raster-point-proximity",
    "raster-statistics",
    "table-group-statistics",
}
ALLOWED_PROCESSORS["419069"] = {
    "vector-filter",
    "table-attribute-join",
    "vector-field-calculate",
    "vector-merge",
    "vector-dissolve",
    "vector-rasterize",
    "spatial-clip",
    "raster-count-density",
    "raster-cell-area",
    "raster-map-algebra",
    "raster-statistics",
    "table-group-statistics",
    "zonal-statistics",
}
ALLOWED_PROCESSORS["321268"] = {
    "spatial-clip",
    "raster-count-density",
    "raster-cell-area",
    "raster-align",
    "raster-map-algebra",
    "raster-statistics",
    "raster-reclassify",
}
for _task, _spec in BIVARIATE_TASKS.items():
    ALLOWED_PROCESSORS[_task] = {
        "table-attribute-join",
        "vector-field-calculate",
        "vector-bivariate-classify",
        "vector-filter",
        "table-group-statistics",
    }
    COUNTRY_TASK_YEARS[_task] = _spec["year"]
for _task in CHANGE_TASKS:
    ALLOWED_PROCESSORS[_task] = {
        "vector-filter",
        "table-attribute-join",
        "vector-field-calculate",
        "vector-spatial-join",
        "table-group-statistics",
    }
for _task in HEAT_TASKS:
    ALLOWED_PROCESSORS[_task] = {
        "vector-filter",
        "table-attribute-join",
        "vector-field-calculate",
        "vector-spatial-join",
        "table-group-statistics",
        "point-density",
    }
    if HEAT_TASKS[_task].get("nearLines"):
        ALLOWED_PROCESSORS[_task].add("vector-nearest-distance")
    if HEAT_TASKS[_task].get("raster"):
        ALLOWED_PROCESSORS[_task].add("raster-sample")
    if HEAT_TASKS[_task].get("predicate") == "intersects":
        ALLOWED_PROCESSORS[_task].add("vector-dissolve")
for _task, (_indicator, _) in MAP_TASKS.items():
    ALLOWED_PROCESSORS[_task] = {
        "table-attribute-join",
        "vector-classify",
        "table-group-statistics",
        "vector-filter",
        "vector-field-calculate",
    }
    COUNTRY_TASK_YEARS[_task] = INDICATORS[_indicator][1]
    COUNTRY_TASK_YEARS[_task] = YEAR_OVERRIDES.get(_task, COUNTRY_TASK_YEARS[_task])

GEOMETRY_DENSITY_TASKS = {task for task, spec in DERIVED.items() if spec[2] == "population_density"} | {
    task for task, spec in BIVARIATE_TASKS.items() if spec.get("derive") == "population_density"
}
for _task in GEOMETRY_DENSITY_TASKS:
    ALLOWED_PROCESSORS[_task].add("vector-measure")


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def selections(value):
    return [d for d in walk(value) if isinstance(d, dict) and "collectionId" in d]


def identity(value):
    return tuple(value.get(k) for k in ("collectionId", "itemId", "assetKey"))


def effective_nodes(manifest):
    return [
        {**deepcopy(n), **deepcopy(manifest.get("nodes", {}).get(n["id"], {}))}
        for n in manifest.get("definition", {}).get("nodes", [])
    ]


def source_roles(manifest, inputs, reused):
    """Trace geometry origin, not analytical truth, through supported transforms."""
    assets = {identity(value): {key} for key, value in inputs.items()}
    assets.update({identity(value): set(value.get("sourceRoles", [])) for value in reused})
    nodes = effective_nodes(manifest)
    roles = {}

    def origin(value):
        if not isinstance(value, dict):
            return set()
        if "value" in value:
            return origin(value["value"])
        if "$output" in value:
            return roles.get(value["$output"].get("nodeId"), set())
        return assets.get(identity(value), set())

    for _ in range(len(nodes) + 1):
        before = deepcopy(roles)
        for node in nodes:
            args = node.get("inputs", {})
            if node["type"] == "source":
                roles[node["id"]] = origin(node.get("selection", {}))
            elif node["type"] == "output":
                roles[node["id"]] = roles.get(node.get("source", {}).get("nodeId"), set())
            elif node.get("processId") == "vector-merge":
                roles[node["id"]] = set().union(*(origin(v) for v in args.get("sources", [])))
            elif node.get("processId") == "distance-surface":
                roles[node["id"]] = origin(args.get("source")) | origin(args.get("match"))
            elif node.get("processId") == "raster-map-algebra":
                roles[node["id"]] = set().union(*(origin(v) for v in args.get("sources", {}).values()))
            else:
                field = {
                    "vector-filter": "source",
                    "raster-sample": "features",
                    "vector-classify": "source",
                    "vector-field-calculate": "source",
                    "vector-bivariate-classify": "source",
                    "point-density": "source",
                    "vector-nearest-distance": "source",
                    "vector-measure": "source",
                    "vector-centroids": "source",
                    "vector-dissolve": "source",
                    "vector-overlay": "primary",
                    "raster-polygonize": "source",
                    "raster-point-proximity": "source",
                    "spatial-clip": "source",
                    "raster-align": "source",
                    "raster-extract-band": "source",
                    "vector-rasterize": "source",
                    "raster-cell-area": "source",
                    "raster-count-density": "source",
                    "raster-reclassify": "source",
                    "raster-contours": "source",
                    "vector-spatial-join": "target",
                    "table-attribute-join": "vector",
                }.get(node.get("processId"))
                roles[node["id"]] = origin(args.get(field)) if field else set()
        if roles == before:
            break
    return roles, origin


def unchanged_weight(calculation, spec):
    """Recognize a typed identity copy, not arbitrary weight transformations."""
    import ast

    fields = calculation.get("fields", {})
    if len(fields) != 1 or next(iter(fields.values())) != spec.get("weight") or calculation.get("unit") != spec.get("weightUnit"):
        return False
    alias = next(iter(fields))
    try:
        expression = ast.parse(calculation.get("expression", ""), mode="eval").body
    except (SyntaxError, TypeError):
        return False
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
        if isinstance(expression.right, ast.Constant) and type(expression.right.value) in (int, float) and expression.right.value == 0:
            expression = expression.left
        elif isinstance(expression.left, ast.Constant) and type(expression.left.value) in (int, float) and expression.left.value == 0:
            expression = expression.right
    return isinstance(expression, ast.Name) and expression.id == alias


def heat_calculation_rule(calculation, spec):
    """Respect the sign of an exact old/new difference, not its prose label."""
    import ast

    if unchanged_weight(calculation, spec):
        return ("gte", 0)
    if spec.get("derived") == "forest_change" and same_unit(calculation.get("unit"), "percentage points"):
        try:
            expression = ast.parse(calculation.get("expression", ""), mode="eval").body
        except (SyntaxError, TypeError):
            expression = None
        if (isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Sub)
                and isinstance(expression.left, ast.Name) and isinstance(expression.right, ast.Name)):
            fields = calculation.get("fields", {})
            compared = [fields.get(expression.left.id), fields.get(expression.right.id)]
            if compared == spec["years"]:
                return ("gt", 0)
    return (spec["operator"], spec["threshold"])


def measurement_rules(manifest, task, reused):
    """Carry policy semantics along actual data edges, including immutable reuse.

    These are derived by the evaluator from inspected graphs, never trusted from
    agent-authored artifact metadata. No field-name aliases or answer hints.
    """
    assets = {identity(v): v.get("measurementRules", {}) for v in reused}
    nodes = effective_nodes(manifest)
    rules = {}

    def upstream(value):
        if not isinstance(value, dict):
            return {}
        if "$output" in value:
            return rules.get(value["$output"].get("nodeId"), {})
        return assets.get(identity(value), {})

    for _ in range(len(nodes) + 1):
        before = deepcopy(rules)
        for node in nodes:
            settings = node.get("inputs", {})
            if node["type"] == "source":
                rules[node["id"]] = assets.get(identity(node.get("selection", {})), {})
            elif node.get("processId") == "vector-filter":
                rules[node["id"]] = upstream(settings.get("source"))
            elif (
                node.get("processId") == "vector-measure"
                and task == "310610"
                and settings.get("measure") == "length"
                and settings.get("unit") in {"m", "km"}
            ):
                rules[node["id"]] = {
                    **upstream(settings.get("source")),
                    settings.get("outputField", "measurement"): ("gt", 0),
                }
            elif (
                node.get("processId") == "vector-nearest-distance"
                and task in HEAT_TASKS
                and HEAT_TASKS[task].get("nearLines")
            ):
                rules[node["id"]] = {
                    **upstream(settings.get("source")),
                    settings.get("outputField"): ("lt", HEAT_TASKS[task]["threshold"]),
                }
            elif node.get("processId") == "vector-nearest-distance" and task in PROXIMITY_TASKS:
                rules[node["id"]] = {
                    **upstream(settings.get("source")),
                    settings.get("outputField"): ("lt", PROXIMITY_TASKS[task]["threshold"]),
                }
            elif node.get("processId") == "vector-nearest-distance" and task in {"154613", "129699", "150069"}:
                rules[node["id"]] = {**upstream(settings.get("source")),
                                      settings.get("outputField"): ("lt", {"154613": FIVE_MILES_M, "129699": 10000, "150069": 20000}[task])}
            elif node.get("processId") == "raster-sample" and task in {"333321", "332083", "883928"}:
                rules[node["id"]] = {
                    **upstream(settings.get("features")),
                    **{
                        field: ("gt", {"333321": 36, "332083": 1000, "883928": 12}[task])
                        for field in settings.get("rasters", {})
                    },
                }
            elif (
                node.get("processId") == "raster-sample"
                and task in HEAT_TASKS
                and HEAT_TASKS[task].get("raster")
            ):
                spec = HEAT_TASKS[task]
                rules[node["id"]] = {
                    **upstream(settings.get("features")),
                    **{field: (spec["operator"], spec["threshold"]) for field in settings.get("rasters", {})},
                }
            elif node.get("processId") == "vector-spatial-join" and task in (
                COUNTRY_TASK_YEARS.keys() | HEAT_TASKS.keys() | CHANGE_TASKS.keys() | {"955741", "645898"}
            ):
                left = upstream(settings.get("target"))
                right = upstream(settings.get("join"))
                # Ordinary joins preserve both sides; aggregated joins only
                # preserve target fields and their explicit aggregation outputs.
                if settings.get("matchMode", "one-to-many") == "aggregate" and settings.get("aggregations"):
                    joined = left
                else:
                    collisions = left.keys() & right.keys()
                    joined = {
                        **{f"{key}_target" if key in collisions else key: value for key, value in left.items()},
                        **{f"{key}_join" if key in collisions else key: value for key, value in right.items()},
                    }
                rules[node["id"]] = {
                    **joined,
                    **{
                        a["outputField"]: ("gt", 5 if task == "806525" else 0)
                        for a in settings.get("aggregations", [])
                        if a.get("operation") == "count"
                    },
                }
            elif node.get("processId") == "table-attribute-join":
                rules[node["id"]] = upstream(settings.get("vector"))
            elif node.get("processId") == "vector-field-calculate" and task in CHANGE_TASKS:
                spec = CHANGE_TASKS[task]
                rules[node["id"]] = {
                    **upstream(settings.get("source")),
                    **{
                        c["outputField"]: (
                            spec.get("operator", "lt"),
                            spec.get("threshold", 0.79 if task == "932053" else -0.03),
                        )
                        for c in settings.get("calculations", [])
                    },
                }
            elif node.get("processId") == "vector-field-calculate" and task in HEAT_TASKS:
                spec = HEAT_TASKS[task]
                rules[node["id"]] = {
                    **upstream(settings.get("source")),
                    **{
                        c["outputField"]: heat_calculation_rule(c, spec)
                        for c in settings.get("calculations", [])
                        if "threshold" in spec
                    },
                }
            elif node.get("processId") == "vector-merge":
                branches = [upstream(value) for value in settings.get("sources", [])]
                rules[node["id"]] = {
                    key: value
                    for key, value in (branches[0] if branches else {}).items()
                    if all(branch.get(key) == value for branch in branches)
                }
            elif node["type"] == "output":
                rules[node["id"]] = rules.get(node.get("source", {}).get("nodeId"), {})
        if before == rules:
            break
    return rules


def ratio_denominators(manifest):
    """Fields actually used as simple divisors; only supports validity diagnostics."""
    import ast

    fields = set()
    for node in effective_nodes(manifest):
        if node.get("processId") != "vector-field-calculate":
            continue
        for calculation in node.get("inputs", {}).get("calculations", []):
            try:
                expression = ast.parse(calculation.get("expression", ""), mode="eval")
            except (ValueError, SyntaxError):
                continue
            for part in ast.walk(expression):
                if (
                    isinstance(part, ast.BinOp)
                    and isinstance(part.op, ast.Div)
                    and isinstance(part.right, ast.Name)
                ):
                    field = calculation.get("fields", {}).get(part.right.id)
                    if isinstance(field, str):
                        fields.add(field)
    return fields


def contains_fixture(area, bounds):
    if (
        not isinstance(area, dict)
        or not {"bbox"} <= set(area) <= {"bbox", "crs"}
        or not isinstance(bounds, list)
        or len(bounds) != 4
    ):
        return False
    if area.get("crs", "OGC:CRS84") not in {"OGC:CRS84", "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}:
        return False
    bbox = area["bbox"]
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or any(type(v) not in {int, float} or not math.isfinite(v) for v in [*bbox, *bounds])
    ):
        return False
    # Same coordinate tolerance as the independently frozen geometry verifier;
    # upstream country vertices can exceed +/-180 by approximately 1e-10 degrees.
    return all(bbox[i] <= bounds[i] + 1e-8 for i in (0, 1)) and all(
        bbox[i] >= bounds[i] - 1e-8 for i in (2, 3)
    )


def authorize(manifest, task, inputs, reused=(), *, provenance_only=False, fixture_bounds=None):
    if task not in ALLOWED_PROCESSORS:
        raise Blocked("Approval policy: unknown task ID.")
    # Grading existing output is not permission to execute it. A completed tiled
    # calculation can have authentic fixture lineage while remaining outside the
    # conservative automatic-approval policy. Exact membership/coverage is graded
    # independently; this switch is never supplied by the agent or approval loop.
    if manifest.get("valid") is not True:
        raise Blocked("Approval policy: workflow is not validated.")
    if manifest.get("readiness", {}).get("status") != "ready":
        raise Blocked("Approval policy: reduced or unavailable work is not preauthorized.")
    definition = manifest.get("definition") or {}
    nodes = definition.get("nodes") or []
    if not nodes or len(nodes) > (1000 if provenance_only else 40):
        raise Blocked("Approval policy: missing or unexpectedly large graph.")
    allowed = {identity(v) for v in inputs.values()} | {identity(v) for v in reused}
    rules = measurement_rules(manifest, task, reused)
    denominators = ratio_denominators(manifest) if task in HEAT_TASKS or task in CHANGE_TASKS else set()
    _, origin = source_roles(manifest, inputs, reused)
    # Checking excluded/zero cases is useful QA, not a changed final selection.
    # Permit such a check only when no published output depends on it. An absent
    # output contract is not evidence that a branch is merely diagnostic.
    effective = list(effective_nodes(manifest))
    by_id = {node["id"]: node for node in effective}
    published_dependencies = set()

    def native_sample_weight(selection, field, spec):
        """Trace an actual band sample through filters, never calculated weights."""
        seen = set()
        while isinstance(selection, dict) and "$output" in selection:
            node_id = selection["$output"].get("nodeId")
            if node_id in seen:
                return False
            seen.add(node_id)
            node = by_id.get(node_id, {})
            args = node.get("inputs", {})
            if node.get("processId") == "vector-filter":
                selection = args.get("source")
                continue
            return (
                node.get("processId") == "raster-sample"
                and field in args.get("rasters", {})
                and args.get("bands", {}).get(field, 1) == 1
                and origin(args["rasters"][field]) == {spec.get("raster")}
                and origin(args.get("features")) == {spec.get("base")}
            )
        return False

    def references(value):
        if isinstance(value, dict):
            if isinstance(value.get("$output"), dict):
                yield value["$output"].get("nodeId")
            for child in value.values():
                yield from references(child)
        elif isinstance(value, list):
            for child in value:
                yield from references(child)

    pending = []
    for output in effective:
        if output.get("type") == "output":
            pending.append(output.get("source", {}).get("nodeId"))
    has_outputs = bool(pending)
    while pending:
        node_id = pending.pop()
        if node_id in published_dependencies:
            continue
        published_dependencies.add(node_id)
        pending.extend(references(by_id.get(node_id, {}).get("inputs", {})))
    for node in effective:
        # Assess effective executable arguments, not parameter placeholders or prose.
        if node.get("type") not in {"source", "processor", "output", "review"}:
            raise Blocked("Approval policy: this node type is not preauthorized.")
        if node.get("areaBindings"):
            raise Blocked("Approval policy: dynamic spatial clipping is not preauthorized.")
        if node.get("type") == "source":
            selection = node.get("selection", {})
            if node.get("area") is not None:
                # The frozen coordinator's generated-Item fast path passes this exact
                # immutable asset by reference; it does NOT crop, select records, or
                # resample it using SourceNode.area. This is tested against the real
                # normalized proposal. Processor areas/dynamic bindings stay denied.
                if (
                    identity(selection) not in allowed
                    or not selection.get("itemId")
                    or not selection.get("collectionId", "").startswith("blue-generated--")
                ):
                    raise Blocked("Approval policy: source extent has no proven full-asset reference path.")
            node.pop("area", None)
        if (task in MAP_TASKS or task in BIVARIATE_TASKS or task in SERIES_TASKS) and node.get("processId") in {
            "table-attribute-join",
            "vector-classify",
            "vector-bivariate-classify",
            "vector-field-calculate",
            "vector-filter",
        }:
            args = node.get("inputs", {})
            if contains_fixture(args.get("area"), (fixture_bounds or {}).get("countries")):
                # Authorize the ORIGINAL graph/digest. Removing this only from the
                # local inspection copy avoids rejecting a provably non-cropping extent.
                args.pop("area", None)
        if task in HEAT_TASKS and node.get("processId") == "raster-sample":
            spec = HEAT_TASKS[task]
            args = node.get("inputs", {})
            if (origin(args.get("features")) == {spec["base"]}
                    and contains_fixture(args.get("area"), (fixture_bounds or {}).get(spec["base"]))):
                # The area contains every original point, not merely the raster
                # footprint. No sampled or unknown input record can be excluded.
                args.pop("area", None)
        if task in {"419069", "321268"} and node.get("processId") == "spatial-clip":
            if task == "419069":
                from .county_density import BBOX
            else:
                from .snow_population import BBOX
            args = node.get("inputs", {})
            area = args.get("area", {})
            if (not isinstance(area, dict) or not {"bbox"} <= set(area) <= {"bbox", "crs"}
                    or area.get("bbox") != BBOX
                    or area.get("crs", "OGC:CRS84") not in {
                        "OGC:CRS84", "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}
                    or origin(args.get("source")) != {"us_population"}):
                raise Blocked(
                    "Approval policy: county population cropping must preserve the disclosed native-grid window."
                )
            # Inspection copy only; the exact approved digest retains this crop.
            args.pop("area", None)
        if task in CONTOUR_TASKS and node.get("processId") == "vector-spatial-join":
            selector = CONTOUR_TASKS[task].get("overlaySelector", {})
            args = node.get("inputs", {})
            bounds_key = selector.get("geography")
            if selector.get("field"):
                bounds_key = f"{bounds_key}:{selector['field']}:{selector['value']}"
            proof_key = f"safe-inner-area:{selector.get('predicate')}:{CONTOUR_TASKS[task].get('overlay')}:{bounds_key}"
            # Production area selects WHOLE target records, not clipped geometry.
            # With an inner join, any within/intersects match must intersect the
            # complete join envelope. This removes no possible matching result.
            if (
                args.get("joinType", "inner") == "inner"
                and args.get("predicate") in {"within", "intersects"}
                and origin(args.get("join")) == {selector.get("geography")}
                and (
                    contains_fixture(args.get("area"), (fixture_bounds or {}).get(bounds_key))
                    or (
                        args.get("predicate") == selector.get("predicate")
                        and origin(args.get("target")) == {CONTOUR_TASKS[task].get("overlay")}
                        and contains_fixture(args.get("area"), (fixture_bounds or {}).get(proof_key))
                    )
                )
            ):
                args.pop("area", None)
        allowed_processors = ALLOWED_PROCESSORS[task] | ({"vector-merge"} if provenance_only else set())
        if node.get("type") == "processor" and node.get("processId") not in allowed_processors:
            raise Blocked("Approval policy: computation is outside the benchmark's frozen operation families.")
        for value in walk(node):
            if not isinstance(value, dict):
                continue
            if value.get("sourceType") == "catalog-query" or isinstance(value.get("features"), list):
                raise Blocked("Approval policy: live queries and injected features are not permitted inputs.")
            if "collectionId" in value and identity(value) not in allowed:
                raise Blocked(
                    "Approval policy: input is not an exact fixture or verified task-owned derivative."
                )
            if any(k in value for k in ("url", "href")):
                raise Blocked("Approval policy: arbitrary remote inputs are not permitted.")
            # Map-algebra source aliases can legitimately be named area, bbox or
            # geometry. Inspect spatial payload shape, not arbitrary dictionary keys.
            spatial = (
                isinstance(value.get("bbox"), (list, tuple))
                or isinstance(value.get("geometry"), dict)
                and "type" in value["geometry"]
                or isinstance(value.get("area"), dict)
                and any(k in value["area"] for k in ("bbox", "geometry"))
            )
            if not provenance_only and spatial:
                raise Blocked(
                    "Approval policy: additional spatial clipping is not preauthorized for these global inputs."
                )
        if node.get("type") == "processor":
            settings = node.get("inputs", {})
            if task in OVERLAY_TASKS and node["processId"] == "raster-extract-band":
                if settings.get("band") != 1 or origin(settings.get("source")) != {OVERLAY_TASKS[task]["raster"]}:
                    raise Blocked("Approval policy: overlay band copy must use the declared original raster and band 1.")
            if task == "150069" and node["processId"] == "vector-nearest-distance":
                if settings.get("distanceCrs") != "EPSG:5070" or settings.get("targetGeometry", "geometry") != "geometry" or origin(settings.get("source")) != {"na_lakes"} or origin(settings.get("targets")) != {"snow"}:
                    raise Blocked("Approval policy: measure original lakes to observed snowy pixel areas in EPSG:5070, not contours or centroids.")
            if task in FLOOD_TASKS:
                s = FLOOD_TASKS[task]
                if node["processId"] == "raster-extract-band" and (origin(settings.get("source")) != {s["flood"]} or settings.get("band") not in [1, 3, 5]):
                    raise Blocked("Approval policy: flood extraction permits only observed flooded, clear-view and permanent-water bands.")
                if node["processId"] == "raster-align" and (origin(settings.get("source")) != {s["flood"]} or origin(settings.get("match")) != {s["population"]} or settings.get("resampling", "nearest") != "nearest" or settings.get("area") or settings.get("grid")):
                    raise Blocked("Approval policy: sample flood bands onto the unchanged original population grid by nearest containing pixel.")
                if node["processId"] in {"raster-cell-area", "raster-count-density"} and origin(settings.get("source")) != {s["population"]}:
                    raise Blocked("Approval policy: density and cell area must use the original population grid.")
            if task == "154613" and node["processId"] == "vector-nearest-distance":
                if (settings.get("distanceCrs") != DISTANCE_CRS
                        or settings.get("targetGeometry", "geometry") != "geometry"
                        or origin(settings.get("source")) != {"towns"}
                        or origin(settings.get("targets")) not in ({"na_lakes"}, {"na_rivers"})):
                    raise Blocked("Approval policy: water proximity needs original towns, lakes/rivers and the frozen metric CRS.")
            if task == "129699" and node["processId"] == "vector-nearest-distance":
                if (settings.get("distanceCrs") != "EPSG:3978"
                        or settings.get("targetGeometry", "geometry") != "boundary"
                        or origin(settings.get("source")) != {"na_lakes"}
                        or origin(settings.get("targets")) != {"countries"}):
                    raise Blocked("Approval policy: lake proximity requires original lake polygons, Canada's polygon boundary and EPSG:3978.")
            if task == "419069" and node["processId"] == "zonal-statistics":
                if (not has_outputs or node["id"] in published_dependencies
                        or settings.get("statistics") != ["count"]
                        or settings.get("allTouched", False)
                        or settings.get("zoneIdField") != "benchmark_row_id"):
                    raise Blocked("Approval policy: county zonal counts are diagnostic centre-cell checks only.")
            if task == "586288" and node["processId"] == "raster-point-proximity":
                if (
                    origin(settings.get("source")) != {"us_population"}
                    or origin(settings.get("points")) != {"fires"}
                    or settings.get("distanceM") != 50000
                    or settings.get("comparison", "lte") != "lte"
                    or settings.get("outputMode", "values") != "values"
                    or settings.get("band", 1) != 1
                ):
                    raise Blocked(
                        "Approval policy: population proximity requires the original native grid, source values and <=50 km geodesic centre selection."
                    )
            if task == "419069" and node["processId"] == "vector-rasterize":
                if (
                    settings.get("allTouched", False)
                    or settings.get("grid") is not None
                    or origin(settings.get("match")) != {"us_population"}
                    or origin(settings.get("source")) != {"counties"}
                ):
                    raise Blocked(
                        "Approval policy: county mask requires cell centres on the native population grid."
                    )
            if task == "321268" and node["processId"] == "raster-align":
                from .snow_population import BBOX

                grid = settings.get("grid") or {}
                native_crop = (
                    origin(settings.get("source")) == {"us_population"}
                    and settings.get("match") is None
                    and grid.get("crs") == "EPSG:4326"
                    and grid.get("bounds") == BBOX
                    and grid.get("width") == 7561
                    and grid.get("height") == 4705
                    and all(
                        type(grid.get(k)) in {int, float}
                        and math.isclose(grid[k], 0.0083333333, rel_tol=0, abs_tol=1e-14)
                        for k in ("resolutionX", "resolutionY")
                    )
                )
                snow_sampling = (
                    settings.get("grid") is None
                    and origin(settings.get("match")) == {"us_population"}
                    and origin(settings.get("source")) == {"snow_previous"}
                )
                if settings.get("resampling", "nearest") != "nearest" or not (native_crop or snow_sampling):
                    raise Blocked(
                        "Approval policy: alignment must be a lossless native population crop or nearest snow sampling onto that unchanged grid."
                    )
            if task == "310610" and node["processId"] == "vector-overlay":
                if (
                    settings.get("operation") not in {"intersection", "difference"}
                    or origin(settings.get("primary")) != {"na_railways"}
                    or origin(settings.get("overlay")) != {"snow"}
                ):
                    raise Blocked(
                        "Approval policy: snowy-rail clipping requires original US lines and a frozen-snow-derived mask."
                    )
            if task == "310610" and node["processId"] == "vector-measure":
                if (
                    settings.get("measure") != "length"
                    or settings.get("unit") not in {"m", "km"}
                    or origin(settings.get("source")) != {"na_railways"}
                ):
                    raise Blocked(
                        "Approval policy: railway measurement requires line length, not perimeter or area."
                    )
            if task in PROXIMITY_TASKS and node["processId"] == "vector-nearest-distance":
                spec = PROXIMITY_TASKS[task]
                if (
                    settings.get("distanceCrs") != spec["distanceCrs"]
                    or origin(settings.get("source")) != {spec["base"]}
                    or origin(settings.get("targets")) != {spec["lines"]}
                ):
                    raise Blocked(
                        "Approval policy: proximity requires the original point/line fixtures and declared projection."
                    )
            if task in HEAT_TASKS and node["processId"] == "vector-nearest-distance":
                spec = HEAT_TASKS[task]
                if (
                    settings.get("distanceCrs") != spec.get("distanceCrs")
                    or origin(settings.get("source")) != {spec["base"]}
                    or origin(settings.get("targets")) != {spec.get("nearLines")}
                ):
                    raise Blocked(
                        "Approval policy: nearest distance needs the original point/line fixtures and declared metre projection."
                    )
            if task in GEOMETRY_DENSITY_TASKS and node["processId"] == "vector-measure":
                if (
                    settings.get("measure") != "area"
                    or settings.get("unit") not in {"m2", "km2"}
                    or origin(settings.get("source")) - {"countries", "population", "forest_percent"}
                ):
                    raise Blocked(
                        "Approval policy: density requires physical area of the original country geometry."
                    )
            if task in POPULATION_TASKS and node["processId"] == "raster-cell-area":
                if settings.get("band", 1) != 1 or settings.get("unit", "km2") not in {"km2", "m2"}:
                    raise Blocked(
                        "Approval policy: population cell area requires the original band and physical area units."
                    )
            if task in POPULATION_TASKS and node["processId"] == "raster-count-density":
                if (
                    settings.get("band", 1) != 1
                    or settings.get("countUnit") != "people"
                    or origin(settings.get("source")) != {POPULATION_TASKS[task]["raster"]}
                ):
                    raise Blocked("Approval policy: density requires original band-1 population counts in people.")
            if task in POPULATION_TASKS and node["processId"] == "distance-surface":
                spec = POPULATION_TASKS[task]
                if (
                    settings.get("method") != spec.get("method", "geodesic-points")
                    or settings.get("distanceCrs") != spec.get("distanceCrs")
                    or settings.get("area") is not None
                    or settings.get("grid") is not None
                    or settings.get("maximumDistanceM") is not None
                    or settings.get("targetValues") is not None
                    or origin(settings.get("source")) != {spec.get("points")}
                    or origin(settings.get("match")) != {spec["raster"]}
                ):
                    raise Blocked(
                        "Approval policy: population proximity must retain the declared geodesic centre-distance method, original grid, source points and uncapped distances."
                    )
            if task in COUNTY_HEAT_TASKS:
                if node["processId"] == "vector-centroids" and (
                    settings.get("mode") != "centroid" or settings.get("centroidCrs") != "EPSG:5070"
                ):
                    raise Blocked(
                        "Approval policy: county heatmap requires the disclosed projected geometric centroid."
                    )
                if node["processId"] == "point-density":
                    grid = settings.get("grid", {})
                    if (
                        any(grid.get(k) != v for k, v in COUNTY_GRID.items())
                        or settings.get("radiusM") != COUNTY_RADIUS
                        or settings.get("weightField") != "case_count"
                        or settings.get("weightUnit") != "cases"
                        or settings.get("match") is not None
                    ):
                        raise Blocked("Approval policy: county heatmap grid, weighting or smoothing changed.")
            if task in COUNTY_TASKS and node["processId"] == "vector-classify":
                spec = COUNTY_TASKS[task]
                if (
                    settings.get("method", "equal-interval") != "quantile"
                    or settings.get("classes", 5) != 5
                    or not same_unit(settings.get("unit"), spec["unit"])
                ):
                    raise Blocked("Approval policy: county classification or units changed.")
            if (
                task in SERIES_TASKS
                and SERIES_TASKS[task].get("bivariate")
                and node["processId"] == "vector-bivariate-classify"
            ):
                spec = SERIES_TASKS[task]
                if (
                    settings.get("method", "quantile") != "quantile"
                    or settings.get("classes", 3) != 3
                    or not all(same_unit(settings.get(k), spec[k]) for k in ("xUnit", "yUnit"))
                ):
                    raise Blocked("Approval policy: map-series bivariate classification or units changed.")
            if (
                task in SERIES_TASKS
                and not SERIES_TASKS[task].get("bivariate")
                and node["processId"] == "vector-classify"
            ):
                spec = SERIES_TASKS[task]
                if (
                    settings.get("field") not in spec["years"]
                    or settings.get("method", "equal-interval") != "quantile"
                    or settings.get("classes", 5) != 5
                    or not same_unit(settings.get("unit"), spec["unit"])
                ):
                    raise Blocked("Approval policy: map-series year, classification or units changed.")
            if task in BIVARIATE_TASKS and node["processId"] == "vector-bivariate-classify":
                spec = BIVARIATE_TASKS[task]
                if (
                    settings.get("method", "quantile") != "quantile"
                    or settings.get("classes", 3) != 3
                    or not all(same_unit(settings.get(k), spec[k]) for k in ("xUnit", "yUnit"))
                ):
                    raise Blocked("Approval policy: bivariate classification or measurement units changed.")
            if task in CONTOUR_TASKS and node["processId"] == "raster-contours":
                spec = CONTOUR_TASKS[task]
                if (
                    settings.get("levels") != spec["levels"]
                    or not same_unit(settings.get("unit"), spec["unit"])
                    or settings.get("band", 1) != 1
                ):
                    raise Blocked("Approval policy: contour levels, units or source band changed.")
                expected_origins = {spec["raster"]} | ({spec["floodMask"]} if spec.get("floodMask") else set())
                if origin(settings.get("source")) != expected_origins:
                    raise Blocked("Approval policy: contour raster identity is not the frozen source.")
            if task in CONTOUR_TASKS and node["processId"] == "raster-sample":
                spec = CONTOUR_TASKS[task]
                if (
                    origin(settings.get("features")) != {spec.get("overlay")}
                    or any(
                        origin(value) != {spec["raster"]} for value in settings.get("rasters", {}).values()
                    )
                    or any(band != 1 for band in settings.get("bands", {}).values())
                ):
                    raise Blocked(
                        "Approval policy: overlay inspection must sample the declared band and frozen raster only."
                    )
            if task in HEAT_TASKS and node["processId"] == "point-density":
                spec = HEAT_TASKS[task]
                grid = settings.get("grid", {})
                selection = settings.get("source", {})
                source_rules = rules.get(selection.get("$output", {}).get("nodeId"), {})
                if "$output" not in selection:
                    source_rules = next((asset.get("measurementRules", {}) for asset in reused
                                         if identity(asset) == identity(selection)), {})
                weight_rule = source_rules.get(settings.get("weightField"))
                # In a derived country-selection task only a typed identity
                # weight copy receives the nonnegative rule. Country ratios or
                # differences retain their distinct eligibility threshold.
                identity_alias = (
                    bool(spec.get("derived"))
                    and bool(spec.get("weight"))
                    and weight_rule is not None and tuple(weight_rule) == ("gte", 0)
                    and origin(selection) == {spec["base"]}
                )
                sampled_alias = bool(spec.get("raster")) and native_sample_weight(
                    selection, settings.get("weightField"), spec)
                native_count_unit = (
                    sampled_alias and spec.get("weightUnit") == "people"
                    and settings.get("weightUnit") == "people per source cell"
                )
                if (
                    any(grid.get(k) != v for k, v in GRID.items() if k != "resolutionY")
                    or (grid.get("resolutionY") or grid.get("resolutionX")) != GRID["resolutionY"]
                    or grid.get("width")
                    not in (None, int((GRID["bounds"][2] - GRID["bounds"][0]) / GRID["resolutionX"]))
                    or grid.get("height")
                    not in (None, int((GRID["bounds"][3] - GRID["bounds"][1]) / GRID["resolutionY"]))
                    or settings.get("match") is not None
                    or settings.get("radiusM", 0) != RADIUS_M
                    or (settings.get("weightField") != spec.get("weight") and not identity_alias and not sampled_alias)
                    or (spec.get("weight") and not same_unit(settings.get("weightUnit"), spec["weightUnit"]) and not native_count_unit)
                ):
                    raise Blocked("Approval policy: heatmap grid, smoothing or weight convention changed.")
            if task in HEAT_TASKS and node["processId"] == "raster-sample":
                spec = HEAT_TASKS[task]
                if (
                    origin(settings.get("features")) != {spec["base"]}
                    or len(settings.get("rasters", {})) != 1
                    or any(origin(v) != {spec["raster"]} for v in settings["rasters"].values())
                    or any(b != 1 for b in settings.get("bands", {}).values())
                ):
                    raise Blocked(
                        "Approval policy: heatmap eligibility requires the frozen point source, raster and band."
                    )
            if task in HEAT_TASKS and node["processId"] == "vector-dissolve":
                spec = HEAT_TASKS[task]
                if origin(settings.get("source")) != {spec.get("geographyAsset")} or settings.get(
                    "aggregations"
                ):
                    raise Blocked(
                        "Approval policy: dissolve may only combine the declared geographic selection without changing measurements."
                    )
            if task in MAP_TASKS and node["processId"] == "vector-classify":
                if settings.get("method", "equal-interval") != "quantile" or settings.get("classes", 5) != 5:
                    raise Blocked("Approval policy: the disclosed map classification changed.")
                if not same_unit(settings.get("unit"), unit_for(task, INDICATORS[MAP_TASKS[task][0]][2])):
                    raise Blocked("Approval policy: map measurement units changed.")
            if task in MAP_TASKS and task not in DERIVED and node["processId"] == "vector-field-calculate":
                import ast

                for calculation in settings.get("calculations", []):
                    try:
                        expression = ast.parse(calculation.get("expression", ""), mode="eval").body
                    except (SyntaxError, ValueError):
                        raise Blocked(
                            "Approval policy: field copy is not a simple attribute reference."
                        ) from None
                    if (
                        not isinstance(expression, ast.Name)
                        or expression.id not in calculation.get("fields", {})
                        or not same_unit(
                            calculation.get("unit"), unit_for(task, INDICATORS[MAP_TASKS[task][0]][2])
                        )
                    ):
                        raise Blocked(
                            "Approval policy: this task permits a lossless numeric field copy, not changed values or units."
                        )
            if not provenance_only and node["processId"] == "vector-merge" and settings.get("fieldMappings"):
                raise Blocked("Artifact provenance: field-remapping merges are not verified.")
            def excluded_weight_check(predicate):
                return (
                    task in HEAT_TASKS
                    and (provenance_only or has_outputs and node["id"] not in published_dependencies)
                    and predicate.get("operator") == "lt" and predicate.get("value") == 0
                    and (
                        predicate.get("field") == HEAT_TASKS[task].get("weight")
                        or tuple(rules.get(node["id"], {}).get(predicate.get("field"), ())) == ("gte", 0)
                    )
                )

            null_diagnostic = bool(settings.get("predicates")) and all(
                p.get("operator") in {"is-null", "not-null"}
                or (p.get("field") in denominators and p.get("operator") == "lte" and p.get("value") == 0)
                or excluded_weight_check(p)
                for p in settings["predicates"]
            )
            if (
                not provenance_only
                and not null_diagnostic
                and task not in COUNTRY_TASK_YEARS
                and task != "883928"
                and settings.get("combine", "all") != "all"
            ):
                raise Blocked(
                    "Approval policy: changing required criteria to alternatives is not preauthorized."
                )
            permitted_predicates = {"within", "intersects"} if task == "417961" else {"within"}
            if task == "645898" and node["processId"] == "vector-spatial-join":
                if (origin(settings.get("target")), origin(settings.get("join"))) != ({"counties"}, {"na_rivers"}):
                    raise Blocked("Approval policy: Mississippi selection needs original county geometry and river source.")
                permitted_predicates = {"intersects"}
            if (
                task in CONTOUR_TASKS
                and CONTOUR_TASKS[task].get("overlaySelector")
                and node["processId"] == "vector-spatial-join"
            ):
                spec = CONTOUR_TASKS[task]
                sel = spec["overlaySelector"]
                if (origin(settings.get("target")), origin(settings.get("join"))) != (
                    {spec["overlay"]},
                    {sel["geography"]},
                ):
                    raise Blocked(
                        "Approval policy: contour overlay must use original lines and declared geography."
                    )
                permitted_predicates = {sel["predicate"]}
            if task == "365343" and node["processId"] == "vector-spatial-join":
                if (origin(settings.get("target")), origin(settings.get("join"))) != (
                    {"sa_rivers"},
                    {"countries"},
                ):
                    raise Blocked(
                        "Approval policy: river selection needs the original rivers against the selected country geometry."
                    )
                permitted_predicates = {"intersects"}
            if task == "955741" and node["processId"] == "vector-spatial-join":
                pair = (origin(settings.get("target")), origin(settings.get("join")))
                if "counties" not in pair[0] or not pair[1] <= {"earthquakes", "fires"} or not pair[1]:
                    raise Blocked(
                        "Approval policy: county/event relationship requires original county geometry and authorized events."
                    )
                permitted_predicates = {"intersects", "contains"}
            if task in HEAT_TASKS and HEAT_TASKS[task].get("predicate") == "intersects":
                spec = HEAT_TASKS[task]
                if node.get("processId") == "vector-spatial-join" and (
                    origin(settings.get("target")),
                    origin(settings.get("join")),
                ) == ({spec["base"]}, {spec["geographyAsset"]}):
                    permitted_predicates = {"intersects"}
            if task in COUNTRY_TASK_YEARS and node["processId"] == "vector-spatial-join":
                pair = (origin(settings.get("target")), origin(settings.get("join")))
                point_source = "earthquakes" if task == "918547" else "power_stations"
                if pair == ({"countries"}, {point_source}):
                    permitted_predicates = {"contains"}
                elif pair == ({point_source}, {"countries"}):
                    permitted_predicates = {"within"}
                elif not provenance_only:
                    raise Blocked("Approval policy: country/point join lacks permitted source roles.")
            if not provenance_only and task == "417961" and node["processId"] == "vector-spatial-join":
                pair = (origin(settings.get("target")), origin(settings.get("join")))
                if pair == ({"counties"}, {"earthquakes"}):
                    permitted_predicates = {"intersects"}
                elif pair == ({"stations"}, {"counties"}):
                    permitted_predicates = {"within"}
                else:
                    raise Blocked(
                        "Approval policy: station/county relationship has no verified source roles."
                    )
            # An independently graded artifact may share a workflow with diagnostic
            # predicates (for example, checking boundary intersections). Provenance
            # proves its authorized inputs, not the analytical correctness of every
            # sibling node. Exact selected IDs/geometry establish correctness later.
            # This exception never grants execution approval.
            if (
                not provenance_only
                and node["processId"] == "vector-spatial-join"
                and settings.get("predicate", "intersects") not in permitted_predicates
            ):
                raise Blocked("Approval policy: the requested spatial relationship was changed.")
            for p in settings.get("predicates", []):
                field = p.get("field")
                if excluded_weight_check(p):
                    continue
                if (
                    task == "741001"
                    and tuple(rules.get(node["id"], {}).get(field, ())) == ("lt", 5000)
                    and p.get("operator") == "gte"
                    and p.get("value") == 5000
                ):
                    from .proximity_tasks import SOUTH_AMERICA

                    if any(
                        q.get("field") == "COUNTRY"
                        and q.get("operator") == "not-in"
                        and set(q.get("value", [])) == set(SOUTH_AMERICA)
                        for q in settings.get("predicates", [])
                    ):
                        continue  # Unselected ports outside source coverage are unknown.
                if task == "741001" and field == "COUNTRY" and p.get("operator") in {"in", "not-in"}:
                    from .proximity_tasks import SOUTH_AMERICA

                    if set(p.get("value", [])) != set(SOUTH_AMERICA):
                        raise Blocked(
                            "Approval policy: port missing-coverage diagnostic changed the declared region."
                        )
                    continue
                if field in denominators and p.get("operator") in {"gt", "lte"} and p.get("value") == 0:
                    continue
                if task in HEAT_TASKS and HEAT_TASKS[task].get("raster") and field == "State":
                    # The full authorized station file includes Canadian rows.
                    # US inclusion and Canadian coverage diagnostics are allowed;
                    # exact final point membership remains independently graded.
                    from .family_oracles import US_STATES

                    declared = US_STATES | {"DC", "AS", "GU", "MP", "PR", "VI", "ON", "QC", "BC"}
                    value = p.get("value")
                    if p.get("operator") in {"is-null", "not-null"} or (
                        p.get("operator") == "in"
                        and isinstance(value, list)
                        and bool(value)
                        and set(value) <= declared
                    ):
                        continue
                    raise Blocked(
                        "Approval policy: station geography diagnostic uses undeclared state codes."
                    )
                expected = {"pop_2010": ("gt", 5000), "2023": ("lt", 0), "CONTINENT": ("eq", "Africa")}
                if task == "332083":
                    expected = {"Country": ("eq", "Algeria")}
                elif task in POPULATION_TASKS:
                    spec = POPULATION_TASKS[task]
                    expected = (
                        {spec["countryField"]: ("eq", spec["country"])} if spec.get("countryField") else {}
                    )
                elif task in CHANGE_TASKS:
                    spec = CHANGE_TASKS[task]
                    expected = {} if spec.get("regionField") else {"CONTINENT": ("eq", "Africa")}
                    if spec.get("regionField") == field and p.get("operator") not in {"is-null", "not-null"}:
                        value = p.get("value")
                        if (
                            not (
                                (p.get("operator") == "eq" and value in spec["regionMembers"])
                                or (
                                    p.get("operator") == "in"
                                    and isinstance(value, list)
                                    and bool(value)
                                    and set(value) <= set(spec["regionMembers"])
                                )
                            )
                            and not provenance_only
                        ):
                            raise Blocked(
                                "Approval policy: country-change geography differs from the frozen region."
                            )
                        continue
                elif task in SERIES_TASKS:
                    spec = SERIES_TASKS[task]
                    expected = (
                        {spec["regionField"]: ("eq", spec["regionMembers"][0])}
                        if spec.get("regionField")
                        else {}
                    )
                elif task in COUNTY_TASKS:
                    expected = {"STATEFP": ("eq", COUNTY_TASKS[task]["state"])}
                elif task in COUNTY_HEAT_TASKS:
                    expected = {}
                    if field == "STATEFP" and p.get("operator") not in {"is-null", "not-null"}:
                        allowed_states = set(COUNTY_HEAT_TASKS[task]["states"])
                        value = p.get("value")
                        if not (
                            (p.get("operator") == "eq" and value in allowed_states)
                            or (
                                p.get("operator") == "in"
                                and isinstance(value, list)
                                and bool(value)
                                and set(value) <= allowed_states
                            )
                        ):
                            raise Blocked("Approval policy: county heatmap changed state coverage.")
                        continue
                elif task == "419069":
                    expected = {
                        "case_count": ("gt", 0),
                        "2023 cases": ("gt", 0),
                        "Number of Cases": ("gt", 0),
                    }
                    if (has_outputs and node["id"] not in published_dependencies
                            and field in expected and p.get("operator") == "eq"
                            and p.get("value") == 0):
                        continue
                    if field == "STATEFP" and p.get("operator") not in {"is-null", "not-null"}:
                        value = p.get("value")
                        if not (
                            (p.get("operator") == "eq" and value in {"25", "36"})
                            or (
                                p.get("operator") == "in"
                                and isinstance(value, list)
                                and bool(value)
                                and set(value) <= {"25", "36"}
                            )
                        ):
                            raise Blocked(
                                "Approval policy: county TB coverage is limited to the two declared states."
                            )
                        continue
                elif task in HEAT_TASKS:
                    spec = HEAT_TASKS[task]
                    expected = (
                        {"CONTINENT": ("eq", "Africa")}
                        if not spec.get("globalCountries")
                        and not spec.get("field")
                        and not spec.get("raster")
                        and not spec.get("nearLines")
                        and not spec.get("allPoints")
                        else {}
                    )
                    if spec.get("nearLines"):
                        expected[spec["lineField"]] = ("eq", spec["lineValue"])
                    if spec.get("indicator"):
                        expected[spec["years"][0]] = (spec["operator"], spec["threshold"])
                    if spec.get("weight"):
                        expected[spec["weight"]] = ("gte", 0)
                    if spec.get("field") == field and p.get("operator") not in {"is-null", "not-null"}:
                        requested = p.get("value")
                        valid = (p.get("operator") == "eq" and requested in spec["members"]) or (
                            p.get("operator") == "in"
                            and isinstance(requested, list)
                            and bool(requested)
                            and set(requested) <= set(spec["members"])
                        )
                        if not valid and not provenance_only:
                            raise Blocked(
                                "Approval policy: heatmap geography differs from the frozen selection."
                            )
                        continue
                elif task == "586288":
                    expected = {"IncidentTy": ("eq", "WF"), "IncidentSi": ("gt", 1000)}
                elif task in {"311281", "955741", "345106"} and field == "IncidentTy":
                    if p.get("operator") not in {"is-null", "not-null"} and not (
                        p.get("operator") == "eq"
                        and p.get("value") == "WF"
                        or p.get("operator") == "in"
                        and p.get("value") == ["WF"]
                    ):
                        raise Blocked("Approval policy: wildfire selection must exclude prescribed burns.")
                    continue
                elif task in {"417961", "955741"}:
                    expected = {"type": ("eq", "earthquake")} if task == "955741" else {}
                elif task == "310610":
                    expected = {"COUNTRY": ("eq", "US")}
                    # Native threshold masks and zero-dimensional overlay touches
                    # are mechanical diagnostics, not additional source criteria.
                    if (
                        field in {"value", "length_km", "length_m", "measurement"}
                        and p.get("operator") in {"eq", "gt"}
                        and p.get("value") in {0, 1}
                    ):
                        continue
                elif task == "365343":
                    expected = {"CONTINENT": ("eq", "South America"), "2021": ("gt", 50)}
                elif task in WATER_SELECTIONS:
                    expected = {"NameEn": ("eq", "Mississippi River")} if task == "645898" else {}
                    if task == "129699":
                        expected = {"NAME_EN": ("eq", "Canada")}
                elif task == "150069":
                    expected = {}
                    if (origin(settings.get("source")) == {"snow"}
                            and field == "value" and p.get("operator") == "eq"
                            and p.get("value") == 1):
                        continue
                elif task in COUNTRY_TASK_YEARS:
                    expected = {"CONTINENT": ("eq", "Africa")} if task in {"806525", "429627"} else {}
                    if task == "429627":
                        expected["DsgAttr02"] = ("gt", 1000)
                elif task == "883928":
                    expected = {}
                expected.update({f: tuple(rule) for f, rule in rules.get(node["id"], {}).items()})
                if task in CONTOUR_TASKS:
                    permitted = CONTOUR_TASKS[task].get("filter", {}).get(field)
                    selector = CONTOUR_TASKS[task].get("overlaySelector", {})
                    if field == selector.get("field"):
                        permitted = [selector["value"]]
                    if permitted is not None and p.get("operator") not in {"is-null", "not-null"}:
                        value = p.get("value")
                        valid = (p.get("operator") == "eq" and value in permitted) or (
                            p.get("operator") == "in"
                            and isinstance(value, list)
                            and bool(value)
                            and set(value) <= set(permitted)
                        )
                        if not valid:
                            raise Blocked("Approval policy: contour overlay geography changed.")
                        continue
                    expected = {}
                if (
                    task in REGIONAL
                    and field == REGIONAL[task][2]
                    and p.get("operator") not in {"is-null", "not-null"}
                ):
                    allowed_values = REGIONAL[task][3]
                    requested = p.get("value")
                    valid = (p.get("operator") == "eq" and requested in allowed_values) or (
                        p.get("operator") == "in"
                        and isinstance(requested, list)
                        and bool(requested)
                        and set(requested) <= set(allowed_values)
                    )
                    if not valid and not provenance_only:
                        raise Blocked(
                            "Approval policy: regional membership differs from the disclosed geography."
                        )
                    continue
                if (
                    task in BIVARIATE_TASKS
                    and BIVARIATE_TASKS[task].get("geography", {}).get("field") == field
                    and p.get("operator") not in {"is-null", "not-null"}
                ):
                    allowed_values = BIVARIATE_TASKS[task]["geography"]["values"]
                    value = p.get("value")
                    valid = (
                        p.get("operator") == "eq"
                        and value in allowed_values
                        or p.get("operator") == "in"
                        and isinstance(value, list)
                        and bool(value)
                        and set(value) <= set(allowed_values)
                    )
                    if not valid and not provenance_only:
                        raise Blocked("Approval policy: bivariate geography changed.")
                    continue
                if (
                    task in GROUP_COMPARISONS
                    and field == GROUP_COMPARISONS[task][0]
                    and p.get("operator") not in {"is-null", "not-null"}
                ):
                    members = {value for group in GROUP_COMPARISONS[task][1].values() for value in group}
                    value = p.get("value")
                    valid = (p.get("operator") == "eq" and value in members) or (
                        p.get("operator") == "in"
                        and isinstance(value, list)
                        and bool(value)
                        and set(value) <= members
                    )
                    if not valid and not provenance_only:
                        raise Blocked(
                            "Approval policy: comparison membership differs from the disclosed groups."
                        )
                    continue
                if task == "883928" and field == "State" and p.get("operator") not in {"is-null", "not-null"}:
                    from .family_oracles import US_STATES

                    value = p.get("value")
                    valid = (
                        p.get("operator") == "in" and isinstance(value, list) and set(value) == US_STATES
                    ) or (
                        p.get("operator") == "not-in"
                        and isinstance(value, list)
                        and set(value) == {"ON", "QC", "BC", "DC"}
                    )
                    if not valid and not provenance_only:
                        raise Blocked("Approval policy: state eligibility changed.")
                    continue
                if (
                    task == "977524"
                    and field == "INCOME_GRP"
                    and p.get("operator") not in {"is-null", "not-null"}
                ):
                    from .family_oracles import HIGH_INCOME, LOW_INCOME

                    allowed_groups = {*HIGH_INCOME, LOW_INCOME}
                    value = p.get("value")
                    valid = (p.get("operator") == "eq" and value in allowed_groups) or (
                        p.get("operator") == "in"
                        and isinstance(value, list)
                        and bool(value)
                        and set(value) <= allowed_groups
                    )
                    if not valid and not provenance_only:
                        raise Blocked("Approval policy: income-group definition changed.")
                    continue
                if (
                    not provenance_only
                    and field not in expected
                    and p.get("operator") not in {"is-null", "not-null"}
                ):
                    raise Blocked("Approval policy: an additional record-selection criterion needs review.")
                # Null checks are legitimate coverage investigations, not substitutions.
                if field in expected and p.get("operator") not in {"is-null", "not-null"}:
                    actual = (p.get("operator"), p.get("value"))
                    equivalent_change = (
                        task in CHANGE_TASKS
                        and field in rules.get(node["id"], {})
                        and actual
                        in (
                            {("lt", 0.79), ("gt", 0.21), ("lt", -0.21), ("lt", 79), ("gt", 21), ("lt", -21)}
                            if task == "932053"
                            else {("lt", -0.03), ("gt", 0.03), ("lt", -3), ("gt", 3)}
                        )
                    )
                    count_equivalent = (
                        task in (COUNTRY_TASK_YEARS.keys() | {"955741", "645898"})
                        and field in rules.get(node["id"], {})
                        and actual == ("gte", expected[field][1] + 1)
                    )
                    if actual != expected[field] and not count_equivalent and not equivalent_change:
                        raise Blocked("Approval policy: a task threshold or geography criterion was changed.")
            if node["processId"] == "table-attribute-join":
                fields = settings.get("fields", [])
                allowed_years = (
                    set(SERIES_TASKS[task]["years"])
                    if task in SERIES_TASKS
                    else set(CHANGE_TASKS[task]["years"])
                    if task in CHANGE_TASKS
                    else set(HEAT_TASKS[task]["years"])
                    if task in HEAT_TASKS
                    else years_for(task, COUNTRY_TASK_YEARS.get(task, "2023"))
                )
                if task == "365343":
                    allowed_years = {"2021"}
                if any(str(f).isdigit() and len(str(f)) == 4 and str(f) not in allowed_years for f in fields):
                    raise Blocked("Approval policy: a different measurement year was selected.")
    # Do not assert that prose proves mathematical equivalence. The exact graph and
    # source-only lineage are retained and independently graded after execution.
    return {"decision": "approve", "approvalDigest": manifest["approvalDigest"], "acceptScopeChanges": False}


def trusted_reuse(data, task, inputs, *, for_grading=False, fixture_bounds=None):
    """Build provenance closure from exact fixtures through permitted completed work."""
    reusable = []
    remaining = list(data.get("workflows", []))
    for _ in range(len(remaining) + 1):
        progress = False
        for workflow in remaining[:]:
            try:
                if data.get('approvalPolicy') == 'authorized-scope-v1':
                    from .scope_policy import authorize_scope
                    authorize_scope(workflow['manifest'], inputs, reusable, provenance_only=for_grading,
                                    processors=data.get('profileProcessors'))
                else:
                    authorize(
                    workflow["manifest"],
                    task,
                    inputs,
                    reusable,
                    provenance_only=for_grading,
                    fixture_bounds=fixture_bounds,
                    )
            except (Blocked, KeyError):
                continue
            rules = measurement_rules(workflow["manifest"], task, reusable)
            roles, _ = source_roles(workflow["manifest"], inputs, reusable)
            for node in workflow.get("nodes", []):
                if node["status"] != "succeeded":
                    continue
                for output in (node.get("outputs") or {}).values():
                    if isinstance(output, dict) and output.get("collectionId") and output.get("itemId"):
                        # Only expose actual asset keys inspected on the resulting Item.
                        reusable.extend(
                            {
                                **{k: a[k] for k in ("collectionId", "itemId", "assetKey")},
                                "measurementRules": rules.get(node["node_id"], {}),
                                "sourceRoles": sorted(roles.get(node["node_id"], set())),
                            }
                            for a in data.get("artifacts", [])
                            if a["collectionId"] == output["collectionId"] and a["itemId"] == output["itemId"]
                        )
            remaining.remove(workflow)
            progress = True
        if not progress:
            break
    return reusable
