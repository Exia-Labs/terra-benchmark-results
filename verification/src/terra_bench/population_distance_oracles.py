"""Population exposure reference: original cell counts and independent geodesics."""

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

from .common import Blocked, sha
from .geodesic_oracle import nearest_distances
from .population_tasks import POPULATION_TASKS


def distance_answer(directory, task, assets):
    if POPULATION_TASKS[task].get('method') == 'projected-features':
        from .projected_population_oracle import projected_answer
        return projected_answer(directory,task,assets)
    directory = Path(directory)
    spec = POPULATION_TASKS[task]
    point_path = directory / assets[spec["points"]]["path"]
    frame = gpd.read_parquet(point_path)
    frame = frame.loc[frame[spec["countryField"]].eq(spec["country"])].to_crs(4326)
    if frame.empty or frame.geometry.isna().any() or not frame.geom_type.eq("Point").all():
        raise Blocked("Population-distance fixture lacks a complete nonempty Point selection.")
    points = np.column_stack([frame.geometry.x, frame.geometry.y])
    path = directory / assets[spec["raster"]]["path"]
    with rasterio.open(path) as source:
        if source.crs.to_epsg() != 4326 or source.transform.b or source.transform.d:
            raise Blocked("Population-distance oracle requires the original north-up WGS84 grid.")
        raw = source.read(1, masked=True).astype("float64")
        counts = raw.data * source.scales[0] + source.offsets[0]
        valid = ~np.ma.getmaskarray(raw) & np.isfinite(counts)
        if (counts[valid] < 0).any():
            raise Blocked("Negative population counts are not silently discarded.")
        distance = np.full(raw.shape, np.nan)
        for start in range(0, source.height, 128):
            rows, cols = np.nonzero(valid[start : start + 128])
            lon = source.transform.c + (cols + 0.5) * source.transform.a
            lat = source.transform.f + (start + rows + 0.5) * source.transform.e
            distance[start + rows, cols] = nearest_distances(lon, lat, points)
        if np.any(valid & (np.abs(distance - spec["threshold"]) < 0.01)):
            raise Blocked(
                "Distance threshold has a numerically ambiguous cell; resolve precision before dispatch."
            )
        selected = valid & (
            (distance <= spec["threshold"]) if spec["operator"] == "lte" else (distance > spec["threshold"])
        )
        total = math.fsum(counts[valid].tolist())
        included = math.fsum(counts[selected].tolist())
        if total <= 0:
            raise Blocked("Population denominator must contain positive total population.")
        selected_counts = np.where(valid, np.where(selected, counts, 0.0), np.nan)
        folder = directory / "oracle-assets"
        folder.mkdir(exist_ok=True)
        target = folder / f"{task}-population-distance.npz"
        np.savez_compressed(target, distance=distance, selected=selected_counts, valid=valid)
        return {
            "family": "population-distance-share",
            "derivedField": "distance",
            "derivedUnit": "m",
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
            "pointSourceSha256": sha(point_path),
            "pointIds": sorted(frame["benchmark_row_id"]),
            "raster": spec["raster"],
            "tolerance": {"absolute": 0.001, "relative": 2e-6},
            "coverage": "Original valid country raster and supplied country-specific facility inventory. Centre-based geodesic proximity, not travel accessibility.",
        }
