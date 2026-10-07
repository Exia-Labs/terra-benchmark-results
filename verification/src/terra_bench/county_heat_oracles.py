from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from .common import Blocked, sha
from .county_tasks import COUNTY_GRID, COUNTY_HEAT_TASKS, COUNTY_RADIUS
from .fixtures import ROW_ID
from .heat_oracles import heat_values


def polygon_centroid(geometry):
    """Independent shoelace moments; holes subtract area, multipart areas combine."""
    components = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    moment = np.zeros(2)
    total = 0.0
    for polygon in components:
        if polygon.geom_type != "Polygon" or not polygon.is_valid:
            raise Blocked("County centroid requires valid polygon geometry.")
        for ring, sign in [(polygon.exterior, 1), *((r, -1) for r in polygon.interiors)]:
            xy = np.asarray(ring.coords)[:, :2]
            anchor = xy[0].copy()
            xy = xy - anchor
            a, b = xy[:-1], xy[1:]
            cross = a[:, 0] * b[:, 1] - b[:, 0] * a[:, 1]
            signed = float(cross.sum())
            if signed == 0:
                continue
            center = ((a + b) * cross[:, None]).sum(axis=0) / (3 * signed) + anchor
            area = sign * abs(signed) / 2
            moment += center * area
            total += area
    if total <= 0:
        raise Blocked("County geometry has no measurable area.")
    return Point(moment / total)


def county_heat_answer(directory, task, assets):
    directory = Path(directory)
    spec = COUNTY_HEAT_TASKS[task]
    counties = gpd.read_parquet(directory / assets["counties"]["path"])
    selected = counties.loc[counties.STATEFP.isin(spec["states"])].copy()
    values = pd.Series(np.nan, index=selected.index, dtype=float)
    for state, key in spec["states"].items():
        table = pd.read_parquet(directory / assets[key]["path"])
        table = table.loc[table.County.notna()]
        if table.County.dropna().duplicated().any():
            raise Blocked("County heatmap has ambiguous statistical keys.")
        field = "Number of Cases" if key == "tb_ma" else "2023 cases"
        rows = selected.STATEFP == state
        values.loc[rows] = selected.loc[rows, "NAME"].map(
            pd.to_numeric(table.set_index("County")[field], errors="raise")
        )
    known = np.isfinite(values)
    if (values[known] < 0).any():
        raise Blocked("Negative county case count.")
    unknown = sorted(selected.loc[~known, ROW_ID])
    eligible = selected.loc[known].copy()
    weights = values.loc[known]
    projected = eligible.to_crs("EPSG:5070")
    points = projected.geometry.map(polygon_centroid)
    if any(a.distance(b) > 1e-5 for a, b in zip(points, projected.geometry.centroid, strict=True)):
        raise Blocked("Independent centroid moment cross-check failed.")
    projected.geometry = points
    raster = heat_values(projected, weights, COUNTY_GRID, COUNTY_RADIUS)
    path = directory / f"county-heat-reference-{task}.npz"
    np.savez_compressed(path, values=raster)
    return {
        "family": "county-heatmap",
        "ids": sorted(eligible[ROW_ID]),
        "count": len(eligible),
        "unknownIds": unknown,
        "values": dict(zip(eligible[ROW_ID], weights, strict=True)),
        "totalCases": float(weights.sum()),
        "grid": COUNTY_GRID,
        "unit": "sum of cases per grid cell",
        "reference": path.name,
        "referenceSha256": sha(path),
        "tolerance": {"absolute": 1e-5, "relative": 2e-6},
        "mapRequired": True,
    }
