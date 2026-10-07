"""Observed flood-footprint questions, not inferred national hazard models."""

FLOOD_TASKS = {
    "480358": {"question": "Make contour lines of population density in flood-affected areas of Bangladesh.", "population": "bangladesh_density", "flood": "flood_bangladesh", "country": "Bangladesh", "bbox": [88, 20, 93, 27], "quantity": "density"},
    "381719": {
        "question": "Calculate the total population affected by floods in Peru during February 2018",
        "population": "peru_population",
        "flood": "flood_peru",
        "country": "Peru",
        "bbox": [-83, -19, -68, 1],
        "quantity": "count",
    },
    "536420": {
        "question": "Compare population density between flood-affected and non-flood-affected areas in Bangladesh during August 2018",
        "population": "bangladesh_density",
        "flood": "flood_bangladesh",
        "country": "Bangladesh",
        "bbox": [88, 20, 93, 27],
        "quantity": "density",
    },
}


def assets():
    return {
        key: {
            "file": filename,
            "kind": "raster",
            "title": title,
            "edition": "Original five-band GFD v1 benchmark snapshot, not a current flood map; benchmark-only use",
            "units": {
                "band1": "binary flooded flag",
                "band2": "days",
                "band3": "observations",
                "band4": "fraction",
                "band5": "binary permanent-water flag",
            },
        }
        for key, filename, title in [
            (
                "flood_peru",
                "DFO_4569_From_20180201_to_20180221.tif",
                "GFD observed flood 4569, 2018-02-01 to 2018-02-21",
            ),
            (
                "flood_bangladesh",
                "DFO_4665_From_20180802_to_20180810.tif",
                "GFD observed flood 4665, 2018-08-02 to 2018-08-10",
            ),
        ]
    }


def terms():
    return {
        key: {
            "status": "benchmark-only-user-directed",
            "license": "Original GFD/Cloud to Street notices retained; benchmark-only use directed by user",
            "attribution": "Global Flood Database v1 (Tellman et al., 2021), MODIS observations, Cloud to Street. Original GeoBenchX archive.",
            "evidence": ["Pinned Data.zip", "User benchmark-only direction 2026-10-06"],
            "sharingRestriction": "Internal benchmark only; no product reuse or external map publication.",
        }
        for key in assets()
    }


def protocols():
    result = {}
    for task, s in FLOOD_TASKS.items():
        result[task] = {
            "question": s["question"],
            "title": s["question"],
            "family": "observed-flood-population",
            "bbox": s["bbox"],
            "clarification": f"Use the frozen 2018 {s['country']} population raster and supplied event {s['flood']}. Population source values are "
            + ("people per original cell" if s["quantity"] == "count" else "people/km2")
            + ". Keep its entire original grid; no population resampling. Sample the original flood raster at each original population-cell centre by containing pixel (nearest alignment); no max/bilinear interpolation or inferred flooded fractions. GFD bands are 1 flooded (0/1), 2 duration in days, 3 clear-view count, 4 clear-view fraction, 5 permanent water (0/1). Observe a cell only if population is finite/unmasked, bands 1,3,5 are finite/unmasked, clear views >0, and permanent water=0. Observed band1=1 is flooded; observed band1=0 is non-flooded. Everything else is unknown/excluded, never non-flooded or zero population. Calculate original full geographic-cell WGS84 ellipsoidal meridian/parallel area in km2; density is counts/area and counts are density*area as appropriate. Sum original/derived population over flooded cells. For the density comparison use group population divided by group physical area, not an unweighted mean of densities. This explicitly defines affected as people in observed flooded cell centres, not proven personal impacts. The event covers only part of the country/month: report the observed-footprint result, never an exhaustive national total. The supplied Bangladesh event's footprint includes northern Bangladesh despite its Tibetan event label; inspect actual coverage. Permanent water, cloud gaps and unobserved regions do not establish absence of flooding. No current source substitutions. Internal benchmark only.",
            "outputContract": "Publish a full native-grid selected-population raster: people per cell for observed flooded cells, zero for observed non-flooded cells, NoData elsewhere. Also publish classification (1 flooded, 0 non-flooded, NoData unknown) on the same grid. End with fenced JSON {count:observed flooded cell count,unknown_count:all other unobserved/excluded population-grid cells,coverage_note:string,selection:{collectionId,itemId,assetKey},classification:{collectionId,itemId,assetKey},metrics:{selected_people:number,nonflood_people:number,selected_area_km2:number,nonflood_area_km2:number,selected_density:number,nonflood_density:number}}. Label classification unit as dimensionless and selected population as people per cell. Maps optional. Do not round machine-readable metrics to integers. Explicitly state incomplete country coverage and the 2018 source/event dates.",
        }
    return result


def arrays(population, flood, quantity):
    """Independent containing-pixel lookup; no production alignment or algebra."""
    import numpy as np

    from .common import Blocked
    from .population_oracles import quadrature_areas

    if population.crs != flood.crs or population.crs.to_epsg() != 4326:
        raise Blocked("Flood oracle requires original WGS84 grids")
    p = population.read(1, masked=True)
    values = p.data.astype(float) * population.scales[0] + population.offsets[0]
    valid = ~np.ma.getmaskarray(p) & np.isfinite(values)
    rows, cols = np.indices(p.shape)
    x, y = population.transform * (cols + 0.5, rows + 0.5)
    fc, fr = (~flood.transform) * (x, y)
    fr, fc = np.floor(fr).astype(int), np.floor(fc).astype(int)
    inside = (fr >= 0) & (fc >= 0) & (fr < flood.height) & (fc < flood.width)
    observed = valid & inside
    sampled = {}
    for band in [1, 3, 5]:
        raw = flood.read(band, masked=True)
        sample = np.full(p.shape, np.nan)
        sample[inside] = np.where(
            ~np.ma.getmaskarray(raw)[fr[inside], fc[inside]], raw.data[fr[inside], fc[inside]], np.nan
        )
        sample = sample * flood.scales[band - 1] + flood.offsets[band - 1]
        sampled[band] = sample
        observed &= np.isfinite(sample)
    observed &= (sampled[3] > 0) & (sampled[5] == 0) & np.isin(sampled[1], [0, 1])
    area = np.broadcast_to(
        quadrature_areas(population.transform, population.height, population.crs)[:, None], p.shape
    )
    counts = values if quantity == "count" else values * area
    if (valid & (counts < 0)).any():
        raise Blocked("Unexplained negative population values")
    flooded = observed & (sampled[1] == 1)
    dry = observed & (sampled[1] == 0)
    selected = np.where(observed, np.where(flooded, counts, 0), np.nan)
    classification = np.where(observed, sampled[1], np.nan)
    import math

    metrics = {
        "selected_people": math.fsum(counts[flooded]),
        "nonflood_people": math.fsum(counts[dry]),
        "selected_area_km2": math.fsum(area[flooded]),
        "nonflood_area_km2": math.fsum(area[dry]),
    }
    if not metrics["selected_area_km2"] or not metrics["nonflood_area_km2"]:
        raise Blocked("An observed comparison group is empty; no density ratio can be established")
    metrics.update(
        selected_density=metrics["selected_people"] / metrics["selected_area_km2"],
        nonflood_density=metrics["nonflood_people"] / metrics["nonflood_area_km2"],
    )
    return selected, classification, metrics


def oracle(directory, task, assets):
    from pathlib import Path

    import numpy as np
    import rasterio

    from .common import sha

    directory = Path(directory)
    s = FLOOD_TASKS[task]
    with (
        rasterio.open(directory / assets[s["population"]]["path"]) as p,
        rasterio.open(directory / assets[s["flood"]]["path"]) as f,
    ):
        selected, classification, metrics = arrays(p, f, s["quantity"])
        target = directory / f"flood-reference-{task}.npz"
        np.savez_compressed(target, selected=selected, classification=classification)
        return {
            "family": "observed-flood-population",
            "count": int((classification == 1).sum()),
            "unknownCount": int(np.isnan(classification).sum()),
            "metrics": metrics,
            "grid": {"crs": str(p.crs), "transform": list(p.transform)[:6], "shape": list(p.shape)},
            "reference": target.name,
            "referenceSha256": sha(target),
            "tolerance": {"absolute": 0.001, "relative": 2e-6},
            "rasterChecks": [
                ["selection", "selected", "people per cell"],
                ["classification", "classification", "dimensionless"],
            ],
        }
