import bisect
import math

import pandas as pd

from .bivariate_tasks import BIVARIATE_TASKS
from .common import Blocked
from .fixtures import ROW_ID
from .map_oracles import reference_quantiles
from .units import label_has_unit, same_unit


def bivariate_answer(task, countries, tables):
    s = BIVARIATE_TASKS[task]
    if s.get("geography"):
        countries = countries.loc[countries[s["geography"]["field"]].isin(s["geography"]["values"])].copy()
    def values(key):
        table = tables[key]
        if table["Country Code"].duplicated().any():
            raise Blocked("Duplicate bivariate source country keys.")
        return countries.ISO_A3.map(pd.to_numeric(table.set_index("Country Code")[s["year"]], errors="raise"))
    x, y = values(s["x"]), values(s["y"])
    if s.get("derive") == "population_density":
        from .geometry_oracles import country_areas
        area = country_areas(countries)
        x = x / area.where(area > 0)
    elif s.get("derive"):
        total = values("population")
        if s["derive"] == "rural_share":
            x = 100*x/total.where(total > 0)
        else:
            y = y/total.where(total > 0)
    def mapped(series):
        return {fid: float(v) if pd.notna(v) and math.isfinite(v) else None for fid, v in zip(countries[ROW_ID], series, strict=True)}
    xv, yv = mapped(x), mapped(y)
    paired = [fid for fid in xv if xv[fid] is not None and yv[fid] is not None]
    xb, yb = reference_quantiles([xv[f] for f in paired], 3), reference_quantiles([yv[f] for f in paired], 3)
    classes = {f: bisect.bisect_right(yb, yv[f])*(len(xb)+1)+bisect.bisect_right(xb, xv[f])+1 if f in paired else 0 for f in xv}
    return {"ids": sorted(xv), "count": len(paired), "unknownIds": sorted(set(xv)-set(paired)),
        "values": xv, "valuesY": yv, "classes": classes, "xBreaks": xb, "yBreaks": yb,
        "xUnit": s["xUnit"], "yUnit": s["yUnit"], "bivariate": True, "mapRequired": True,
        "semantics": {"year": s["year"], "method": "three paired quantile classes per axis"}}


def check_bivariate(frame, field, claim, expected, snapshot, artifact):
    from .contour_grading import bound_layer
    from .grading import check_extra_results
    check_extra_results(frame, field, {**claim, "value_field": claim.get("y_value_field")}, {"values": expected["valuesY"]})
    column, layer = claim.get("class_field"), claim.get("map_layer_id")
    if column not in frame or frame.set_index(field)[column].to_dict() != expected["classes"]:
        raise Blocked("Bivariate joint classes differ from the independent paired classification.")
    bound_layer(snapshot, artifact, layer)
    display = snapshot.get("mapDisplays", {}).get(layer, {})
    view = next((x.get("blue:vector_presentation") for x in display.get("tilesets", []) if x.get("blue:vector_presentation")), None)
    if not view or view.get("categoryField") != column:
        raise Blocked("Map renderer did not receive the bivariate class legend.")
    categories = view.get("categories", [])
    size = (len(expected["xBreaks"])+1)*(len(expected["yBreaks"])+1)
    if (len(categories) != size+1 or {c.get("value") for c in categories} != set(range(size+1))
            or len({c.get("color") for c in categories}) != len(categories)):
        raise Blocked("Bivariate legend omits joint or missing classes or has indistinguishable colors.")
    if any(not all(label_has_unit(c.get("label", ""), expected[k]) for k in ("xUnit", "yUnit")) for c in categories if c["value"]):
        raise Blocked("Bivariate legend omits one of its measurement units.")
    metadata = artifact.get("item", {}).get("properties", {}).get("blue:bivariate_classification", {})
    if metadata.get("method") != "quantile" or metadata.get("requestedClasses") != 3:
        raise Blocked("Published bivariate method differs from the frozen method.")
    for key in ("xBreaks", "yBreaks"):
        actual = metadata.get(key)
        if (not isinstance(actual, list) or len(actual) != len(expected[key])
                or any(not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9) for a,b in zip(actual,expected[key],strict=True))):
            raise Blocked("Published bivariate class boundaries are incorrect.")
    if not all(same_unit(metadata.get(k), expected[k]) for k in ("xUnit", "yUnit")):
        raise Blocked("Published bivariate units are incorrect.")
