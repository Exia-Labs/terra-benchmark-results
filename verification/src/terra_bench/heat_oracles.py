"""Independent point selection, pixel binning and discrete Gaussian convolution."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.prepared import prep

from .common import Blocked, sha
from .fixtures import ROW_ID
from .heat_tasks import GRID, HEAT_TASKS, RADIUS_M


def heat_selection(task, points, countries, tables, raster=None, lines=None):
    s = HEAT_TASKS[task]
    valid = points.geometry.notna() & ~points.geometry.is_empty & points.geometry.is_valid
    unlocated = set(points.loc[~valid, ROW_ID])
    if s.get("allPoints"):
        located = points.loc[valid].copy()
        weights = pd.to_numeric(located[s["weight"]], errors="raise")
        if (weights.dropna() < 0).any():
            raise Blocked("Negative reported weights need a separate signed-map convention.")
        known = np.isfinite(weights)
        unknown = unlocated | set(located.loc[~known, ROW_ID])
        return located.loc[known], weights.loc[known], sorted(unknown), sorted(unlocated)
    if s.get("nearLines"):
        import shapely

        from .projected_population_oracle import segment_distances, segments

        target = lines.loc[lines[s["lineField"]] == s["lineValue"]].to_crs(s["distanceCrs"])
        located = points.loc[valid].copy()
        projected = located.to_crs(s["distanceCrs"])
        coordinates = np.column_stack([projected.geometry.x, projected.geometry.y])
        if not np.isfinite(coordinates).all():
            raise Blocked("Earthquake coordinates cannot be represented in the declared projection.")
        bounds = target.total_bounds
        possible = (
            (coordinates[:, 0] >= bounds[0] - s["threshold"])
            & (coordinates[:, 0] <= bounds[2] + s["threshold"])
            & (coordinates[:, 1] >= bounds[1] - s["threshold"])
            & (coordinates[:, 1] <= bounds[3] + s["threshold"])
        )
        distances = np.full(len(coordinates), np.inf)
        distances[possible] = segment_distances(coordinates[possible], segments(target.geometry))
        tree = shapely.STRtree(target.geometry.to_numpy())
        indices, check = tree.query_nearest(
            projected.geometry.to_numpy(), all_matches=False, return_distance=True
        )
        ordered = np.empty(len(distances))
        ordered[indices[0]] = check
        if (
            len(check) != len(distances)
            or not np.allclose(distances[possible], ordered[possible], atol=1e-7, rtol=1e-10)
            or np.any(ordered[~possible] < s["threshold"])
        ):
            raise Blocked("Independent Canada point-to-segment distance cross-check failed.")
        if np.any(np.abs(distances - s["threshold"]) < 0.01):
            raise Blocked("Near-threshold event needs a declared precision convention before measurement.")
        selected = located.loc[distances < s["threshold"]].copy()
        return selected, pd.Series(1.0, index=selected.index), sorted(unlocated), sorted(unlocated)
    if s.get("directPoints") or s.get("raster"):
        located = points.loc[valid].copy()
        unknown = set(unlocated)
        if s.get("directPoints"):
            unknown.update(located.loc[located[s["field"]].isna(), ROW_ID])
            selected = located.loc[located[s["field"]].isin(s["members"])].copy()
            return selected, pd.Series(1.0, index=selected.index), sorted(unknown), sorted(unlocated)
        import rasterio

        with rasterio.open(raster) as ds:
            projected = located.to_crs(ds.crs)
            x, y = projected.geometry.x.to_numpy(), projected.geometry.y.to_numpy()
            inverse = ~ds.transform
            cols, rows = inverse * (x, y)
            cols, rows = np.floor(cols).astype(int), np.floor(rows).astype(int)
            inside = (rows >= 0) & (rows < ds.height) & (cols >= 0) & (cols < ds.width)
            values = np.full(len(located), np.nan)
            band = ds.read(1, masked=True)
            sampled = band[rows[inside], cols[inside]].astype(float)
            values[inside] = np.asarray(sampled.filled(np.nan))
            check = np.array(
                [
                    float(v[0]) if not np.ma.is_masked(v[0]) else np.nan
                    for v in ds.sample(zip(x, y, strict=True), masked=True)
                ]
            )
            if not np.allclose(values, check, equal_nan=True):
                raise Blocked("Raster eligibility sample cross-check failed.")
        known = np.isfinite(values)
        unknown.update(located.loc[~known, ROW_ID])
        mask = known & ((values >= s["threshold"]) if s.get('operator') == 'gte' else (values > s["threshold"]))
        selected = located.loc[mask].copy()
        selected[s["weight"]] = values[mask]
        return selected, pd.Series(values[mask], index=selected.index), sorted(unknown), sorted(unlocated)
    region = countries.copy()
    if s.get("field"):
        region = region[region[s["field"]].isin(s["members"])]
    elif not s.get("globalCountries"):
        region = region[region.CONTINENT == "Africa"]

    def v(key, year):
        table = tables[key]
        if table["Country Code"].duplicated().any():
            raise Blocked("Heatmap oracle country keys are not unique.")
        return region.ISO_A3.map(pd.to_numeric(table.set_index("Country Code")[year], errors="raise"))

    measure = None
    if s.get("indicator"):
        measure = v(s["indicator"], s["years"][0])
    elif s.get("derived") == "rural_share":
        denom = v("population", "2023")
        measure = v("rural", "2023") / denom.where(denom > 0)
    elif s.get("derived") == "forest_change":
        measure = v("forest_percent", "2021") - v("forest_percent", "1990")
    elif s.get("derived") == "population_growth":
        denom = v("population", "2010")
        measure = (v("population", "2023") - denom) / denom.where(denom > 0)
    elif s.get("derived") == "gdp_growth":
        denom = v("gdp", "2018")
        measure = v("gdp", "2023") / denom.where(denom > 0)
    qualified = region
    unknown_countries = region.iloc[:0]
    if measure is not None:
        measure = measure.where(np.isfinite(measure))
        condition = {"gt": measure.gt, "gte": measure.ge, "lt": measure.lt}[s["operator"]](s["threshold"])
        qualified = region.loc[condition]
        unknown_countries = region.loc[measure.isna()]
    located = points.loc[valid].to_crs(region.crs)

    def membership(polygons):
        predicate = s.get("predicate", "within")
        matched = set(
            gpd.sjoin(located[[ROW_ID, "geometry"]], polygons[["geometry"]], predicate=predicate)[ROW_ID]
        )
        prepared = [prep(p) for p in polygons.geometry]
        # A second predicate implementation avoids depending on duplicate join rows.
        explicit = {
            row[ROW_ID]
            for _, row in located.iterrows()
            if any(
                p.intersects(row.geometry) if predicate == "intersects" else p.contains(row.geometry)
                for p in prepared
            )
        }
        if matched != explicit:
            raise Blocked("Heatmap membership cross-check failed.")
        return matched

    eligible = membership(qualified)
    unknown = (membership(unknown_countries) | unlocated) - eligible
    selected = located.loc[located[ROW_ID].isin(eligible)].copy()
    weights = (
        pd.to_numeric(selected[s["weight"]], errors="raise")
        if s.get("weight")
        else pd.Series(1.0, index=selected.index)
    )
    if (weights.dropna() < 0).any():
        raise Blocked(
            "Negative frozen heatmap weights require an explicit signed-map convention before measurement."
        )
    known = np.isfinite(weights)
    unknown.update(selected.loc[~known, ROW_ID])
    selected = selected.loc[known]
    weights = weights.loc[known]
    return selected, weights, sorted(unknown), sorted(unlocated)


def heat_values(points, weights, grid=GRID, radius=RADIUS_M):
    minx, miny, maxx, maxy = grid["bounds"]
    dx, dy = grid["resolutionX"], grid["resolutionY"]
    width, height = int(round((maxx - minx) / dx)), int(round((maxy - miny) / dy))
    inverse = Transformer.from_crs(grid["crs"], "OGC:CRS84", always_xy=True)
    _, latitude = inverse.transform([0, 0], [miny, maxy])
    if not np.isfinite(latitude).all():
        raise Blocked("Declared heatmap grid extends beyond the projection's geographic domain.")
    transformer = Transformer.from_crs(points.crs, grid["crs"], always_xy=True)
    x, y = transformer.transform(points.geometry.x.to_numpy(), points.geometry.y.to_numpy())
    cols, rows = (
        np.floor((np.asarray(x) - minx) / dx).astype(int),
        np.floor((maxy - np.asarray(y)) / dy).astype(int),
    )
    if ((cols < 0) | (cols >= width) | (rows < 0) | (rows >= height)).any():
        raise Blocked("The declared heatmap grid fails to cover contributing points.")
    raw = np.zeros((height, width), dtype=float)
    np.add.at(raw, (rows, cols), np.asarray(weights, dtype=float))
    if not np.isclose(raw.sum(), sum(weights), rtol=1e-12, atol=1e-10):
        raise Blocked("Heatmap binning mass cross-check failed.")
    for axis, resolution in ((0, dy), (1, dx)):
        sigma = radius / 3 / resolution
        if sigma == 0:
            continue
        reach = int(4 * sigma + 0.5)
        offsets = np.arange(-reach, reach + 1)
        kernel = np.exp(-(offsets**2) / (2 * sigma**2))
        kernel /= kernel.sum()
        pad = [(0, 0), (0, 0)]
        pad[axis] = (reach, reach)
        padded = np.pad(raw, pad, mode="constant")
        raw = np.apply_along_axis(lambda line: np.convolve(line, kernel, mode="valid"), axis, padded)
    return raw


def heat_answer(directory, task, assets):
    directory = Path(directory)
    s = HEAT_TASKS[task]
    points = gpd.read_parquet(directory / assets[s["base"]]["path"])
    if s.get("literalQuestionSupported") is False:
        # This protocol was explicitly scoped to a source with no final observations.
        # A changed source requires a fresh protocol, not a silent substitution.
        if "FinalAcres" not in points or points["FinalAcres"].notna().any():
            raise Blocked("Reported-size adaptation no longer matches the frozen final-acreage evidence.")
    geography = s.get("geographyAsset", "countries")
    countries = gpd.read_parquet(directory / assets[geography]["path"]) if geography in assets else None
    tables = {
        k: pd.read_parquet(directory / assets[k]["path"])
        for k in s["assets"]
        if k not in {geography, s["base"], s.get("raster"), s.get("nearLines")}
    }
    selected, weights, unknown, unlocated = heat_selection(
        task,
        points,
        countries,
        tables,
        directory / assets[s["raster"]]["path"] if s.get("raster") else None,
        gpd.read_parquet(directory / assets[s["nearLines"]]["path"]) if s.get("nearLines") else None,
    )
    values = heat_values(selected, weights)
    reference = directory / f"heat-reference-{task}.npz"
    np.savez_compressed(reference, values=values)
    return {
        "family": "geographic-heatmap",
        "ids": sorted(selected[ROW_ID]),
        "count": len(selected),
        "unknownIds": unknown,
        "unlocatedPointIds": unlocated,
        "identityField": ROW_ID,
        "grid": GRID,
        "radiusM": RADIUS_M,
        "reference": reference.name,
        "referenceSha256": sha(reference),
        "unit": f"sum of {s['weightUnit']} per grid cell" if s.get("weight") else "events per grid cell",
        "tolerance": {"absolute": 1e-7, "relative": 2e-6},
        "totalInputWeight": float(sum(weights)),
        "totalRasterWeight": float(values.sum()),
    }
