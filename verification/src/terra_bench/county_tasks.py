"""County statistical maps; data preparation is performed by Terra, not fixtures."""

COUNTY_TASKS = {
    "476053": {
        "question": "Map the distribution of tuberculosis cases across Massachusetts counties. ",
        "state": "25",
        "assets": ["counties", "tb_ma"],
        "table": "tb_ma",
        "field": "TB Case Rate[1] 2023(cases per 100,000)",
        "unit": "cases per 100,000 people",
    },
}

COUNTY_HEAT_TASKS = {
    "272736": {
        "question": "Make a heatmap of tuberculosis cases in New York State",
        "states": {"36": "tb_ny"},
        "assets": ["counties", "tb_ny"],
    },
    "695398": {
        "question": "Create heatmap of TB cases in states with available data.",
        "states": {"25": "tb_ma", "36": "tb_ny"},
        "assets": ["counties", "tb_ma", "tb_ny"],
    },
}
COUNTY_GRID = {
    "bounds": [-500000, 1000000, 3000000, 3500000],
    "crs": "EPSG:5070",
    "resolutionX": 5000,
    "resolutionY": 5000,
}
COUNTY_RADIUS = 50000


def county_heat_protocols():
    import json

    return {
        task: {
            "title": s["question"],
            "question": s["question"],
            "family": "county-heatmap",
            "bbox": [-80, 40, -69, 46],
            "clarification": f"Use only the frozen 2023 county TB tables for these states: {json.dumps(s['states'])}. Select original Census county features by STATEFP before joining NAME to the corresponding table's County column. "
            "Use tb_ny '2023 cases' and tb_ma 'Number of Cases', not rates. Repeated county names across states must not mix; aggregate state/city totals and footnotes are not counties. "
            "Preserve genuine zero cases. Missing counts are unknown, never zero. Derive one geometric centroid per original county in EPSG:5070 and weight it by the published county case count. "
            "This represents county totals at geometric centroids, not patient locations or within-county disease density. No population-weighted centroid is claimed. "
            f"Use a disclosed metric raster adaptation instead of the reference's screen-pixel radius: grid={json.dumps(COUNTY_GRID)}, Gaussian radiusM={COUNTY_RADIUS} is three sigma, kernel truncated at four sigma with constant-zero padding. "
            "Use weightField='case_count' and weightUnit='cases'. A cell measures smoothed case-count mass per cell, not cases/km². Preserve complete grid including zero cells; no normalization, resampling or extra clipping. "
            "The two-state task corrects the archived reference's joining of tables by county name without state disambiguation; no cases may be counted twice.",
            "outputContract": "Add the heatmap and publish both its raster and an inspectable original-county polygon selection carrying case_count and benchmark_row_id. "
            "End with one fenced JSON: {count: number of counties with known counts, unknown_count: counties with unknown counts, coverage_note, "
            "selection:{collectionId,itemId,assetKey} for original county polygons with known counts, value_field:'case_count', "
            "density:{collectionId,itemId,assetKey} for the raster, map_layer_id: actual heatmap layer ID}. Clearly disclose centroid aggregation and frozen year.",
        }
        for task, s in COUNTY_HEAT_TASKS.items()
    }


def county_protocols():
    return {
        task: {
            "title": s["question"],
            "question": s["question"],
            "family": "county-choropleth",
            "bbox": [-74, 41, -69, 43],
            "clarification": "Use Census TIGER/Line 2024 original county polygons with STATEFP='25', and the frozen Massachusetts 2023 TB table. "
            "Map the published TB case RATE per 100,000 people, following the first released reference method; retain Number of Cases as supporting information. "
            "Join NAME to County exactly after selecting the state. Footnotes and totals are not counties. Keep all matching original county features, source geometry and benchmark_row_id. "
            "Genuine zero cases and zero rates remain zero; unknown measurements remain unknown. Do not substitute current rates or infer individual patient locations. "
            "Use five quantile classes (collapse ties), upper class on equal breaks, and a distinct neutral No data category with numeric bounds and units in the legend. "
            "This is a county-level public aggregate, not a patient map or medical risk recommendation.",
            "outputContract": "Publish an inspectable county data artifact and add its quantitative map. End with one fenced JSON object containing "
            "count (known counties), unknown_count (unknown counties), coverage_note, selection: {collectionId,itemId,assetKey}, value_field, class_field and map_layer_id. "
            "Explain the year, rate versus count distinction, and county-level limitations.",
        }
        for task, s in COUNTY_TASKS.items()
    }
