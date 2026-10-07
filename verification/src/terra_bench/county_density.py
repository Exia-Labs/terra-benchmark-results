"""Independent population-density coverage for the available county TB tables."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.windows import Window

from .common import Blocked, beneath, read, sha, timestamp

TASK = "419069"
# A lossless native-grid crop surrounding the complete NY/MA county coverage.
# These are grid edges, not selected analytical features or an answer.
BBOX = [-80.00124969990557, 39.99958334884655, -68.99291641060557, 46.00791665814655]
STATES = {"25": ("tb_ma", "Number of Cases"), "36": ("tb_ny", "2023 cases")}


def protocol():
    return {
        TASK: {
            "question": "Generate a heatmap of USA population density in counties with reported tuberculosis cases. ",
            "title": "Population density in counties with reported TB",
            "family": "county-population-density",
            "bbox": BBOX,
            "clarification": "The supplied county TB observations cover Massachusetts and New York in 2023 only. Other US states are UNKNOWN, not zero-case counties. "
            "Select original Census counties by STATEFP 25 or 36 as strings, then join NAME to the corresponding table County: MA Number of Cases, NY 2023 cases. "
            "Ignore state/city aggregate rows and footnotes; repeated names across states must not mix. Select strictly positive reported county case counts; preserve missing as unknown and exclude genuine zero cases. "
            "Heatmap means the native WorldPop USA 2020 population-density surface in those counties, not smoothed TB patients or a health-risk model. "
            "WorldPop stores people PER CELL. Divide each scaled count by its full original WGS84 meridian/parallel cell area in km2. No resampling, nominal one-km2 divisor, or smoothing. "
            f"A lossless native-grid rectangular crop may use EXACT bounds {BBOX}; these encompass the full observed states. Retain all original cells on that 1321x721 crop. "
            "Keep a cell only when its centre is inside a selected original county and its population is valid. Outside selected counties and source NoData are NoData, not zero density. "
            "Zero population inside selected counties stays valid. The historical years differ; this is population context, not inferred patient positions or a causal association.",
            "outputContract": "Publish and map the masked density raster in people/km2, plus an inspectable original-county polygon selection retaining benchmark_row_id and a numeric case_count. "
            "End with fenced JSON {count:number of selected positive-case counties,unknown_count:NY/MA counties with unknown case counts,coverage_note:string, "
            'selection:{collectionId,itemId,assetKey} for the density raster,map_layer_id:string,county_selection:{collectionId,itemId,assetKey},value_field:"case_count"}. '
            "Explain that the rest of the USA is unobserved and that 2020 population and 2023 reported cases are different measurements.",
        }
    }


def counties_with_cases(counties, tables):
    selected = counties.loc[counties.STATEFP.isin(STATES)].copy()
    values = pd.Series(np.nan, index=selected.index)
    for state, (key, field) in STATES.items():
        table = tables[key].loc[tables[key].County.notna()]
        if table.County.duplicated().any():
            raise Blocked("Ambiguous county table names; state-qualified joins are required.")
        names = table.set_index("County")[field]
        nums = pd.to_numeric(names, errors="raise")
        subset = selected.STATEFP == state
        values.loc[subset] = selected.loc[subset, "NAME"].map(nums)
    if (values.dropna() < 0).any() or np.isinf(values.dropna()).any():
        raise Blocked("Invalid reported county case count.")
    unknown = selected.loc[values.isna(), "benchmark_row_id"].tolist()
    selected["case_count"] = values
    return selected.loc[values > 0].copy(), unknown


def reference_grid(source, selected, bounds=BBOX):
    from .population_oracles import quadrature_areas

    raw_window = rasterio.windows.from_bounds(*bounds, source.transform)
    rounded = np.round([raw_window.col_off, raw_window.row_off, raw_window.width, raw_window.height])
    if not np.allclose(
        rounded,
        [raw_window.col_off, raw_window.row_off, raw_window.width, raw_window.height],
        atol=1e-5,
        rtol=0,
    ):
        raise Blocked("County density crop is not exactly aligned to the native grid.")
    window = Window(*map(int, rounded))
    transform = source.window_transform(window)
    raw = source.read(1, window=window, masked=True)
    rr, cc = np.indices(raw.shape)
    xs, ys = transform * (cc + 0.5, rr + 0.5)
    polygons = selected.to_crs(source.crs)
    if polygons.geometry.isna().any() or not polygons.geometry.is_valid.all():
        raise Blocked("County geometry is not valid.")
    union = shapely.union_all(polygons.geometry)
    inside = shapely.contains_xy(union, xs, ys)
    # Freeze no ambiguous centre-on-border choices rather than silently choosing
    # a different rasterizer edge convention from the independent point oracle.
    if np.any(shapely.intersects_xy(union.boundary, xs, ys)):
        raise Blocked(
            "A native cell centre lies exactly on a county boundary; resolve edge semantics before running."
        )
    counts = raw.data.astype("float64") * source.scales[0] + source.offsets[0]
    valid = inside & ~np.ma.getmaskarray(raw) & np.isfinite(counts)
    areas = quadrature_areas(transform, raw.shape[0], source.crs)
    result = counts / areas[:, None]
    result[~valid] = np.nan
    return result, transform


def oracle(directory, assets):
    directory = Path(directory)
    counties = gpd.read_parquet(directory / assets["counties"]["path"])
    selected, unknown = counties_with_cases(
        counties, {key: pd.read_parquet(directory / assets[key]["path"]) for key, _ in STATES.values()}
    )
    with rasterio.open(directory / assets["us_population"]["path"]) as src:
        values, transform = reference_grid(src, selected)
        target = directory / "county-density-reference.tif"
        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            width=values.shape[1],
            height=values.shape[0],
            transform=transform,
            count=1,
            dtype="float64",
            nodata=np.nan,
            compress="deflate",
        )
        with rasterio.open(target, "w", **profile) as out:
            out.write(values, 1)
    return {
        "family": "county-population-density",
        "count": len(selected),
        "unknownCount": len(unknown),
        "ids": sorted(selected.benchmark_row_id),
        "unknownIds": sorted(unknown),
        "values": dict(zip(selected.benchmark_row_id, selected.case_count, strict=True)),
        "reference": target.name,
        "referenceSha256": sha(target),
        "mapRequired": True,
        "answerConcepts": [
            ["2020"],
            ["2023"],
            ["unknown", "unobserved", "not covered", "unavailable"],
            ["Massachusetts"],
            ["New York"],
        ],
    }


def grade(task, claim, expected, snapshot, frozen, scope, folder, deadline):
    from .lineage import record_identity_field
    from .map_bindings import verify_map_binding
    from .policy import identity, trusted_reuse
    from .units import same_unit

    directory = Path(frozen["fixtureDirectory"])
    fixtures = read(directory / "fixtures.json")
    trusted = {identity(a) for a in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True)}

    def artifact(selection):
        a = next((a for a in snapshot.get("artifacts", []) if identity(a) == identity(selection)), None)
        if (
            not a
            or identity(a) not in trusted
            or not a.get("finishedAt")
            or timestamp(a["finishedAt"]) > deadline
        ):
            raise Blocked("County density requires an authorized pre-deadline output.")
        path = beneath(folder, a["path"])
        if sha(path) != a["sha256"]:
            raise Blocked("County output checksum changed.")
        return a, path

    a, path = artifact(claim.get("selection", {}))
    reference = directory / expected["reference"]
    if sha(reference) != expected["referenceSha256"]:
        raise Blocked("County density oracle changed.")
    with rasterio.open(path) as actual, rasterio.open(reference) as ref:
        if (
            actual.crs != ref.crs
            or actual.shape != ref.shape
            or not actual.transform.almost_equals(ref.transform, precision=1e-10)
            or actual.count != 1
        ):
            raise Blocked("County density changed the original cropped grid.")
        out = actual.read(1, masked=True)
        wanted = ref.read(1, masked=True)
        valid = ~np.ma.getmaskarray(wanted) & np.isfinite(wanted.data)
        if not np.array_equal(~np.ma.getmaskarray(out) & np.isfinite(out.data), valid) or not np.allclose(
            out.data[valid], wanted.data[valid], rtol=3e-6, atol=1e-7
        ):
            raise Blocked("County population density or missing-data coverage is incorrect.")
        if not same_unit(actual.units[0], "people/km2"):
            raise Blocked("County density unit is incorrect.")
    verify_map_binding(snapshot, a, claim.get("map_layer_id"))
    _, path = artifact(claim.get("county_selection", {}))
    frame = gpd.read_parquet(path)
    fid = record_identity_field(snapshot, claim["county_selection"], scope["inputs"], fixtures, "counties")
    if fid not in frame or frame[fid].duplicated().any() or set(frame[fid]) != set(expected["ids"]):
        raise Blocked("Positive-case county membership is incorrect.")
    frame = frame.set_index(fid)
    base = gpd.read_parquet(directory / fixtures["assets"]["counties"]["path"]).set_index("benchmark_row_id")
    frame = frame.to_crs(base.crs)
    field = claim.get("value_field")
    if field not in frame:
        raise Blocked("County case-count field is missing.")
    for key, value in expected["values"].items():
        if frame.loc[key, field] != value or not frame.loc[key].geometry.equals_exact(
            base.loc[key].geometry, 1e-8, normalize=True
        ):
            raise Blocked("Original county geometry or reported case counts changed.")
    if claim["count"] != expected["count"] or claim["unknown_count"] != expected["unknownCount"]:
        raise Blocked("Final county counts disagree with the produced data.")
