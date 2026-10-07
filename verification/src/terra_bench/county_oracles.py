import bisect
import math

import pandas as pd

from .common import Blocked
from .county_tasks import COUNTY_TASKS
from .fixtures import ROW_ID
from .map_oracles import reference_quantiles


def county_answer(task, counties, table):
    s = COUNTY_TASKS[task]
    selected = counties.loc[counties.STATEFP == s["state"]]
    if selected.empty or table.County.dropna().duplicated().any():
        raise Blocked("County map has empty geography or ambiguous table keys.")
    values = selected.NAME.map(pd.to_numeric(table.set_index("County")[s["field"]], errors="raise"))
    by_id = {
        fid: float(v) if pd.notna(v) and math.isfinite(v) else None
        for fid, v in zip(selected[ROW_ID], values, strict=True)
    }
    # Cross-check direct key lookup against a validated left merge, preserving all counties.
    merged = selected[[ROW_ID, "NAME"]].merge(
        table[["County", s["field"]]], left_on="NAME", right_on="County", how="left", validate="many_to_one"
    )
    for _, r in merged.iterrows():
        expected = by_id[r[ROW_ID]]
        if (pd.isna(r[s["field"]]) and expected is not None) or (
            pd.notna(r[s["field"]]) and r[s["field"]] != expected
        ):
            raise Blocked("County lookup/merge oracle disagreement.")
    breaks = reference_quantiles(by_id.values())
    return {
        "family": "county-choropleth",
        "ids": sorted(by_id),
        "values": by_id,
        "count": sum(v is not None for v in by_id.values()),
        "unknownIds": sorted(k for k, v in by_id.items() if v is None),
        "classes": {k: bisect.bisect_right(breaks, v) + 1 if v is not None else 0 for k, v in by_id.items()},
        "breaks": breaks,
        "unit": s["unit"],
        "mapRequired": True,
    }
