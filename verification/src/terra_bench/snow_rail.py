"""Independent pixel-crossing oracle for railway length, not production clipping."""

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Geod
from shapely.geometry import LineString, MultiLineString

from .common import Blocked, sha

TASK = "310610"


def protocol():
    return {
        TASK: {
            "question": "What is the total length of railways within areas that received more than 3 feet of snow this season in the USA?",
            "title": "Railway length inside observed deep-snow cells",
            "family": "clipped-line-length",
            "bbox": [-128, 18, -64, 58],
            "clarification": "Use original NARN railway records with COUNTRY='US' and the frozen 2024-09-30 to 2025-05-20 snowfall raster, band 1 in inches. Season means that archive, not today. Define snowy areas as the CLOSED native pixel footprints with finite unmasked snowfall strictly >36 inches, applying scale/offset. Clip the original railway geometry to their union BEFORE measuring; do not sum entire lines or counties that merely touch a contour. Keep original source feature identity on fragments. Measure clipped lines in km using shortest WGS84 ellipsoidal geodesics between original and intersection vertices. Source line interpolation for clipping is straight in the original geographic grid; this is not route distance. A boundary shared with a qualifying pixel is included; zero-length touches contribute zero. Multiple qualifying polygons must not double-count a source line portion; different original railway records remain distinct (no inferred track conflation). NoData/outside-raster means unknown, not low snowfall: disclose that the length describes observed coverage, not a complete all-USA weather total. The benchmark's released reference selects whole lines/counties; this protocol corrects that mismatch with the stated length-within-areas question.",
            "outputContract": "Publish an inspectable CLIPPED line artifact preserving the original benchmark_row_id (a documented prefix is fine). Map optional. End with one fenced JSON: {count:number of distinct original US railway records with positive clipped length, unknown_count:number of original US railway records with any positive-length portion lacking raster observations, metrics:{length_km:number}, coverage_note:string, selection:{collectionId,itemId,assetKey}}. Explain historical season, strict snow threshold and incomplete observation coverage. Do not round machine-readable length to whole kilometres.",
        }
    }


def split_segment(first, second, inverse, values, valid):
    """Split by exact grid lines; inspect midpoint cells instead of polygon overlay."""
    x0, y0 = inverse * tuple(first)
    x1, y1 = inverse * tuple(second)
    changes = [0.0, 1.0]
    for a, b in [(x0, x1), (y0, y1)]:
        if a != b:
            changes.extend(
                (edge - a) / (b - a)
                for edge in range(math.floor(min(a, b)) + 1, math.ceil(max(a, b)))
                if 0 < (edge - a) / (b - a) < 1
            )
    changes = sorted(set(changes))
    pieces = []
    unknown = False
    for start, end in zip(changes, changes[1:]):
        if end - start < 1e-14:
            continue
        mid = (start + end) / 2
        x, y = x0 + (x1 - x0) * mid, y0 + (y1 - y0) * mid
        cols = {math.floor(x)}
        rows = {math.floor(y)}
        if abs(x - round(x)) < 1e-10:
            cols |= {round(x) - 1, round(x)}
        if abs(y - round(y)) < 1e-10:
            rows |= {round(y) - 1, round(y)}
        cells = [(r, c) for r in rows for c in cols if 0 <= r < valid.shape[0] and 0 <= c < valid.shape[1]]
        known = [(r, c) for r, c in cells if valid[r, c]]
        selected = any(values[r, c] > 36 for r, c in known)
        if not selected and (len(known) < len(rows) * len(cols)):
            unknown = True
        if selected:
            a = np.asarray(first) + (np.asarray(second) - first) * start
            b = np.asarray(first) + (np.asarray(second) - first) * end
            if np.linalg.norm(b - a) > 1e-13:
                pieces.append((a, b))
    return pieces, unknown


def answer(directory, assets):
    directory = Path(directory)
    rails = gpd.read_parquet(directory / assets["na_railways"]["path"])
    rails = rails.loc[rails.COUNTRY == "US"].to_crs(4326)
    with rasterio.open(directory / assets["snow"]["path"]) as src:
        if src.crs.to_epsg() != 4326 or src.transform.b or src.transform.d:
            raise Blocked("Snow length oracle requires the original nonrotated WGS84 raster.")
        raw = src.read(1, masked=True)
        values = raw.data.astype(float) * src.scales[0] + src.offsets[0]
        valid = ~np.ma.getmaskarray(raw) & np.isfinite(values)
        inverse = ~src.transform
    records = []
    unknown = []
    geod = Geod(ellps="WGS84")
    for row in rails.itertuples():
        geom = row.geometry
        if (
            geom is None
            or geom.is_empty
            or not geom.is_valid
            or geom.geom_type not in {"LineString", "MultiLineString"}
        ):
            unknown.append(row.benchmark_row_id)
            continue
        parts = []
        missing = False
        for line in geom.geoms if geom.geom_type == "MultiLineString" else [geom]:
            xy = np.asarray(line.coords)[:, :2]
            for a, b in zip(xy, xy[1:]):
                if np.array_equal(a, b):
                    continue
                pieces, gap = split_segment(a, b, inverse, values, valid)
                parts.extend(pieces)
                missing |= gap
        if missing:
            unknown.append(row.benchmark_row_id)
        if parts:
            vertices = np.asarray(parts)
            _, _, length = geod.inv(
                vertices[:, 0, 0], vertices[:, 0, 1], vertices[:, 1, 0], vertices[:, 1, 1]
            )
            records.append(
                {
                    "benchmark_row_id": row.benchmark_row_id,
                    "length_km": float(np.sum(length)) / 1000,
                    "geometry": MultiLineString([LineString(p) for p in parts]),
                }
            )
    frame = gpd.GeoDataFrame(records, geometry="geometry", crs=4326)
    target = directory / "oracle-snow-rails.parquet"
    frame.to_parquet(target, index=False)
    return {
        "family": "clipped-line-length",
        "count": len(frame),
        "unknownCount": len(unknown),
        "unknownIds": unknown,
        "metrics": {"length_km": math.fsum(frame.length_km)},
        "reference": target.name,
        "referenceSha256": sha(target),
    }


def grade(frame, claim, expected, directory, identity_field):
    from .common import Blocked

    target = Path(directory) / expected["reference"]
    if sha(target) != expected["referenceSha256"]:
        raise Blocked("Clipped-line oracle changed after freeze.")
    reference = gpd.read_parquet(target).set_index("benchmark_row_id")
    if identity_field not in frame or frame[identity_field].isna().any():
        raise Blocked("Clipped lines lost original identity.")
    actual = frame.to_crs(4326)
    if set(actual[identity_field]) != set(reference.index):
        raise Blocked("Clipped line source membership differs.")
    geod = Geod(ellps="WGS84")
    for fid, group in actual.groupby(identity_field):
        combined = group.geometry.union_all()
        expected_geometry = reference.loc[fid].geometry
        if (
            combined.hausdorff_distance(expected_geometry) > 1e-8
            or abs(combined.length - expected_geometry.length) > 1e-8
        ):
            raise Blocked(
                "Railway geometry is not exactly the selected portion; whole-line selection is insufficient."
            )
        measured = sum(abs(geod.geometry_length(g)) for g in group.geometry) / 1000
        if not math.isclose(measured, reference.loc[fid].length_km, rel_tol=1e-6, abs_tol=1e-5):
            raise Blocked("Duplicated fragments or clipped length mismatch.")
    if (
        claim["count"] != expected["count"]
        or claim["unknown_count"] != expected["unknownCount"]
        or not math.isclose(
            claim.get("metrics", {}).get("length_km", float("nan")),
            expected["metrics"]["length_km"],
            rel_tol=1e-6,
            abs_tol=1e-4,
        )
    ):
        raise Blocked("Final railway length, source count, or unknown-coverage count is incorrect.")
