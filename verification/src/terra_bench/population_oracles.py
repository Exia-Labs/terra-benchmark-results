"""Evaluator-only density reference using independent Gaussian quadrature."""

import math
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS

from .common import Blocked, sha
from .population_tasks import POPULATION_TASKS


def quadrature_areas(transform, height, crs):
    crs = CRS.from_user_input(crs)
    if not crs.is_geographic or transform.b or transform.d or transform.a <= 0 or transform.e >= 0:
        raise Blocked("Population oracle requires the original north-up geographic grid.")
    a, b = crs.ellipsoid.semi_major_metre, crs.ellipsoid.semi_minor_metre
    e2 = 1 - (b / a) ** 2
    nodes, weights = np.polynomial.legendre.leggauss(32)
    upper = np.deg2rad(transform.f + np.arange(height) * transform.e)
    lower = np.deg2rad(transform.f + (np.arange(height) + 1) * transform.e)
    phi = (upper + lower)[:, None] / 2 + (upper - lower)[:, None] * nodes / 2
    jacobian = a * a * (1 - e2) * np.cos(phi) / (1 - e2 * np.sin(phi) ** 2) ** 2
    areas = ((jacobian * weights).sum(axis=1) * (upper - lower) / 2) * math.radians(transform.a) / 1e6
    if not np.isfinite(areas).all() or (areas <= 0).any():
        raise Blocked("Invalid independent ellipsoidal cell area.")
    return areas


def population_answer(directory, task, assets):
    if POPULATION_TASKS[task].get("points"):
        from .population_distance_oracles import distance_answer

        return distance_answer(directory, task, assets)
    directory = Path(directory)
    path = directory / assets[POPULATION_TASKS[task]["raster"]]["path"]
    with rasterio.open(path) as source:
        raw = source.read(1, masked=True).astype("float64")
        valid = ~np.ma.getmaskarray(raw) & np.isfinite(raw.data)
        counts = raw.data * source.scales[0] + source.offsets[0]
        if (counts[valid] < 0).any():
            raise Blocked("Population counts contain an unexplained negative valid value.")
        areas = quadrature_areas(source.transform, source.height, source.crs)
        density = counts / areas[:, None]
        # Standard float32 map algebra must not flip a strict threshold in these fixtures.
        if np.any(valid & (np.abs(density - 1000) < 0.001)):
            raise Blocked(
                "A source cell is numerically ambiguous at the strict density threshold; freeze a precision convention before running."
            )
        selected = valid & (density > 1000)
        total = math.fsum(counts[valid].tolist())
        included = math.fsum(counts[selected].tolist())
        if total <= 0:
            raise Blocked("Population denominator is empty or zero.")
        # Cross-check full-grid reduction by independent row-wise stable sums.
        if not math.isclose(
            total,
            sum(math.fsum(row[mask].tolist()) for row, mask in zip(counts, valid, strict=True)),
            rel_tol=1e-12,
        ):
            raise Blocked("Population summation cross-check failed.")
        density = np.where(valid, density, np.nan)
        selected_counts = np.where(valid, np.where(selected, counts, 0.0), np.nan)
        folder = directory / "oracle-assets"
        folder.mkdir(exist_ok=True)
        target = folder / f"{task}-population.npz"
        np.savez_compressed(target, density=density, selected=selected_counts, valid=valid)
        return {
            "family": "population-density-share",
            "count": int(selected.sum()),
            "unknownCount": int((~valid).sum()),
            "metrics": {
                "selected_people": included,
                "total_people": total,
                "percentage": 100 * included / total,
            },
            "grid": {
                "crs": str(source.crs),
                "transform": list(source.transform)[:6],
                "shape": list(raw.shape),
            },
            "reference": str(target.relative_to(directory)),
            "referenceSha256": sha(target),
            "sourceSha256": sha(path),
            "raster": POPULATION_TASKS[task]["raster"],
            "tolerance": {"absolute": 0.0001, "relative": 2e-6},
            "coverage": "Original valid 2020 WorldPop raster coverage; missing cells remain unknown. No land-only denominator or current population is claimed.",
        }
