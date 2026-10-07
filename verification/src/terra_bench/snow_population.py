"""Native-cell population/snow overlap, independently sampled and graded."""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from .common import Blocked, beneath, sha, timestamp

TASK = "321268"
BBOX = [-127.52624950980558, 18.432916768446546, -64.51791642850557, 57.64124994494655]


def protocol():
    return {
        TASK: {
            "question": "Find areas in the USA where population density exceeds 1000 people per square kilometer and snow accumulation was over 15 inches in 2023-2024",
            "title": "High-density population and 2023–24 snowfall",
            "family": "native-population-snow",
            "bbox": BBOX,
            "clarification": "Use frozen WorldPop USA 2020 counts and NOAA 2023-09-30 to 2024-09-30 snow in inches, original band 1. "
            "WorldPop is people PER CELL; derive people/km2 by dividing scaled counts by the full original WGS84 ellipsoidal meridian/parallel cell area. "
            f"To limit memory, a lossless population crop uses these EXACT native-grid edges around the whole snow footprint: {BBOX}, width 7561 height 4705. "
            "Retain that original population grid: do not resample or interpolate population. Sample original snow at each population cell centre by containing pixel (nearest on aligned pixel centres), no bilinear averages. "
            "A cell qualifies only if density STRICTLY >1000 people/km2 AND sampled snow STRICTLY >15 inches. Both must be observed. "
            "Source masks/nonfinite values or outside the snow grid are unknown, not a failed threshold. Unobserved USA outside the supplied snow footprint is also unknown, not proof of no qualifying areas. "
            "Valid nonqualifying cells are zero; qualifying are one; missing either input is NoData. This native-cell allocation is a spatial screening convention, not within-cell uniformity or simultaneous observation in 2020 and 2023–24.",
            "outputContract": "Publish the full cropped 0/1/NoData result raster and add it to the map, showing selected cells and unknown coverage distinctly. "
            "End with fenced JSON {count:qualifying cells,unknown_count:missing-either-input cells within the specified crop,coverage_note:string,selection:{collectionId,itemId,assetKey},map_layer_id:string}. "
            "Explain 2020 population, 2023–24 snow, strict thresholds, and incomplete geographic coverage.",
        }
    }


def reference_blocks(pop, snow, bounds=BBOX):
    from .population_oracles import quadrature_areas

    if pop.crs != snow.crs or str(pop.crs) != "EPSG:4326":
        raise Blocked("Reference expects verified longitude/latitude fixture grids.")
    w = rasterio.windows.from_bounds(*bounds, pop.transform)
    raw = [w.col_off, w.row_off, w.width, w.height]
    rounded = np.round(raw)
    if not np.allclose(raw, rounded, atol=1e-5, rtol=0):
        raise Blocked("Snow/population crop is not native-grid aligned.")
    window = Window(*map(int, rounded))
    transform = pop.window_transform(window)
    if snow.transform.b or snow.transform.d or snow.transform.a <= 0 or snow.transform.e >= 0:
        raise Blocked("Snow sampling grid is unsupported.")
    snow_values = snow.read(1, masked=True)
    area = quadrature_areas(transform, int(window.height), pop.crs)
    for r in range(0, int(window.height), 256):
        for c in range(0, int(window.width), 256):
            h = min(256, int(window.height) - r)
            width = min(256, int(window.width) - c)
            raw = pop.read(
                1,
                window=Window(window.col_off + c, window.row_off + r, width, h),
                masked=True,
                boundless=True,
            )
            values = raw.data.astype("float64") * pop.scales[0] + pop.offsets[0]
            rr, cc = np.indices(raw.shape)
            x, y = transform * (c + cc + 0.5, r + rr + 0.5)
            sr = np.floor((y - snow.transform.f) / snow.transform.e).astype(int)
            sc = np.floor((x - snow.transform.c) / snow.transform.a).astype(int)
            inside = (sr >= 0) & (sr < snow.height) & (sc >= 0) & (sc < snow.width)
            sampled = np.full(raw.shape, np.nan)
            ix, iy = sr[inside], sc[inside]
            present = ~np.ma.getmaskarray(snow_values)[ix, iy]
            scaled = snow_values.data[ix, iy].astype("float64") * snow.scales[0] + snow.offsets[0]
            sampled[inside] = np.where(present, scaled, np.nan)
            valid = ~np.ma.getmaskarray(raw) & np.isfinite(values) & np.isfinite(sampled)
            if (values[valid] < 0).any():
                raise Blocked("Negative population is not valid missing-data handling.")
            mask = np.full(raw.shape, 255, dtype="uint8")
            mask[valid] = ((values / area[r : r + h, None] > 1000) & (sampled > 15))[valid]
            yield mask, Window(c, r, width, h), transform, int(window.width), int(window.height)


def oracle(directory, assets):
    directory = Path(directory)
    target = directory / "snow-population-reference.tif"
    out = None
    count = unknown = 0
    try:
        with (
            rasterio.open(directory / assets["us_population"]["path"]) as pop,
            rasterio.open(directory / assets["snow_previous"]["path"]) as snow,
        ):
            for mask, w, t, width, height in reference_blocks(pop, snow):
                if out is None:
                    out = rasterio.open(
                        target,
                        "w",
                        driver="GTiff",
                        height=height,
                        width=width,
                        transform=t,
                        crs=pop.crs,
                        count=1,
                        dtype="uint8",
                        nodata=255,
                        tiled=True,
                        blockxsize=256,
                        blockysize=256,
                        compress="deflate",
                    )
                out.write(mask, 1, window=w)
                count += int((mask == 1).sum())
                unknown += int((mask == 255).sum())
    finally:
        if out:
            out.close()
    return {
        "family": "native-population-snow",
        "count": count,
        "unknownCount": unknown,
        "reference": target.name,
        "referenceSha256": sha(target),
        "mapRequired": True,
        "answerConcepts": [["2020"], ["2023"], ["unknown", "unobserved", "incomplete", "outside"]],
    }


def grade(task, claim, expected, snapshot, frozen, scope, folder, deadline):
    from .map_bindings import verify_map_binding
    from .policy import identity, trusted_reuse

    a = next(
        (a for a in snapshot.get("artifacts", []) if identity(a) == identity(claim.get("selection", {}))),
        None,
    )
    if (
        not a
        or not a.get("finishedAt")
        or timestamp(a["finishedAt"]) > deadline
        or identity(a)
        not in {identity(v) for v in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True)}
    ):
        raise Blocked("Snow/population result lacks verified pre-deadline fixture provenance.")
    actual_path = beneath(folder, a["path"])
    ref = Path(frozen["fixtureDirectory"]) / expected["reference"]
    if sha(actual_path) != a["sha256"] or sha(ref) != expected["referenceSha256"]:
        raise Blocked("Snow/population evidence changed.")
    with rasterio.open(actual_path) as actual, rasterio.open(ref) as reference:
        if (
            actual.crs != reference.crs
            or actual.shape != reference.shape
            or not actual.transform.almost_equals(reference.transform, precision=1e-10)
            or actual.count != 1
        ):
            raise Blocked("Snow/population output changed the native grid.")
        for _, w in reference.block_windows(1):
            labels = reference.read(1, window=w)
            aout = actual.read(1, window=w, masked=True)
            valid = labels != 255
            if not np.array_equal(
                valid, ~np.ma.getmaskarray(aout) & np.isfinite(aout.data)
            ) or not np.array_equal(aout.data[valid], labels[valid]):
                raise Blocked("Snow/population selected cells or unknown coverage differ.")
    verify_map_binding(snapshot, a, claim.get("map_layer_id"))
    if claim["count"] != expected["count"] or claim["unknown_count"] != expected["unknownCount"]:
        raise Blocked("Final snow/population count differs.")
