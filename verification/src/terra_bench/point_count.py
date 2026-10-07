"""Independent original-grid exposure oracle; never executed for the agent."""

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Geod, Transformer
from rasterio.windows import Window

from .common import Blocked, beneath, read, sha, timestamp

TASK = "586288"


def protocol():
    return {
        TASK: {
            "question": "Calculate the total population living within 50km of active wildfire incidents larger than 1000 acres in the USA",
            "title": "Historical population near large wildfire incident locations",
            "family": "raster-proximity-count",
            "bbox": [-180, 18, 180, 72],
            "clarification": "Use original WorldPop USA 2020 UN-adjusted people-per-cell counts on its native grid, band 1, with source scale/offset and mask. The NIFC archive is historical (latest record modification 2024-02-27), not current activity. Select ALL IncidentTy='WF' records with IncidentSi strictly >1000 acres; RX burns are excluded. Latest modification describes the archive date, not an additional record filter. IncidentSi is recorded incident size, not final burned acreage (FinalAcres is missing). A valid population cell qualifies if its centre is <=50000 metres from ANY selected original fire Point by shortest WGS84 ellipsoidal distance. Count a cell once even with overlapping radii. Preserve original grid and counts, do not approximate density as population or resample. This centre-allocation approximation identifies people near supplied incident locations, not people burned/evacuated or observed during the same year. Outside and masked cells are unknown, never invented zero population.",
            "outputContract": "Publish an inspectable full-grid selected-population raster: original scaled counts in qualifying cells, zero in other valid cells, original missing/nonfinite mask. Map optional. Give the total people, source years and proximity limitation. End with a fenced JSON {count:qualifying valid cell count,unknown_count:original missing/nonfinite cell count,coverage_note:string,selection:{collectionId,itemId,assetKey},metrics:{selected_people:number,total_people:number}}. Keep unrounded machine-readable sums. total_people is sum over the full original valid raster, not an external Census total.",
        }
    }


def oracle(directory, assets):
    directory = Path(directory)
    fires = gpd.read_parquet(directory / assets["fires"]["path"])
    selected = fires.loc[(fires.IncidentTy == "WF") & (fires.IncidentSi > 1000)].to_crs(4326)
    if selected.empty or selected.geometry.isna().any() or not selected.geom_type.eq("Point").all():
        raise Blocked("Selected historical fire geometry is missing or incompatible.")
    points = np.array([(p.x, p.y) for p in selected.geometry])
    target = directory / "oracle-fire-proximity.tif"
    count = missing = 0
    parts = []
    totals = []
    geod = Geod(ellps="WGS84")
    from geographiclib.geodesic import Geodesic

    crosschecked = False
    with (
        rasterio.Env(GDAL_CACHEMAX=64 * 1024**2),
        rasterio.open(directory / assets["us_population"]["path"]) as src,
    ):
        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            count=1,
            dtype="uint8",
            nodata=255,
            compress="deflate",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        convert = Transformer.from_crs(src.crs, 4326, always_xy=True)
        with rasterio.open(target, "w", **profile) as out:
            for r in range(0, src.height, 256):
                for c in range(0, src.width, 256):
                    win = Window(c, r, min(256, src.width - c), min(256, src.height - r))
                    raw = src.read(1, window=win, masked=True)
                    values = raw.data.astype("float64") * src.scales[0] + src.offsets[0]
                    valid = ~np.ma.getmaskarray(raw) & np.isfinite(values)
                    if (values[valid] < 0).any():
                        raise Blocked("Negative original population is not silently discarded.")
                    rr, cc = np.nonzero(valid)
                    chosen = np.zeros(len(rr), dtype=bool)
                    if len(rr):
                        x, y = src.transform * (c + cc + 0.5, r + rr + 0.5)
                        lon, lat = convert.transform(x, y)
                        # Independent exhaustive pair calculation: no production
                        # spherical pruning, no production module import.
                        for px, py in points:
                            _, _, distance = geod.inv(lon, lat, np.full(len(rr), px), np.full(len(rr), py))
                            chosen |= distance <= 50000
                            if not crosschecked:
                                for i in range(min(3, len(rr))):
                                    reference = Geodesic.WGS84.Inverse(float(lat[i]), float(lon[i]), py, px)[
                                        "s12"
                                    ]
                                    if not math.isclose(distance[i], reference, rel_tol=1e-12, abs_tol=1e-5):
                                        raise Blocked("Independent distance libraries disagree.")
                        crosschecked = True
                        parts.append(math.fsum(values[rr[chosen], cc[chosen]]))
                        totals.append(math.fsum(values[valid]))
                    result = np.full(raw.shape, 255, dtype="uint8")
                    result[rr, cc] = chosen.astype("uint8")
                    out.write(result, 1, window=win)
                    count += int(chosen.sum())
                    missing += int((~valid).sum())
    return {
        "family": "raster-proximity-count",
        "count": count,
        "unknownCount": missing,
        "metrics": {"selected_people": math.fsum(parts), "total_people": math.fsum(totals)},
        "reference": target.name,
        "referenceSha256": sha(target),
        "sourceFireIds": selected.benchmark_row_id.tolist(),
    }


def grade(task, claim, expected, snapshot, frozen, scope, folder, deadline):
    from .policy import identity, trusted_reuse

    directory = Path(frozen["fixtureDirectory"])
    fixtures = read(directory / "fixtures.json")
    match = next(
        (a for a in snapshot.get("artifacts", []) if identity(a) == identity(claim.get("selection", {}))),
        None,
    )
    if not match or not match.get("finishedAt") or timestamp(match["finishedAt"]) > deadline:
        raise Blocked("No selected-population raster completed before deadline.")
    if identity(match) not in {
        identity(a) for a in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True)
    }:
        raise Blocked("Selected-population raster lacks frozen fixture lineage.")
    path = beneath(folder, match["path"])
    ref = directory / expected["reference"]
    source = directory / fixtures["assets"]["us_population"]["path"]
    if (
        sha(path) != match["sha256"]
        or sha(ref) != expected["referenceSha256"]
        or sha(source) != fixtures["assets"]["us_population"]["sha256"]
    ):
        raise Blocked("A source, result or reference changed after freeze.")
    with rasterio.open(path) as actual, rasterio.open(ref) as membership, rasterio.open(source) as src:
        if (
            actual.crs != src.crs
            or actual.transform != src.transform
            or actual.shape != src.shape
            or actual.count != 1
        ):
            raise Blocked("Selected-population raster changed the original grid.")
        for _, win in membership.block_windows(1):
            labels = membership.read(1, window=win)
            out = actual.read(1, window=win, masked=True)
            valid = labels != 255
            if not np.array_equal(~np.ma.getmaskarray(out) & np.isfinite(out.data), valid):
                raise Blocked("Population missing-data coverage changed.")
            values = src.read(1, window=win).astype("float64") * src.scales[0] + src.offsets[0]
            wanted = np.where(labels == 1, values, 0)
            if not np.allclose(out.data[valid], wanted[valid], rtol=1e-9, atol=1e-8):
                raise Blocked("Selected population differs from exhaustive exact-distance oracle.")
    metrics = claim.get("metrics", {})
    if (
        claim["count"] != expected["count"]
        or claim["unknown_count"] != expected["unknownCount"]
        or any(
            not math.isclose(metrics.get(k, float("nan")), v, rel_tol=1e-8, abs_tol=1e-5)
            for k, v in expected["metrics"].items()
        )
    ):
        raise Blocked("Final cell counts or population sums disagree with actual selected coverage.")
