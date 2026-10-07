"""One original question can require several independently verified map panels."""

SERIES_TASKS = {
    "438953": {
        "question": "Create a bivariate map showing the relationship between CO2 emissions per capita and greenhouse gases emissions per capita for 1990 and 2020 across all countries.",
        "assets": ["countries", "co2", "ghg"], "years": ["1990", "2020"], "bivariate": True,
        "x": "co2", "y": "ghg", "xKey": "Country name", "yKey": "Country Name", "geographyKey": "NAME_EN",
        "xUnit": "tonnes CO2 per person", "yUnit": "tonnes CO2e per person",
    },
    "702872": {
        "question": "Make a series of maps with share of forest covered areas in countries of South Asia in 2005, 2015 and the last available year.",
        "assets": ["countries", "forest_percent"],
        "years": ["2005", "2015", "2021"],
        "indicator": "forest_percent",
        "regionField": "SUBREGION",
        "regionMembers": ["Southern Asia"],
        "unit": "% of land area",
    }
}


def series_protocols():
    result = {
        task: {
            "title": s["question"],
            "question": s["question"],
            "family": "map-series",
            "bbox": [-180, -85, 180, 85],
            "clarification": "Use the frozen WDI AG.LND.FRST.ZS columns 2005, 2015 and 2021, each percent of land area. Last available year means 2021 in this frozen source, not a live replacement. "
            "Retain original country features with SUBREGION=Southern Asia and join ISO_A3 to Country Code exactly. Keep unmatched or missing measurements as unknown, not zero, and preserve benchmark_row_id and original geometry. "
            "Produce three separate quantitative maps, one per year. For each year independently use five quantile classes, fewer only for collapsed ties, upper class on equality, and a separate neutral No data category. "
            "Each legend must show numeric bounds and units; disclose that per-year class boundaries differ so equal colors do not imply equal percentages across years. "
            "This freezes the reference solution years and regional membership; no country may be dropped because its measurement is missing.",
            "outputContract": "Add all three maps and retain their inspectable data artifacts. End with one fenced JSON object: "
            "{count: number of delivered year maps, unknown_count: total missing country-year measurements across all three panels, coverage_note: string, selection: artifact identity for the 2005 panel, "
            "panels: [{year: string, count: known country features, unknown_count: unknown country features, selection: {collectionId,itemId,assetKey}, value_field: numeric field, class_field: class field, map_layer_id: actual layer ID}]}. "
            "Give one panel for each required year and explain the observed changes without claiming comparability of different per-year colors.",
        }
        for task, s in SERIES_TASKS.items()
    }
    result["438953"].update(
        clarification="Use all original country features and the frozen OWID CO2 and GHG tables for 1990 and 2020, not current datasets. "
            "Join country NAME_EN exactly to CO2 'Country name' and GHG 'Country Name', as in the released reference. Do not fuzzy-match, replace original geometries or drop unmatched features. "
            "CO2 uses tonnes CO2 per person; GHG uses tonnes CO2-equivalents per person including land use. Preserve finite negative values and genuine zeros; missing or unmatched values remain unknown. "
            "Create two distinct bivariate maps, one per year, using three marginal quantile classes per axis over the same paired-known rows within each year, collapsing ties. "
            "Use increasing x=CO2, y=GHG classes with joint code (yClass-1)*effectiveXClasses+xClass; code 0 for either missing value. Equality goes to the upper class. "
            "Each actual map needs a two-axis legend with numeric bounds and both units, plus neutral No data. State that per-year breaks differ and that this is a visual association, not causal inference.",
        outputContract="Add both year maps and retain their inspectable data artifacts, preserving benchmark_row_id and original geometry. End with one fenced JSON object: "
            "{count: number of delivered year maps, unknown_count: total country-year rows missing either variable, coverage_note: string, selection: artifact identity for 1990, "
            "panels: [{year: string, count: paired-known features, unknown_count: features missing either variable, selection: {collectionId,itemId,assetKey}, value_field: CO2 numeric field, "
            "y_value_field: GHG numeric field, class_field: joint class field, map_layer_id: actual layer ID}]}. Give both 1990 and 2020 panels."
    )
    return result
