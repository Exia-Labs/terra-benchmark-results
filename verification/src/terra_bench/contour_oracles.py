"""Independent cell-segment oracle; does not call Terra or its contour library."""
from pathlib import Path

import numpy as np
import rasterio
import shapely

from .common import Blocked, sha
from .contour_tasks import CONTOUR_TASKS

# Edges clockwise: top, right, bottom, left. Low corners remain connected at saddles.
PAIRS = {1: [(0, 3)], 2: [(0, 1)], 3: [(1, 3)], 4: [(1, 2)],
         5: [(0, 3), (1, 2)], 6: [(0, 2)], 7: [(2, 3)], 8: [(2, 3)],
         9: [(0, 2)], 10: [(0, 1), (2, 3)], 11: [(1, 2)], 12: [(1, 3)],
         13: [(0, 1)], 14: [(0, 3)]}


def cell_segments(values, valid, level):
    a, b, c, d = values[:-1, :-1], values[:-1, 1:], values[1:, :-1], values[1:, 1:]
    codes = (a > level).astype(np.uint8) + 2*(b > level) + 4*(d > level) + 8*(c > level)
    mask = valid[:-1, :-1] & valid[:-1, 1:] & valid[1:, :-1] & valid[1:, 1:]
    arrays = []
    for code, pairs in PAIRS.items():
        rows, cols = np.where(mask & (codes == code))
        if not len(rows):
            continue
        corners = [a[rows, cols], b[rows, cols], d[rows, cols], c[rows, cols]]
        def edge(index):
            left, right = [(0, 1), (1, 2), (3, 2), (0, 3)][index]
            fraction = (level-corners[left])/(corners[right]-corners[left])
            x = cols + .5 + (fraction if index in (0, 2) else int(index == 1))
            y = rows + .5 + (fraction if index in (1, 3) else int(index == 2))
            return np.column_stack([x, y])
        for first, second in pairs:
            segments = np.stack([edge(first), edge(second)], axis=1)
            segments = segments[np.linalg.norm(segments[:, 1]-segments[:, 0], axis=1) > 1e-12]
            arrays.append(segments)
    return np.concatenate(arrays) if arrays else np.empty((0, 2, 2))


def contour_answer(directory, task, assets):
    directory = Path(directory)
    spec = CONTOUR_TASKS[task]
    with rasterio.open(directory / assets[spec["raster"]]["path"]) as raster:
        raw = raster.read(1, masked=True)
        values = np.asarray(raw, dtype=float) * raster.scales[0] + raster.offsets[0]
        valid = ~np.ma.getmaskarray(raw) & np.isfinite(values)
        if spec.get("floodMask"):
            from .flood_tasks import arrays
            with rasterio.open(directory / assets[spec["floodMask"]]["path"]) as flood:
                _, classification, _ = arrays(raster, flood, "density")
            valid &= classification == 1
        if spec.get('deriveDensity'):
            from .population_oracles import quadrature_areas
            values /= quadrature_areas(raster.transform, raster.height, raster.crs)[:, None]
        segments = {f"level_{i}": cell_segments(values, valid, level) for i, level in enumerate(spec["levels"])}
        reference = directory / f"contour-reference-{task}.npz"
        np.savez_compressed(reference, **segments)
        result = {"family": "contour-map", "count": sum(bool(len(s)) for s in segments.values()),
            "unknownCount": int((~valid).sum()), "unit": spec["unit"], "levels": spec["levels"],
            "sourceCrs": str(raster.crs), "transform": list(raster.transform),
            "segmentCounts": [len(segments[f"level_{i}"]) for i in range(len(spec["levels"]))],
            "reference": reference.name, "referenceSha256": sha(reference), "tolerancePixels": 1e-5}
    if spec.get("overlay"):
        import geopandas as gpd
        frame = gpd.read_parquet(directory / assets[spec["overlay"]]["path"])
        for field, allowed in spec.get("filter", {}).items():
            frame = frame[frame[field].isin(allowed)]
        if spec.get('overlaySelector'):
            sel = spec['overlaySelector']
            geography = gpd.read_parquet(directory / assets[sel['geography']]['path']).to_crs(frame.crs)
            region = geography.loc[geography[sel['field']] == sel['value']] if sel.get('field') else geography
            ids = set(gpd.sjoin(frame[['benchmark_row_id','geometry']], region[['geometry']], predicate=sel['predicate']).benchmark_row_id)
            frame = frame.loc[frame.benchmark_row_id.isin(ids)]
        result["overlayIds"] = sorted(frame.benchmark_row_id)
    if spec.get('contexts'):
        result['contextIds'] = {key: sorted(gpd.read_parquet(directory / assets[key]['path']).benchmark_row_id)
                                for key in spec['contexts']}
    return result


def complete_intervals(indices, starts, ends, lengths, tolerance):
    """Prove every segment is covered exactly once; splitting/orientation is immaterial."""
    if len(lengths) == 0:
        return not len(indices)
    order = np.lexsort((starts, indices))
    last_index, end, covered = -1, 0., 0
    for pos in order:
        index, start, stop = int(indices[pos]), float(starts[pos]), float(ends[pos])
        if index != last_index:
            if last_index >= 0 and abs(end-lengths[last_index]) > tolerance:
                return False
            if index != last_index+1 or start > tolerance:
                return False
            last_index, end = index, stop
            covered += 1
        else:
            if abs(start-end) > tolerance:  # gap or overlap/duplicate
                return False
            end = stop
    return covered == len(lengths) and abs(end-lengths[-1]) <= tolerance


def same_segments(actual, expected, tolerance=1e-5):
    if not len(actual) or not len(expected):
        return len(actual) == len(expected)
    av, ev = actual[:, 1]-actual[:, 0], expected[:, 1]-expected[:, 0]
    al, el = np.linalg.norm(av, axis=1), np.linalg.norm(ev, axis=1)
    if not np.isfinite(actual).all() or (al <= 1e-12).any():
        return False
    tree = shapely.STRtree(shapely.linestrings(expected))
    pairs = tree.query(shapely.linestrings(actual), predicate="dwithin", distance=tolerance)
    ai, ei = pairs
    if not len(ai):
        return False
    eu, au = ev[ei]/el[ei, None], av[ai]/al[ai, None]
    delta = actual[ai]-expected[ei, :1]
    perpendicular = np.abs(delta[..., 0]*eu[:, None, 1]-delta[..., 1]*eu[:, None, 0])
    p = np.sum(delta*eu[:, None, :], axis=2)
    lo, hi = np.maximum(0, p.min(axis=1)), np.minimum(el[ei], p.max(axis=1))
    keep = (perpendicular.max(axis=1) <= tolerance) & (hi-lo > tolerance/10)
    ai, ei, lo, hi = ai[keep], ei[keep], lo[keep], hi[keep]
    if not complete_intervals(ei, lo, hi, el, tolerance):
        return False
    reverse = np.sum((expected[ei]-actual[ai, :1])*au[keep, None, :], axis=2)
    return complete_intervals(ai, np.maximum(0, reverse.min(axis=1)),
                              np.minimum(al[ai], reverse.max(axis=1)), al, tolerance)


def check_contours(frame, claim, expected, directory):
    from affine import Affine
    field = claim.get("level_field")
    if frame.crs is None or field not in frame or frame[field].isna().any():
        raise Blocked("Contour artifact lacks its level field or CRS.")
    if claim.get("feature_count") != len(frame) or set(frame[field])-set(expected["levels"]):
        raise Blocked("Contour feature count or levels disagree with the frozen contract.")
    path = Path(directory) / expected["reference"]
    if sha(path) != expected["referenceSha256"]:
        raise Blocked("Independent contour reference changed after freeze.")
    projected = frame.to_crs(expected["sourceCrs"])
    inverse = ~Affine(*expected["transform"][:6])
    with np.load(path, allow_pickle=False) as reference:
        for index, level in enumerate(expected["levels"]):
            pieces = []
            for geometry in projected.loc[projected[field] == level].geometry:
                if geometry is None or geometry.is_empty or geometry.geom_type not in {"LineString", "MultiLineString"}:
                    raise Blocked("Contour output contains an invalid or non-line geometry.")
                for line in (geometry.geoms if geometry.geom_type == "MultiLineString" else [geometry]):
                    xy = np.array(line.coords)[:, :2]
                    cols, rows = inverse * (xy[:, 0], xy[:, 1])
                    coords = np.column_stack([cols, rows])
                    pieces.append(np.stack([coords[:-1], coords[1:]], axis=1))
            actual = np.concatenate(pieces) if pieces else np.empty((0, 2, 2))
            if not same_segments(actual, reference[f"level_{index}"], expected["tolerancePixels"]):
                raise Blocked("Contour geometry differs from the independent complete cell-segment calculation.")
    if claim["count"] != expected["count"] or claim["unknown_count"] != expected["unknownCount"]:
        raise Blocked("Final contour level or missing-pixel count is incorrect.")
