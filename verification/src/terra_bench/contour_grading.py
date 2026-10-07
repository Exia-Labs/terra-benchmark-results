"""Contour and overlay fulfillment, using saved artifacts and live-binding receipts."""

from pathlib import Path

import geopandas as gpd

from .common import Blocked, beneath, sha, timestamp
from .contour_oracles import check_contours
from .contour_tasks import CONTOUR_TASKS
from .fixtures import ROW_ID
from .policy import identity, trusted_reuse


def bound_layer(snapshot, artifact, layer_id):
    from .map_bindings import verify_map_binding

    verify_map_binding(snapshot, artifact, layer_id)


def same_overlay_geometry(actual, expected):
    """Preserve unlocated records without treating a fabricated location as valid."""
    if actual is None or expected is None:
        return actual is None and expected is None
    return bool(actual.equals_exact(expected, tolerance=1e-8, normalize=True))


def check_level_legend(frame, claim, expected, view):
    from .units import label_has_unit

    field = (view or {}).get("categoryField")
    if field not in frame or claim.get("level_field") not in frame:
        raise Blocked("Contour renderer lacks a field-backed level legend.")
    # A native legend can use the contour level itself; selecting that column
    # twice creates duplicate pandas columns rather than a second variable.
    pairs = frame[list(dict.fromkeys([claim["level_field"], field]))].drop_duplicates()
    if (
        len(pairs) != expected.get("count", len(expected["levels"]))
        or pairs[claim["level_field"]].duplicated().any()
        or pairs[field].duplicated().any()
    ):
        raise Blocked("Contour legend combines different levels or splits one level.")
    categories = view.get("categories", [])
    # The classifier advertises its reserved NoData class even when no
    # feature uses it. This does not combine levels or hide real contours.
    categories = [
        c
        for c in categories
        if not (
            c.get("value") not in set(pairs[field]) and c.get("value") == 0 and c.get("label") == "No data"
        )
    ]
    if (
        len(categories) != len(pairs)
        or {c.get("value") for c in categories} != set(pairs[field])
        or len({c.get("color") for c in categories}) != len(categories)
        or any(not label_has_unit(c.get("label", ""), expected["unit"]) for c in categories)
    ):
        raise Blocked("Contour legend levels, distinguishable colors or units are incorrect.")


def grade_contour(
    task, frame, claim, expected, snapshot, artifact, frozen, fixtures, scope, folder, deadline
):
    check_contours(frame, claim, expected, frozen["fixtureDirectory"])
    layer_id = claim.get("map_layer_id")
    bound_layer(snapshot, artifact, layer_id)
    display = snapshot.get("mapDisplays", {}).get(layer_id, {})
    view = next(
        (
            x.get("blue:vector_presentation")
            for x in display.get("tilesets", [])
            if x.get("blue:vector_presentation")
        ),
        None,
    )
    check_level_legend(frame, claim, expected, view)
    spec = CONTOUR_TASKS[task]
    for key in spec.get("contexts", []):
        contexts = [c for c in claim.get("context_layers", []) if c.get("name") == key]
        if len(contexts) != 1:
            raise Blocked("Contour map is missing a required context layer.")
        check_vector_overlay(
            task,
            key,
            contexts[0],
            expected["contextIds"][key],
            snapshot,
            frozen,
            fixtures,
            scope,
            folder,
            deadline,
        )
    if not spec.get("overlay"):
        return
    check_vector_overlay(
        task,
        spec["overlay"],
        claim.get("overlay", {}),
        expected["overlayIds"],
        snapshot,
        frozen,
        fixtures,
        scope,
        folder,
        deadline,
    )


def check_vector_overlay(
    task, key, overlay, expected_ids, snapshot, frozen, fixtures, scope, folder, deadline
):
    from .grading import check_membership
    from .lineage import record_identity_field

    source_spec = fixtures["assets"][key]
    source_path = Path(frozen["fixtureDirectory"]) / source_spec["path"]
    if sha(source_path) != source_spec["sha256"]:
        raise Blocked("Overlay source checksum changed after freeze.")
    if identity(overlay.get("selection", {})) == identity(scope["inputs"][key]):
        match, path, field = scope["inputs"][key], source_path, ROW_ID
    else:
        match = next(
            (
                a
                for a in snapshot.get("artifacts", [])
                if identity(a) == identity(overlay.get("selection", {}))
            ),
            None,
        )
        if not match or not match.get("finishedAt") or timestamp(match["finishedAt"]) > deadline:
            raise Blocked("Contour comparison is missing its pre-deadline vector artifact.")
        trusted = {identity(a) for a in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True)}
        if identity(match) not in trusted:
            raise Blocked("Overlay lacks authorized frozen-source lineage.")
        path = beneath(folder, match["path"])
        if sha(path) != match["sha256"]:
            raise Blocked("Collected overlay checksum changed.")
        field = record_identity_field(snapshot, overlay.get("selection", {}), scope["inputs"], fixtures, key)
    actual = gpd.read_parquet(path)
    if field not in actual or not check_membership(actual[field], expected_ids)["pass"]:
        raise Blocked("Contour overlay membership is incomplete or incorrect.")
    source = gpd.read_parquet(source_path).set_index(ROW_ID)
    points = actual.set_index(field).to_crs(source.crs)
    if overlay.get("count") != len(points):
        raise Blocked("Overlay final count disagrees with its artifact.")
    for fid, geometry in points.geometry.items():
        if not same_overlay_geometry(geometry, source.loc[fid].geometry):
            raise Blocked("Overlay geometry was changed from the frozen source.")
    bound_layer(snapshot, match, overlay.get("map_layer_id"))
