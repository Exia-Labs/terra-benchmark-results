"""Independent multi-year calculations and original-feature spatial selection."""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.prepared import prep

from .change_tasks import CHANGE_TASKS
from .common import Blocked
from .fixtures import ROW_ID


def change_answer(task, points, countries, tables):
    spec = CHANGE_TASKS[task]
    africa = (
        countries[countries[spec["regionField"]].isin(spec["regionMembers"])].copy()
        if spec.get("regionField")
        else countries[countries.CONTINENT == "Africa"].copy()
    )

    def values(key, year):
        table = tables[key]
        if table["Country Code"].duplicated().any():
            raise Blocked("Change oracle has duplicate country keys.")
        return africa.ISO_A3.map(pd.to_numeric(table.set_index("Country Code")[year], errors="raise"))

    if task == "932053":
        earlier, later = values("forest_area", "1990"), values("forest_area", "2021")
        measure = later / earlier.where(earlier > 0)
        cutoff = 0.79
    elif task == "104119":
        earlier, later = values("population", "2013"), values("population", "2023")
        measure = later / earlier.where(earlier > 0)
        cutoff = 1.1
    else:
        r0, r1, p0, p1 = (
            values("rural", "2013"),
            values("rural", "2023"),
            values("population", "2013"),
            values("population", "2023"),
        )
        measure = r1 / p1.where(p1 > 0) - r0 / p0.where(p0 > 0)
        cutoff = -0.03
    measure = measure.where(np.isfinite(measure))
    qualified, unknown = (
        africa.loc[measure > cutoff if spec.get("operator") == "gt" else measure < cutoff],
        africa.loc[measure.isna()],
    )
    valid = points.geometry.notna() & ~points.geometry.is_empty & points.geometry.is_valid
    unlocated = points.loc[~valid, ROW_ID].tolist()
    located = points.loc[valid].to_crs(countries.crs)

    def members(polygons):
        prepared = [prep(p) for p in polygons.geometry]
        ids = set(located.loc[located.geometry.map(lambda p: any(g.contains(p) for g in prepared)), ROW_ID])
        cross = set(
            gpd.sjoin(located[[ROW_ID, "geometry"]], polygons[["geometry"]], predicate="within")[ROW_ID]
        )
        if ids != cross:
            raise Blocked("Change selection oracle spatial cross-check failed.")
        return ids

    selected = members(qualified)
    # In an overlap, positive evidence wins; no point is both selected and unknown.
    missing = (members(unknown) | set(unlocated)) - selected
    return {
        "ids": sorted(selected),
        "count": len(selected),
        "unknownIds": sorted(missing),
        "unlocatedPointIds": sorted(unlocated),
        "identityField": ROW_ID,
        "outsideGeometryIds": sorted(set(located[ROW_ID]) - members(africa)),
        "countryValues": {
            str(key): None if pd.isna(value) else float(value)
            for key, value in zip(africa[ROW_ID], measure, strict=True)
        },
        "semantics": {
            "predicate": "within",
            "threshold": cutoff,
            "strict": True,
            "unknown": "missing measurement or invalid point location",
        },
    }
