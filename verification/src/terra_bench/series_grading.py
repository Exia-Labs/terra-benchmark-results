from pathlib import Path

import geopandas as gpd

from .common import Blocked, beneath, sha, timestamp
from .fixtures import ROW_ID
from .lineage import record_identity_field
from .map_oracles import check_map
from .policy import identity, trusted_reuse


def check_series_structure(claim, expected):
    panels = claim.get("panels")
    if (
        not isinstance(panels, list)
        or len(panels) != len(expected["panels"])
        or {p.get("year") for p in panels} != set(expected["panels"])
    ):
        raise Blocked("Map series is missing a year or repeats a panel.")
    if claim["count"] != len(panels) or claim["unknown_count"] != len(expected["unknownIds"]):
        raise Blocked("Map-series total or unknown country-year coverage disagrees with the reference.")
    if len({p.get("map_layer_id") for p in panels}) != len(panels):
        raise Blocked("Each year must have a distinct delivered map layer.")
    first = next(p for p in panels if p["year"] == next(iter(expected["panels"])))
    if identity(first.get("selection", {})) != identity(claim["selection"]):
        raise Blocked("Map-series anchor selection is not the first-year panel.")
    return panels


def grade_series(task, claim, expected, snapshot, frozen, fixtures, scope, folder, deadline):
    from .grading import check_extra_results, check_membership

    panels = check_series_structure(claim, expected)
    trusted = {identity(a) for a in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True)}
    source_path = Path(frozen["fixtureDirectory"]) / fixtures["assets"]["countries"]["path"]
    if sha(source_path) != fixtures["assets"]["countries"]["sha256"]:
        raise Blocked("Map-series original boundaries changed after freeze.")
    original = gpd.read_parquet(source_path).set_index(ROW_ID)
    for p in panels:
        ref = expected["panels"][p["year"]]
        artifact = next(
            (a for a in snapshot.get("artifacts", []) if identity(a) == identity(p.get("selection", {}))),
            None,
        )
        if (
            not artifact
            or not artifact.get("finishedAt")
            or timestamp(artifact["finishedAt"]) > deadline
            or identity(artifact) not in trusted
        ):
            raise Blocked("Map-series panel lacks a pre-deadline authorized artifact.")
        path = beneath(folder, artifact["path"])
        if sha(path) != artifact["sha256"]:
            raise Blocked("Map-series artifact checksum changed.")
        frame = gpd.read_parquet(path)
        field = record_identity_field(snapshot, p["selection"], scope["inputs"], fixtures, "countries")
        if field not in frame or not check_membership(frame[field], ref["ids"])["pass"]:
            raise Blocked("Map-series panel has incorrect original feature membership.")
        spatial = frame.set_index(field).to_crs(original.crs)
        if any(
            not geom.equals_exact(original.loc[fid].geometry, tolerance=1e-8, normalize=True)
            for fid, geom in spatial.geometry.items()
        ):
            raise Blocked("Map-series boundaries differ from the original geography.")
        if p.get("count") != ref["count"] or p.get("unknown_count") != len(ref["unknownIds"]):
            raise Blocked("Map-series panel counts disagree with its data.")
        check_extra_results(frame, field, p, ref)
        if ref.get("bivariate"):
            from .bivariate_oracles import check_bivariate
            check_bivariate(frame,field,p,ref,snapshot,artifact)
        else:
            check_map(frame, field, p, ref, snapshot, artifact)
