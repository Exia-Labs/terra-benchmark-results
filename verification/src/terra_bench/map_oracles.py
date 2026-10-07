"""Country map oracle and quantitative display checks, independent of Terra code."""
import bisect
import math

import pandas as pd

from .common import Blocked
from .fixtures import ROW_ID
from .map_tasks import INDICATORS, MAP_TASKS, REGION_AGGREGATE_TASKS
from .regional_tasks import DERIVED, GROUP_COMPARISONS, REGIONAL, YEAR_OVERRIDES, unit_for
from .units import label_has_unit


def reference_quantiles(values, classes=5):
    ordered = sorted(float(v) for v in values if v is not None and math.isfinite(v))
    if not ordered or ordered[0] == ordered[-1]:
        return []
    breaks = []
    for index in range(1, classes):
        position = (len(ordered) - 1) * index / classes
        low = math.floor(position)
        value = ordered[low] + (ordered[math.ceil(position)] - ordered[low]) * (position - low)
        if ordered[0] < value < ordered[-1] and value not in breaks:
            breaks.append(value)
    return breaks


def map_answer(task, countries, table, extra=None):
    key = MAP_TASKS[task][0]
    indicator, year, unit, _ = INDICATORS[key]
    year, unit = YEAR_OVERRIDES.get(task, year), unit_for(task, unit)
    if task in REGIONAL:
        field, allowed = REGIONAL[task][2:]
        countries = countries.loc[countries[field].isin(allowed)].copy()
        if countries.empty:
            raise Blocked("Declared regional geography has no matching source features.")
    if table["Country Code"].duplicated().any():
        raise Blocked("Ambiguous country-map join keys.")
    values = countries.ISO_A3.map(pd.to_numeric(table.set_index("Country Code")[year], errors="raise"))
    if task in REGION_AGGREGATE_TASKS:
        if table['Country Name'].duplicated().any():
            raise Blocked('Ambiguous regional aggregate names.')
        values = countries.REGION_WB.map(pd.to_numeric(table.set_index('Country Name')[year], errors='raise'))
    if task in DERIVED:
        if DERIVED[task][2] in {'migration_per_thousand','internal_water_per_capita'}:
            population = extra['population']
            if population['Country Code'].duplicated().any():
                raise Blocked('Ambiguous population denominator keys.')
            total = countries.ISO_A3.map(pd.to_numeric(population.set_index('Country Code')[year],errors='raise'))
            if DERIVED[task][2] == 'migration_per_thousand':
                values = 1000 * values / total.where(total > 0)
            else:
                percentage = extra['water_withdrawal']
                if percentage['Country Code'].duplicated().any():
                    raise Blocked('Ambiguous withdrawal share keys.')
                share = countries.ISO_A3.map(pd.to_numeric(percentage.set_index('Country Code')[year],errors='raise'))
                values = values * 1e11 / share.where(share > 0) / total.where(total > 0)
        elif DERIVED[task][2] == "population_density":
            from .geometry_oracles import country_areas
            area = country_areas(countries)
            values = values / area.where(area > 0)
        elif DERIVED[task][2] == "rural_share":
            total = extra["population"]
            if total["Country Code"].duplicated().any():
                raise Blocked("Ambiguous denominator country keys.")
            denominator = countries.ISO_A3.map(pd.to_numeric(total.set_index("Country Code")[year], errors="raise"))
            values = 100 * values / denominator.where(denominator > 0)
        else:
            initial = countries.ISO_A3.map(pd.to_numeric(table.set_index("Country Code")["2011"], errors="raise"))
            values = values - initial
    by_id = {fid: float(v) if pd.notna(v) and math.isfinite(v) else None for fid, v in zip(countries[ROW_ID], values, strict=True)}
    breaks = reference_quantiles(by_id.values())
    answer = {"ids": sorted(countries[ROW_ID]), "count": sum(v is not None for v in by_id.values()),
        "unknownIds": sorted(k for k, v in by_id.items() if v is None), "values": by_id,
        "classes": {fid: bisect.bisect_right(breaks, value) + 1 if value is not None else 0 for fid, value in by_id.items()},
        "breaks": breaks, "mapRequired": True, "unit": unit, "identityField": ROW_ID,
        "semantics": {"indicator": indicator, "year": year, "join": "ISO_A3/Country Code", "classification": "five quantiles, ties collapsed"}}
    if task in REGION_AGGREGATE_TASKS:
        answer['semantics']['join'] = 'REGION_WB/Country Name; published regional aggregates'
    if task in GROUP_COMPARISONS:
        field, groups = GROUP_COMPARISONS[task]
        answer["metrics"] = {}
        for name, eligible in groups.items():
            measured = [by_id[row[ROW_ID]] for _, row in countries.iterrows()
                        if row[field] in eligible and by_id[row[ROW_ID]] is not None]
            answer["metrics"][name] = sum(measured) / len(measured) if measured else None
    if task == '734213':
        names = countries.set_index(ROW_ID).NAME_EN.to_dict()
        answer['topCountries'] = [names[f] for f in sorted((f for f,v in by_id.items() if v is not None),key=lambda f:(-by_id[f],names[f]))[:3]]
    if task == '399319':
        answer['answerConcepts'] = [['internal'], ['derived','inferred','estimate','estimated']]
    return answer


def check_map(frame, record_field, claim, expected, snapshot, artifact):
    column, layer_id = claim.get("class_field"), claim.get("map_layer_id")
    if not isinstance(column, str) or column not in frame or not isinstance(layer_id, str):
        raise Blocked("Map result omits its class field or delivered layer identity.")
    for fid, value in frame.set_index(record_field)[column].items():
        if pd.isna(value) or value != expected["classes"][str(fid)]:
            raise Blocked("Quantitative map classes differ from the independent classification.")
    from .map_bindings import verify_map_binding
    verify_map_binding(snapshot, artifact, layer_id)
    display = snapshot.get("mapDisplays", {}).get(layer_id)
    sets = display.get("tilesets", []) if isinstance(display, dict) else []
    view = next((s.get("blue:vector_presentation") for s in sets if s.get("blue:vector_presentation")), None)
    if not view or view.get("categoryField") != column:
        raise Blocked("Map renderer did not receive the quantitative classification field and legend.")
    categories = view.get("categories", [])
    category_values = [c.get("value") for c in categories]
    if set(category_values) != set(range(len(expected["breaks"]) + 2)) or len(set(category_values)) != len(category_values):
        raise Blocked("Map legend has missing or duplicated classes.")
    known = [c for c in categories if c["value"] != 0]
    if len({c.get("color") for c in categories}) != len(categories):
        raise Blocked("Map classes or missing data are not visually distinguishable.")
    if any(not label_has_unit(c.get("label", ""), expected["unit"]) for c in known):
        raise Blocked("Quantitative map legend omits measurement units.")
    props = artifact.get("item", {}).get("properties", {})
    metadata = props.get("blue:numeric_classification", {})
    actual_breaks = metadata.get("breaks")
    if (metadata.get("method") != "quantile" or not isinstance(actual_breaks, list)
            or len(actual_breaks) != len(expected["breaks"])
            or any(not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9) for a, b in zip(actual_breaks, expected["breaks"], strict=True))):
        raise Blocked("Published map class boundaries do not match the declared quantitative method.")
