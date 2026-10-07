"""Independent numeric point-to-segment oracle: no production distance implementation."""

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from scipy.spatial import cKDTree

from .common import Blocked, sha
from .population_oracles import quadrature_areas
from .population_tasks import POPULATION_TASKS


def segments(geometries):
    pairs = []
    for geometry in geometries:
        if (
            geometry is None
            or geometry.is_empty
            or not geometry.is_valid
            or geometry.geom_type not in {"LineString", "MultiLineString"}
        ):
            raise Blocked("Railway fixture requires valid nonempty original line geometry.")
        for line in geometry.geoms if geometry.geom_type == "MultiLineString" else [geometry]:
            xy = np.asarray(line.coords)[:, :2]
            pairs.extend(zip(xy[:-1], xy[1:], strict=True))
    if not pairs:
        raise Blocked("No original railway segments exist.")
    result = np.asarray(pairs, dtype="float64")
    if not np.isfinite(result).all():
        raise Blocked("Nonfinite projected railway vertices.")
    return result


def segment_distances(points, lines):
    """KD midpoint bound is exhaustive; final distances use the dot-product formula."""
    first, delta = lines[:, 0], lines[:, 1] - lines[:, 0]
    norm = np.einsum("ij,ij->i", delta, delta)
    midpoint = first + delta / 2
    tree = cKDTree(midpoint)
    max_half = float(np.sqrt(norm).max() / 2)
    output = np.empty(len(points), dtype="float64")
    block = min(256, max(1, 1_000_000 // len(lines)))

    def distances(point, idx):
        vector = point - first[idx]
        parameter = np.divide(
            np.einsum("ij,ij->i", vector, delta[idx]), norm[idx], out=np.zeros(len(idx)), where=norm[idx] > 0
        )
        residual = vector - np.clip(parameter, 0, 1)[:, None] * delta[idx]
        return np.sqrt(np.einsum("ij,ij->i", residual, residual))

    for start in range(0, len(points), block):
        p = np.asarray(points[start : start + block])
        _, nearest = tree.query(p, k=1)
        upper = distances(p, np.asarray(nearest))
        # Any segment closer than upper has midpoint within upper + half-length.
        candidates = tree.query_ball_point(p, upper + max_half + 1e-6)
        sizes = np.asarray([len(c) for c in candidates])
        idx = np.concatenate(candidates).astype(int)
        owner = np.repeat(np.arange(len(p)), sizes)
        actual = distances(p[owner], idx)
        best = np.full(len(p), np.inf)
        np.minimum.at(best, owner, actual)
        output[start : start + len(p)] = best
    return output


def projected_answer(directory, task, assets):
    directory = Path(directory)
    spec = POPULATION_TASKS[task]
    line_path = directory / assets[spec["points"]]["path"]
    frame = gpd.read_parquet(line_path).to_crs(spec["distanceCrs"])
    lines = segments(frame.geometry)
    path = directory / assets[spec["raster"]]["path"]
    with rasterio.open(path) as ds:
        raw = ds.read(1, masked=True).astype("float64")
        density = raw.data * ds.scales[0] + ds.offsets[0]
        valid = ~np.ma.getmaskarray(raw) & np.isfinite(density)
        if (density[valid] < 0).any():
            raise Blocked("Unknown negative population density.")
        area = np.broadcast_to(quadrature_areas(ds.transform, ds.height, ds.crs)[:, None], raw.shape)
        people = density * area
        rows, cols = np.nonzero(valid)
        x = ds.transform.c + (cols + 0.5) * ds.transform.a
        y = ds.transform.f + (rows + 0.5) * ds.transform.e
        x, y = Transformer.from_crs(ds.crs, spec["distanceCrs"], always_xy=True).transform(x, y)
        coordinates = np.column_stack([x, y])
        distances = segment_distances(coordinates, lines)
        # Separate GEOS kernel cross-check of bounded fixed indices, not the oracle's algorithm.
        import shapely

        check = np.linspace(0, len(coordinates) - 1, min(64, len(coordinates)), dtype=int)
        check_values = shapely.distance(
            shapely.points(coordinates[check]), shapely.union_all(frame.geometry.array)
        )
        if not np.allclose(check_values, distances[check], atol=1e-7, rtol=1e-10):
            raise Blocked("Independent point-to-segment cross-check failed.")
        if np.any(np.abs(distances - spec["threshold"]) < 0.01):
            raise Blocked(
                "Numerically ambiguous corridor boundary cell; freeze a precision convention first."
            )
        distance = np.full(raw.shape, np.nan)
        distance[rows, cols] = distances
        selected = valid & (distance <= spec["threshold"])
        total = math.fsum(people[valid])
        included = math.fsum(people[selected])
        if total <= 0:
            raise Blocked("Population denominator must be positive.")
        metrics = {"selected_people": included, "total_people": total, "percentage": 100 * included / total}
        if spec.get("compareDensity"):
            total_area = math.fsum(area[valid])
            selected_area = math.fsum(area[selected])
            if selected_area <= 0:
                raise Blocked("No valid corridor area for density comparison.")
            metrics.update(
                corridor_density=included / selected_area,
                national_density=total / total_area,
                selected_area_km2=selected_area,
                total_area_km2=total_area,
            )
        folder = directory / "oracle-assets"
        folder.mkdir(exist_ok=True)
        target = folder / f"{task}-projected-population.npz"
        np.savez_compressed(
            target,
            distance=distance,
            selected=np.where(valid, np.where(selected, people, 0), np.nan),
            valid=valid,
        )
        return {
            "family": "population-distance-share",
            "derivedField": "distance",
            "derivedUnit": "m",
            "count": int(selected.sum()),
            "unknownCount": int((~valid).sum()),
            "metrics": metrics,
            "grid": {"crs": str(ds.crs), "transform": list(ds.transform)[:6], "shape": list(raw.shape)},
            "reference": str(target.relative_to(directory)),
            "referenceSha256": sha(target),
            "sourceSha256": sha(path),
            "pointSourceSha256": sha(line_path),
            "pointIds": sorted(frame["benchmark_row_id"]),
            "raster": spec["raster"],
            "tolerance": {"absolute": 0.001, "relative": 2e-6},
            "coverage": "Original valid density cells converted with ellipsoidal physical cell area; projected centre-to-original-line corridor, not travel accessibility or contemporaneous observations.",
        }
