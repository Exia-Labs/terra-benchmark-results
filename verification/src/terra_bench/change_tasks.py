"""Frozen multi-year country-change selections; no computed reference values."""

CHANGE_TASKS = {
    "104119": {
        "question": "How many Latin American seaports are located in regions with high population growth?",
        "assets": ["seaports", "countries", "population"],
        "base": "seaports",
        "years": ["2013", "2023"],
        "regionField": "SUBREGION",
        "regionMembers": ["Central America", "Caribbean", "South America"],
        "operator": "gt",
        "threshold": 1.1,
        "calculation": "High growth means 2023 total population divided by 2013 total population strictly greater than 1.1, using WDI SP.POP.TOTL. This freezes the reference's ten-year comparison and 10% growth cutoff. Count records in the supplied USGS mineral-exporting-port inventory, not all modern commercial seaports.",
    },
    "932053": {
        "question": "How many African power stations are located in countries with significant forest loss?",
        "assets": ["power_stations", "countries", "forest_area"],
        "base": "power_stations",
        "years": ["1990", "2021"],
        "calculation": "Significant loss means forest area in 2021 divided by forest area in 1990 is strictly less than 0.79 (more than 21% loss). Use WDI AG.LND.FRST.K2 in square kilometres. The released references offer several incompatible thresholds; this protocol freezes the first reference's 0.79 convention, not any decrease or a percentage-point threshold.",
    },
    "710732": {
        "question": "How many mineral extraction facilities in Africa are located in countries with rapid urbanization?",
        "assets": ["facilities", "countries", "rural", "population"],
        "base": "facilities",
        "years": ["2013", "2023"],
        "calculation": "Rapid urbanization means rural population divided by total population in 2023 minus that same fraction in 2013 is strictly less than -0.03. This is a drop of more than three percentage points, not a 3% relative change. Use WDI SP.RUR.TOTL and SP.POP.TOTL for those exact years.",
    },
}


def change_protocols():
    import json

    return {
        task: {
            "title": spec["question"].rstrip("?"),
            "question": spec["question"],
            "family": "country-change-selection",
            "bbox": [-180, -85, 180, 85] if spec.get("regionField") else [-26, -36, 65, 39],
            "clarification": spec["calculation"]
            + (
                f" Use original country polygons with {spec['regionField']} in {json.dumps(spec['regionMembers'])}. "
                if spec.get("regionField")
                else " Use original country polygons with CONTINENT=Africa. "
            )
            + "Use exact ISO_A3/Country Code matching. "
            "A point qualifies only when strictly within a qualifying original country polygon. Count original point records once, regardless of operational status. "
            "Missing observations, nonmatching country codes, nonpositive denominators and nonfinite derived values are unknown, never zero. "
            "Points in unknown-measurement countries and points without valid geometry are unknown. Valid points outside all selected geographical polygons do not qualify and are not counted as unknown. "
            "Do not infer locations from point country-name attributes or fetch live substitutes. Maps are optional.",
            "outputContract": "Produce an inspectable selected-point artifact retaining original geometry and benchmark_row_id. "
            "End with one fenced JSON object: {count: selected original point records, unknown_count: points with unknown eligibility under the stated coverage rule, "
            "unlocated_count: original point records lacking valid geometry, coverage_note: string, selection: {collectionId, itemId, assetKey}}. "
            "Explain the fixed years, threshold and coverage in the final answer.",
        }
        for task, spec in CHANGE_TASKS.items()
    }
