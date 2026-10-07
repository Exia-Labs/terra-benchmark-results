"""Full rasters and final numbers, independently verified; no production imports."""

import math
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

from .common import Blocked, beneath, sha, timestamp
from .policy import identity, trusted_reuse
from .units import same_unit


def check_population_raster(path, values, expected, unit):
    with rasterio.open(path) as source:
        grid = expected["grid"]
        if (
            source.count != 1
            or str(source.crs) != grid["crs"]
            or list(source.shape) != grid["shape"]
            or not source.transform.almost_equals(Affine(*grid["transform"]), precision=1e-10)
        ):
            raise Blocked("Population result changed the original grid, extent or band count.")
        actual = source.read(1, masked=True)
        mask = ~np.isfinite(values)
        if not np.array_equal(np.ma.getmaskarray(actual), mask):
            raise Blocked("Population result changed missing-data coverage.")
        # On the verified unchanged native grid, each value is a number of
        # people. "Per cell" identifies its support, not a density conversion.
        native_count_unit = unit == "people per cell" and same_unit(source.units[0], "people")
        if not same_unit(source.units[0], unit) and not native_count_unit:
            raise Blocked("Population result units do not match the declared physical quantity.")
        if not np.allclose(
            actual.data[~mask],
            values[~mask],
            **{"atol": expected["tolerance"]["absolute"], "rtol": expected["tolerance"]["relative"]},
        ):
            raise Blocked("Population raster values differ from the independent cell-by-cell calculation.")


def grade_population(task, claim, expected, snapshot, frozen, scope, folder, deadline):
    directory = Path(frozen["fixtureDirectory"])
    reference = directory / expected["reference"]
    if sha(reference) != expected["referenceSha256"]:
        raise Blocked("Independent population reference checksum changed.")
    trusted = {identity(a) for a in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True)}
    with np.load(reference) as saved:
        for key, field, unit in expected.get("rasterChecks", [
            ("selection", "selected", "people per cell"),
            (
                expected.get("derivedField", "density"),
                expected.get("derivedField", "density"),
                expected.get("derivedUnit", "people/km2"),
            ),
        ]):
            selected = claim.get(key, {})
            artifact = next(
                (a for a in snapshot.get("artifacts", []) if identity(a) == identity(selected)), None
            )
            if not artifact or identity(artifact) not in trusted:
                raise Blocked("Population output lacks collected authorized fixture-only lineage.")
            if not artifact.get("finishedAt") or timestamp(artifact["finishedAt"]) > deadline:
                raise Blocked("Population output was not verified before the deadline.")
            path = beneath(folder, artifact["path"])
            if sha(path) != artifact["sha256"]:
                raise Blocked("Collected population artifact checksum changed.")
            check_population_raster(path, saved[field], expected, unit)
            map_key = "map_layer_id" if key == "selection" else f"{key}_map_layer_id"
            if claim.get(map_key):
                from .map_bindings import verify_map_binding

                verify_map_binding(snapshot, artifact, claim[map_key])
    if claim["count"] != expected["count"] or claim["unknown_count"] != expected["unknownCount"]:
        raise Blocked("Final qualifying-cell or missing-cell count differs from the independent evidence.")
    metrics = claim.get("metrics", {})
    if set(metrics) != set(expected["metrics"]):
        raise Blocked("Final population metrics are incomplete.")
    for key, value in metrics.items():
        if (
            type(value) not in {int, float}
            or not math.isfinite(value)
            or not math.isclose(value, expected["metrics"][key], rel_tol=2e-6, abs_tol=1e-4)
        ):
            raise Blocked(
                "Final population percentage or totals disagree with the independent raster calculation."
            )
