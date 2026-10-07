"""Two-variable questions and disclosed quantitative-map conventions."""
BIVARIATE_TASKS = {
    "984439": {"question": "Compare the freshwater withdrawal between African countries with and without significant railway networks.",
        "assets": ["countries", "water_volume", "rail_length"], "year": "2018", "x": "water_volume", "y": "rail_length",
        "xUnit": "billion m³ per year", "yUnit": "route-km", "geography": {"field": "CONTINENT", "values": ["Africa"]},
        "meaning": "Use the released reference's second accepted approach: a paired 2018 country choropleth of freshwater withdrawals and railway route length. This compares relative railway-network scale, not a binary assertion that countries with missing railway statistics have no railways. Do not invent a significance threshold or convert unknown length to zero; discuss low/high paired quantile classes as relative scale only. No causal water-rail claim is warranted."},
    "958938": {"question": "Map the relationship between population density and forest coverage in Asian countries.",
        "assets": ["countries", "population", "forest_percent"], "year": "2021", "x": "population", "y": "forest_percent",
        "xUnit": "people/km²", "yUnit": "% of land area", "derive": "population_density",
        "geography": {"field": "CONTINENT", "values": ["Asia"]}},
    "301626": {"question": "Map the relationship between GDP per capita and electric power consumption per capita globally.",
        "assets": ["countries", "gdp", "electricity"], "year": "2014", "x": "gdp", "y": "electricity",
        "xUnit": "current USD per capita", "yUnit": "kWh per capita"},
    "663841": {"question": "Make a map to explore the relationship between forest area (% of land area) and annual freshwater withdrawals (% of internal resources) in 2015 globally.",
        "assets": ["countries", "forest_percent", "water_withdrawal"], "year": "2015", "x": "forest_percent", "y": "water_withdrawal",
        "xUnit": "% of land area", "yUnit": "% of internal resources"},
    "854050": {"question": "Visualize at one map rural population percentage (calculated from total and rural population) and agriculture value added as % of GDP for 2019.",
        "assets": ["countries", "rural", "population", "agriculture"], "year": "2019", "x": "rural", "y": "agriculture",
        "xUnit": "% of population", "yUnit": "% of GDP", "derive": "rural_share"},
    "631643": {"question": "Make a map visualizing relationship between fertility rate and net migration (normalized by total population) across the World.",
        "assets": ["countries", "fertility", "migration", "population"], "year": "2022", "x": "fertility", "y": "migration",
        "xUnit": "births per woman", "yUnit": "net migrants per person", "derive": "migration_rate"},
}


def bivariate_protocols():
    result = {}
    for task, s in BIVARIATE_TASKS.items():
        extra = ("X is 100 times rural population divided by total population. " if s.get("derive") == "rural_share" else
                 "Y is net migration divided by total population, NOT multiplied by 100 or 1000. " if s.get("derive") == "migration_rate" else "")
        result[task] = {"title": s["question"], "question": s["question"], "bbox": [-180,-85,180,85], "family": "bivariate-map",
            "clarification": f"Use the frozen country boundaries and the {s['year']} column of every supplied indicator. "
                f"X is {s['x']} ({s['xUnit']}); Y is {s['y']} ({s['yUnit']}). " + extra +
                "Join ISO_A3 to Country Code exactly. Keep every original country feature and benchmark_row_id, including unknowns and repeated country identities. "
                "Do not guess missing values or substitute years. A missing numerator or missing/zero denominator is unknown. "
                "Make one bivariate choropleth: three quantile classes on each axis, computed over rows where BOTH measurements are known. "
                "Collapse tied breaks; equality enters the upper class. Combined class is (yClass-1)*xClasses+xClass with 1-based axes. "
                "Missing either measurement is neutral class zero. Retain the numeric X and Y values even when only one is missing. "
                "The legend must distinguish joint classes with both ranges and units. These are disclosed evaluation conventions, not live-data replacements or proof of causation.",
            "outputContract": "Add the quantitative joint-class layer to the map and retain its complete vector artifact. "
                "End with one fenced JSON object: {count: rows with both measurements known, unknown_count: rows missing either, coverage_note: string, "
                "selection: {collectionId,itemId,assetKey}, value_field: X numeric column, y_value_field: Y numeric column, "
                "class_field: joint class column, map_layer_id: delivered layer ID}. Explain year, units, missing coverage and the relationship without claiming causality."}
        if s.get("derive") == "population_density":
            from .geometry_conventions import DENSITY_CONVENTION
            result[task]["clarification"] += DENSITY_CONVENTION
        if s.get('meaning'):
            result[task]['clarification'] += ' ' + s['meaning']
        if s.get("geography"):
            import json
            geo = s["geography"]
            result[task]["clarification"] += f"Keep only original country features with {geo['field']} in {json.dumps(geo['values'])}, including unknowns; all quantiles use this geography."
    return result
