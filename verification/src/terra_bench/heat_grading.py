from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from .common import Blocked, beneath, sha, timestamp
from .contour_grading import bound_layer
from .heat_tasks import HEAT_TASKS
from .policy import identity, trusted_reuse
from .units import same_unit


def check_heat_interpretation(task, claim):
    if HEAT_TASKS.get(task, {}).get("literalQuestionSupported") is False and (
        claim.get("measurement") != "reported_incident_size"
        or claim.get("final_acreage_available") is not False
    ):
        raise Blocked("Reported-size adaptation must disclose that final acreage is unavailable.")


def check_heat_values(path, expected, directory, *, native_count_samples=False):
    reference = Path(directory) / expected["reference"]
    if sha(reference) != expected["referenceSha256"]:
        raise Blocked("Independent heatmap reference checksum changed.")
    with np.load(reference) as saved:
        values = saved["values"]
    with rasterio.open(path) as actual:
        grid = expected["grid"]
        transform = from_bounds(*grid["bounds"], values.shape[1], values.shape[0])
        if (
            actual.count != 1
            or str(actual.crs) != grid["crs"]
            or actual.shape != values.shape
            or not actual.transform.almost_equals(transform, precision=1e-8)
        ):
            raise Blocked("Heatmap grid, CRS, alignment or band count differs from the frozen convention.")
        data = actual.read(1, masked=True)
        if np.ma.getmaskarray(data).any() or not np.isfinite(data).all():
            raise Blocked("Heatmap has masked/nonfinite cells instead of the declared complete grid.")
        count_context = (
            native_count_samples and expected["unit"] == "sum of people per grid cell"
            and actual.units[0] == "sum of people per source cell per grid cell"
        )
        if not same_unit(actual.units[0], expected["unit"]) and not count_context:
            raise Blocked("Heatmap units do not match the declared weights per cell.")
        if not np.allclose(
            data, values, atol=expected["tolerance"]["absolute"], rtol=expected["tolerance"]["relative"]
        ):
            raise Blocked("Heatmap pixel values differ from independent binning and Gaussian convolution.")


def grade_heat(task, claim, expected, snapshot, frozen, scope, folder, deadline):
    check_heat_interpretation(task, claim)
    selection = claim.get("density", {})
    artifact = next((a for a in snapshot.get("artifacts", []) if identity(a) == identity(selection)), None)
    if not artifact or not artifact.get("finishedAt") or timestamp(artifact["finishedAt"]) > deadline:
        raise Blocked("Final answer lacks a collected pre-deadline heatmap raster.")
    if identity(artifact) not in {
        identity(a) for a in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True,
                                           fixture_bounds=scope.get("fixtureBounds"))
    }:
        raise Blocked("Heatmap raster lacks authorized fixture-only lineage.")
    path = beneath(folder, artifact["path"])
    if sha(path) != artifact["sha256"]:
        raise Blocked("Collected heatmap checksum changed.")
    check_heat_values(path, expected, frozen["fixtureDirectory"], native_count_samples=(
        bool(HEAT_TASKS.get(task, {}).get("raster")) and HEAT_TASKS[task].get("weightUnit") == "people"))
    layer_id = claim.get("map_layer_id")
    bound_layer(snapshot, artifact, layer_id)
    if not snapshot.get("mapDisplays", {}).get(layer_id, {}).get("tilesets"):
        raise Blocked("Heatmap has no inspectable renderer tile set.")
