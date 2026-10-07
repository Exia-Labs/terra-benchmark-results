import bisect
import math

import pandas as pd

from .common import Blocked
from .fixtures import ROW_ID
from .map_oracles import reference_quantiles
from .series_tasks import SERIES_TASKS


def series_answer(task, countries, tables):
    s = SERIES_TASKS[task]
    if s.get("bivariate"):
        return bivariate_series_answer(s, countries, tables)
    table = tables[s["indicator"]] if isinstance(tables, dict) else tables
    region = countries.loc[countries[s["regionField"]].isin(s["regionMembers"])]
    if region.empty or table["Country Code"].duplicated().any():
        raise Blocked("Map series geography is empty or join keys are ambiguous.")
    panels = {}
    for year in s["years"]:
        values = region.ISO_A3.map(pd.to_numeric(table.set_index("Country Code")[year], errors="raise"))
        by_id = {
            fid: float(v) if pd.notna(v) and math.isfinite(v) else None
            for fid, v in zip(region[ROW_ID], values, strict=True)
        }
        breaks = reference_quantiles(by_id.values())
        panels[year] = {
            "ids": sorted(by_id),
            "count": sum(v is not None for v in by_id.values()),
            "unknownIds": [k for k, v in by_id.items() if v is None],
            "values": by_id,
            "classes": {
                k: bisect.bisect_right(breaks, v) + 1 if v is not None else 0 for k, v in by_id.items()
            },
            "breaks": breaks,
            "unit": s["unit"],
            "mapRequired": True,
        }
    return {
        "family": "map-series",
        "count": len(panels),
        "panels": panels,
        "unknownIds": [f"{year}:{fid}" for year, p in panels.items() for fid in p["unknownIds"]],
        "resultUnit": "year maps",
    }


def bivariate_series_answer(s, countries, tables):
    panels = {}
    for year in s["years"]:
        def mapped(axis):
            table = tables[s[axis]]
            key = s[axis+"Key"]
            if table[key].duplicated().any():
                raise Blocked("Emissions table names are ambiguous.")
            lookup = pd.to_numeric(table.set_index(key)[year], errors="raise")
            values = countries[s["geographyKey"]].map(lookup)
            return {fid: float(v) if pd.notna(v) and math.isfinite(v) else None
                    for fid,v in zip(countries[ROW_ID],values,strict=True)}
        xv, yv = mapped("x"), mapped("y")
        paired = [f for f in xv if xv[f] is not None and yv[f] is not None]
        xb, yb = reference_quantiles([xv[f] for f in paired],3), reference_quantiles([yv[f] for f in paired],3)
        panels[year] = {"ids":sorted(xv),"count":len(paired),"unknownIds":sorted(set(xv)-set(paired)),
            "values":xv,"valuesY":yv,"xBreaks":xb,"yBreaks":yb,"xUnit":s["xUnit"],"yUnit":s["yUnit"],
            "classes":{f:bisect.bisect_right(yb,yv[f])*(len(xb)+1)+bisect.bisect_right(xb,xv[f])+1 if f in paired else 0 for f in xv},
            "bivariate":True,"mapRequired":True}
    return {"family":"map-series","count":len(panels),"panels":panels,
            "unknownIds":[f"{year}:{fid}" for year,p in panels.items() for fid in p["unknownIds"]],"resultUnit":"year maps"}
