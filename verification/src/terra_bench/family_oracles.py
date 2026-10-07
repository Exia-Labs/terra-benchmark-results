"""Independent station-group and country-statistic reference calculations."""
from __future__ import annotations

from collections import Counter

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from shapely import STRtree

from .common import Blocked
from .fixtures import ROW_ID

US_STATES = frozenset("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
HIGH_INCOME = ("1. High income: OECD", "2. High income: nonOECD")
LOW_INCOME = "5. Low income"


def snow_stations(stations, raster_path):
    eligible = stations[stations.State.isin(US_STATES)].copy()
    ids, unknown, groups, values = [], [], Counter(), {}
    with rasterio.open(raster_path) as raster:
        points = eligible.to_crs(raster.crs)
        sampled = raster.sample([(p.x, p.y) for p in points.geometry], masked=True)
        for (_, row), sample in zip(points.iterrows(), sampled, strict=True):
            r, c = raster.index(row.geometry.x, row.geometry.y)
            if not (0 <= r < raster.height and 0 <= c < raster.width) or np.ma.is_masked(sample[0]):
                unknown.append(row[ROW_ID])
                continue
            cell = raster.read(1, window=Window(c, r, 1, 1), masked=True)[0, 0]
            if np.ma.is_masked(cell) or not np.isfinite(cell):
                unknown.append(row[ROW_ID])
                continue
            if float(cell) != float(sample[0]):
                raise Blocked("Station-snow oracle sample/window disagreement.")
            if cell > 12:
                ids.append(row[ROW_ID])
                values[row[ROW_ID]] = float(cell)
                groups[str(row.State)] += 1
    return {"ids": sorted(ids), "count": len(ids), "unknownIds": sorted(unknown),
            "identityField": ROW_ID, "groups": dict(sorted(groups.items())),
            "values": values, "semantics": {"threshold": ">12 inches", "states": sorted(US_STATES),
                                             "sampling": "containing pixel"}}


def contained_counts(countries, points):
    """Original per-country predicates cross-checked against GeoPandas indexed joins."""
    points = points.to_crs(countries.crs)
    valid = points[points.geometry.notna() & ~points.geometry.is_empty & points.geometry.is_valid]
    tree = STRtree(valid.geometry.values)
    counts = {str(row[ROW_ID]): len(tree.query(row.geometry, predicate="contains"))
              for _, row in countries.iterrows()}
    joined = gpd.sjoin(countries[[ROW_ID, "geometry"]], valid[["geometry"]], predicate="contains")
    check = joined.groupby(ROW_ID).size().to_dict()
    if any(count != check.get(key, 0) for key, count in counts.items()):
        raise Blocked("Country containment oracle cross-check failed.")
    return pd.Series(counts, dtype="int64")


def country_stat(countries, table, year, *, points=None, minimum=1, africa=False, income=False):
    if table["Country Code"].duplicated().any() or year not in table:
        raise Blocked("Country-statistic source has ambiguous identity or missing year.")
    eligible = countries[countries.CONTINENT == "Africa"].copy() if africa else countries.copy()
    counts = None
    if points is not None:
        counts = contained_counts(eligible, points)
        eligible = eligible[eligible[ROW_ID].map(counts) >= minimum]
    if income:
        eligible = eligible[eligible.INCOME_GRP.isin([*HIGH_INCOME, LOW_INCOME])].copy()
    mapping = pd.to_numeric(table.set_index("Country Code")[year], errors="raise")
    values = eligible.ISO_A3.map(mapping)
    # NoData is not zero; infinities would be invalid evidence, not a valid mean.
    if np.isinf(values.dropna()).any():
        raise Blocked("Country statistic contains nonfinite nonmissing values.")
    selected = eligible.loc[values.notna()].copy()
    selected["_oracle_value"] = values.loc[values.notna()]
    if selected.empty:
        raise Blocked("Country-statistic reference has no known contributors.")
    if income:
        groups = {"high_income": selected.INCOME_GRP.isin(HIGH_INCOME),
                  "low_income": selected.INCOME_GRP.eq(LOW_INCOME)}
        metrics = {key: float(selected.loc[mask, "_oracle_value"].mean()) for key, mask in groups.items()}
        if any(not np.isfinite(value) for value in metrics.values()):
            raise Blocked("Income comparison has an empty group.")
    else:
        metrics = {"mean": float(selected._oracle_value.mean())}
    # Cross-check with an explicit merge and Python summation, not the same reduction.
    merged = eligible.merge(table[["Country Code", year]], left_on="ISO_A3", right_on="Country Code", how="left", validate="many_to_one")
    subsets = {"high_income": merged[merged.INCOME_GRP.isin(HIGH_INCOME)],
               "low_income": merged[merged.INCOME_GRP.eq(LOW_INCOME)]} if income else {"mean": merged}
    for key, subset in subsets.items():
        known = [float(v) for v in subset[year].dropna()]
        if not known or not np.isclose(sum(known) / len(known), metrics[key], rtol=1e-12):
            raise Blocked("Country-statistic mean cross-check failed.")
    return {"ids": sorted(selected[ROW_ID]), "count": len(selected), "identityField": ROW_ID,
            "unknownIds": sorted(eligible.loc[values.isna(), ROW_ID]),
            "unmatchedCountries": sorted(eligible.loc[values.isna(), "NAME_EN"]),
            "values": dict(zip(selected[ROW_ID], selected._oracle_value, strict=True)),
            "metrics": metrics, "tolerance": {"absolute": 1e-6, "relative": 1e-6},
            "stationCounts": counts.to_dict() if counts is not None else {},
            "unlocatedPointIds": sorted(points.loc[points.geometry.isna() | points.geometry.is_empty, ROW_ID]) if points is not None and ROW_ID in points else [],
            "semantics": {"year": year, "join": "ISO_A3/Country Code", "weighting": "one original country feature",
                          "predicate": "contains", "minimumPointCount": minimum if points is not None else None}}
