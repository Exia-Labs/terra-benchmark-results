"""Check full original-data overlays and authoritative map bindings offline."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

from .common import Blocked, beneath, sha, timestamp
from .fixtures import ROW_ID
from .map_bindings import verify_map_binding
from .overlay_tasks import OVERLAY_TASKS
from .policy import identity, trusted_reuse


def overlay_answer(directory, task, assets):
    spec = OVERLAY_TASKS[task]
    frame = gpd.read_parquet(Path(directory) / assets[spec["vector"]]["path"])
    for field, values in spec.get('filter', {}).items():
        frame = frame.loc[frame[field].isin(values)]
    with rasterio.open(Path(directory) / assets[spec["raster"]]["path"]) as src:
        missing = 0
        for _, window in src.block_windows(1):
            values = src.read(1, masked=True, window=window)
            missing += int((np.ma.getmaskarray(values) | ~np.isfinite(values.data)).sum())
    return {
        "family": "source-overlay",
        "count": len(frame),
        "unknownCount": missing,
        "deriveDensity": spec.get('deriveDensity', False),
        "raster": spec["raster"],
        "vector": spec["vector"],
        "ids": frame[ROW_ID].tolist(),
        "sourceHashes": {key: assets[key]["sha256"] for key in (spec["raster"], spec["vector"])},
    }


def check_overlay_raster(actual_path, source_path, *, derive_density=False):
    with rasterio.open(actual_path) as actual, rasterio.open(source_path) as source:
        if (
            actual.count != 1
            or actual.crs != source.crs
            or actual.shape != source.shape
            or not actual.transform.almost_equals(source.transform, precision=1e-10)
        ):
            raise Blocked("Overlay density grid or band changed.")
        from .population_oracles import quadrature_areas
        areas = quadrature_areas(source.transform, source.height, source.crs) if derive_density else None
        exact_copy = not derive_density
        for _, window in source.block_windows(1):
            a, s = actual.read(1, masked=True, window=window), source.read(1, masked=True, window=window)
            sm = np.ma.getmaskarray(s) | ~np.isfinite(s.data)
            am = np.ma.getmaskarray(a) | ~np.isfinite(a.data)
            expected = s.data.astype('float64') * source.scales[0] + source.offsets[0]
            if areas is not None:
                expected /= areas[int(window.row_off):int(window.row_off+window.height), None]
            observed = a.data.astype('float64') * actual.scales[0] + actual.offsets[0]
            exact_copy = exact_copy and np.array_equal(observed[~sm], expected[~sm])
            if not np.array_equal(sm, am) or not np.allclose(observed[~sm], expected[~sm], rtol=2e-6, atol=1e-7):
                raise Blocked("Overlay changed density values or missing coverage.")
        from .units import same_unit

        # Original frozen WorldPop bytes omit the TIFF band-unit tag; their
        # independently verified fixture contract supplies the physical units.
        # A lossless re-encoding also retains that fixture contract, but a
        # numerical conversion or an explicit conflicting tag cannot inherit it.
        unchanged = sha(actual_path) == sha(source_path)
        if not same_unit(actual.units[0], "people/km2") and not ((unchanged or exact_copy) and actual.units[0] is None):
            raise Blocked("Overlay density has incorrect physical units.")


def grade_overlay(task, claim, expected, snapshot, frozen, scope, folder, deadline):
    from .common import read
    from .grading import check_membership
    from .lineage import record_identity_field

    fixtures = read(Path(frozen["fixtureDirectory"]) / "fixtures.json")
    trusted = {identity(a) for a in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True)}
    selections = [
        (expected["raster"], claim.get("selection", {}), claim.get("map_layer_id")),
        (
            expected["vector"],
            claim.get("overlay", {}).get("selection", {}),
            claim.get("overlay", {}).get("map_layer_id"),
        ),
    ]
    if selections[0][2] == selections[1][2]:
        raise Blocked("Overlay requires two distinct map layers.")
    for key, selected, layer_id in selections:
        spec = fixtures["assets"][key]
        source = Path(frozen["fixtureDirectory"]) / spec["path"]
        if sha(source) != expected["sourceHashes"][key]:
            raise Blocked("Overlay source checksum changed.")
        if identity(selected) == identity(scope["inputs"][key]):
            actual = source
            artifact = scope["inputs"][key]
            field = ROW_ID
        else:
            artifact = next(
                (a for a in snapshot.get("artifacts", []) if identity(a) == identity(selected)), None
            )
            if (
                not artifact
                or identity(artifact) not in trusted
                or not artifact.get("finishedAt")
                or timestamp(artifact["finishedAt"]) > deadline
            ):
                raise Blocked("Overlay output lacks authorized pre-deadline source lineage.")
            actual = beneath(folder, artifact["path"])
            if sha(actual) != artifact["sha256"]:
                raise Blocked("Overlay output checksum changed.")
            field = (
                record_identity_field(snapshot, selected, scope["inputs"], fixtures, key)
                if key == expected["vector"]
                else None
            )
        if key == expected["raster"]:
            check_overlay_raster(actual, source, derive_density=expected.get('deriveDensity', False))
        else:
            frame = gpd.read_parquet(actual)
            base = gpd.read_parquet(source).set_index(ROW_ID)
            if field not in frame or not check_membership(frame[field], expected["ids"])["pass"]:
                raise Blocked("Overlay railway membership changed.")
            frame = frame.set_index(field).to_crs(base.crs)
            if any(
                not geom.equals_exact(base.loc[fid].geometry, tolerance=1e-8, normalize=True)
                for fid, geom in frame.geometry.items()
            ):
                raise Blocked("Overlay original railway geometry changed.")
        verify_map_binding(snapshot, artifact, layer_id)
        tiles = snapshot.get("mapDisplays", {}).get(layer_id, {}).get("tilesets", [])
        required = "coverage" if key == expected["raster"] else "vector"
        if not tiles or (
            required == "coverage"
            and not any(
                t.get("dataType") == "coverage" and t.get("blue:display_style") == "continuous-default"
                for t in tiles
            )
        ):
            raise Blocked("Overlay lacks its quantitative raster or line renderer.")
    if claim["count"] != expected["count"] or claim["unknown_count"] != expected["unknownCount"]:
        raise Blocked("Overlay final feature count or missing coverage differs.")
