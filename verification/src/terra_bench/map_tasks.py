"""Frozen country-map protocols. Input conventions only; no reference values."""
import json

from .regional_tasks import DERIVED, GROUP_COMPARISONS, REGIONAL, YEAR_OVERRIDES, unit_for

INDICATORS = {
    "rail_length": ("IS.RRS.TOTL.KM", "2018", "route-km", "API_IS.RRS.TOTL.KM_DS2_en_csv_v2_1937.zip"),
    "electricity": ("EG.USE.ELEC.KH.PC", "2014", "kWh per capita", "API_EG.USE.ELEC.KH.PC_DS2_en_csv_v2_2767.zip"),
    "forest_percent": ("AG.LND.FRST.ZS", "2021", "% of land area", "API_AG.LND.FRST.ZS_DS2_en_csv_v2_102.zip"),
    "forest_area": ("AG.LND.FRST.K2", "2021", "km²", "API_AG.LND.FRST.K2_DS2_en_csv_v2_2627.zip"),
    "water_withdrawal": ("ER.H2O.FWTL.ZS", "2021", "% of internal resources", "API_ER.H2O.FWTL.ZS_DS2_en_csv_v2_7098.zip"),
    "water_volume": ("ER.H2O.FWTL.K3", "2021", "billion m³ per year", "API_ER.H2O.FWTL.K3_DS2_en_csv_v2_8364.zip"),
    "agriculture": ("NV.AGR.TOTL.ZS", "2023", "% of GDP", "API_NV.AGR.TOTL.ZS_DS2_en_csv_v2_4614.zip"),
    "labor": ("SL.TLF.TOTL.IN", "2023", "people", "API_SL.TLF.TOTL.IN_DS2_en_csv_v2_4341.zip"),
    "migration": ("SM.POP.NETM", "2023", "people (net migration)", "API_SM.POP.NETM_DS2_en_csv_v2_91.zip"),
    "population": ("SP.POP.TOTL", "2023", "people", "API_SP.POP.TOTL_DS2_en_csv_v2_56.zip"),
    "rural": ("SP.RUR.TOTL", "2023", "people", "API_SP.RUR.TOTL_DS2_en_csv_v2_6835.zip"),
    "gdp": ("NY.GDP.PCAP.CD", "2023", "current USD per capita", "API_NY.GDP.PCAP.CD_DS2_en_csv_v2_77536.zip"),
    "fertility": ("SP.DYN.TFRT.IN", "2022", "births per woman", "API_SP.DYN.TFRT.IN_DS2_en_csv_v2_821.zip"),
}

# Original task texts are checked against the pinned released inventory in tests.
MAP_TASKS = {
    "252796": ("gdp", "Show the distribution of GDP per capita across different world regions."),
    "720409": ("fertility", "Map total fertility rates across different regions."),
    "348947": ("forest_area", "Map total forest area in square kilometers by region."),
    "523121": ("electricity", "Show me map of electricity consumption in the World."),
    "761363": ("electricity", "Make a World map of electricity consumption per capita by country."),
    "960622": ("forest_percent", "Create a world map showing forest area as percentage of land area by country."),
    "634036": ("water_withdrawal", "Map total freshwater withdrawals as percentage of internal resources by country."),
    "971959": ("agriculture", "Visualize agricultural value added as percentage of GDP worldwide."),
    "553414": ("labor", "Create a map showing total labor force distribution across countries."),
    "702855": ("migration", "Display net migration patterns on a world map."),
    "908870": ("population", "Visualize total population distribution by country."),
    "296055": ("forest_percent", "Create a map showing forest coverage percentage across different countries."),
    "375632": ("gdp", "Map the global distribution of GDP per capita"),
    "737732": ("water_volume", "Show total freshwater withdrawals by country."),
    "914148": ("agriculture", "Visualize agricultural contribution to GDP worldwide."),
    "714649": ("forest_area", "Map absolute forest area distribution globally. "),
    "476358": ("labor", "Show total labor force distribution across the world."),
    "837688": ("fertility", "Create a map of global fertility rates. "),
    "250712": ("migration", "Visualize net migration patterns worldwide. "),
    "460208": ("population", "Map total population distribution globally."),
    "917242": ("rural", "Show rural population distribution across countries."),
    "602318": ("water_withdrawal", "Map freshwater withdrawals as percentage of resources."),
    "861416": ("gdp", "Visualize regional economic patterns using GDP per capita."),
    "530802": ("agriculture", "Map agricultural GDP contribution by region."),
    "270481": ("labor", "Show global labor force concentration."),
    "718627": ("fertility", "Create a map of global demographic patterns using fertility rates."),
    "833697": ("water_withdrawal", "Map water resource utilization globally."),
}
MAP_TASKS.update({task: spec[:2] for task, spec in REGIONAL.items()})
MAP_TASKS.update({task: spec[:2] for task, spec in DERIVED.items()})
REGION_AGGREGATE_TASKS = {'252796', '720409', '348947'}


def map_protocols():
    result = {}
    for task, (key, question) in MAP_TASKS.items():
        indicator, year, unit, _ = INDICATORS[key]
        year, unit = YEAR_OVERRIDES.get(task, year), unit_for(task, unit)
        result[task] = {"title": question.strip().rstrip('.'), "question": question,
            "bbox": [-180, -85, 180, 85], "family": "country-choropleth", "indicator": key,
            "year": year, "unit": unit,
            "clarification": f"Use the frozen country polygons and World Bank {indicator} {year} column, in {unit}. "
                "These are country-level indicators, not a subnational surface or a new regional aggregation. "
                "Join the supplied ISO_A3 to Country Code exactly. Nonmatching identifiers and missing measurements remain unknown; do not guess them or substitute another year. "
                "Retain every original country feature and benchmark_row_id, including unknowns. No data must have a distinct map category, not zero. "
                "Create a quantitative choropleth with five quantile classes (fewer only if tied values collapse breaks), a visible legend with numeric bounds and units, "
                "and a neutral No data category. Values equal to a class break enter the upper class. Preserve negative and genuine zero values. "
                "This fixed classification and year are disclosed evaluation conventions; do not retrieve live replacements.",
            "outputContract": "Add the resulting quantitative country layer to the map and retain an inspectable data artifact containing the original country geometry, benchmark_row_id, numeric value and class. "
                "End with one fenced JSON object: {count: countries with a known numeric value, unknown_count: countries without one, coverage_note: string, "
                "selection: {collectionId, itemId, assetKey}, value_field: numeric_column_name, class_field: classification_column_name, map_layer_id: delivered_layer_id}. "
                "The artifact must include known AND unknown countries, not only the known subset. Explain the year, units, key limitations and legend in the final response."}
        if task in REGIONAL or task in DERIVED:
            if task in REGIONAL:
                result[task]["clarification"] = result[task]["clarification"].replace(
                    "Retain every original country feature and benchmark_row_id",
                    "Retain every original country feature in the declared geography and its benchmark_row_id")
            result[task]["clarification"] += " Count original boundary features, not deduplicated sovereign states; preserve all source rows that meet the declared geography. Country-code sentinels such as -99 remain unmatched."
        if task in REGION_AGGREGATE_TASKS:
            result[task]['clarification'] = result[task]['clarification'].replace(
                'These are country-level indicators, not a subnational surface or a new regional aggregation. ',
                'Use the published World Bank regional aggregates already present in the frozen table, not individual country values or a mean/sum computed from countries. ')
            result[task]['clarification'] = result[task]['clarification'].replace(
                'Join the supplied ISO_A3 to Country Code exactly.',
                'Join original country geometry REGION_WB to table Country Name exactly. This selects the seven published all-income regional aggregates; Antarctica has no corresponding value and remains unknown.')
            result[task]['clarification'] += (
                ' The reporting regions are the supplied World Bank REGION_WB groups. Every original country polygon carries its region’s published value; '
                'retain original boundaries and IDs rather than inventing regional geometry. This does not mean the country itself has that value. '
                'The five-quantile display classification operates on those original feature rows, so its breaks reflect repeated regional values; '
                'this is only a display convention, not population weighting or recomputation of the regional statistic. Label the map and answer as regional aggregates.')
        if task in REGIONAL:
            field, allowed = REGIONAL[task][2:]
            result[task]["clarification"] += f" Geography is fixed to original country features with {field} in {json.dumps(allowed)}; retain all matching source geometries, and no others. Classification is calculated only over this geography. Membership reflects this disclosed benchmark edition, not current organization membership."
        if task in {"598665", "898861"}:
            result[task]["clarification"] += " The archived benchmark uses agriculture's share of GDP as its economic indicator. Label it accurately: this is not yield, production volume or labor productivity. The Mediterranean case follows its disclosed three-subregion approximation, not a coastal buffer."
        if task == "498483":
            result[task]["clarification"] += " As in the archived reference, the three named subregions are a country-level Mediterranean approximation, not measured coastal strips. Freshwater withdrawals as a share of internal resources is the declared screening indicator, not a local drought or water-stress model. Label these geographic and indicator limitations explicitly."
        if task in DERIVED:
            if task == '734213':
                result[task]['clarification'] = result[task]['clarification'].replace(f'World Bank {indicator} {year} column, in {unit}.', 'World Bank 2019 net migration in people and 2019 total population in people.')
                result[task]['clarification'] += 'Define annual net migration rate as 1000 times net migration divided by total population, in net migrants per 1000 people. A missing numerator, missing denominator or nonpositive population is unknown. Identify the three highest known rates in descending order; break exact ties by NAME_EN alphabetically. These are rates, not absolute migrant counts.'
                result[task]['outputContract'] += ' Include top_countries as the three original NAME_EN country names in that ranking order in the final JSON.'
            elif task == '399319':
                result[task]['clarification'] = result[task]['clarification'].replace(f'World Bank {indicator} {year} column, in {unit}.', 'World Bank 2021 freshwater withdrawals in billion m³/year, 2021 withdrawals as percent of internal resources, and 2021 total population in people.')
                result[task]['clarification'] += 'Use an explicitly derived estimate of INTERNAL renewable water resources: withdrawal volume times 1e9 divided by (withdrawal percentage / 100), then divide by population. This recovers the reported ratio denominator, not total renewable resources including external inflows, available drinking water or utility capacity. Rounding, different collection methods and intermittently updated national observations limit accuracy. Missing inputs or nonpositive percentage/population are unknown, not zero. Western Asia is the fixed country-level Middle East approximation. Label both the derived and internal-only nature on the map and in the answer.'
            elif DERIVED[task][2] == "population_density":
                from .geometry_conventions import DENSITY_CONVENTION
                result[task]["clarification"] = result[task]["clarification"].replace(
                    f"World Bank {indicator} {year} column, in {unit}.",
                    f"World Bank {indicator} {year} population column in people; derived map units are people/km².")
                result[task]["clarification"] += DENSITY_CONVENTION
                if task == "170096":
                    result[task]["clarification"] += "Here regions means the original country-level features worldwide; no continent aggregation or unobserved within-country distribution is inferred."
            elif DERIVED[task][2] == "rural_share":
                result[task]["clarification"] = result[task]["clarification"].replace(
                    f"World Bank {indicator} {year} column, in {unit}.",
                    "World Bank 2023 rural and total population columns, both measured in people. The derived map is in percent of population.")
                result[task]["clarification"] += " The mapped quantity is 100 times 2023 rural population divided by 2023 total population, joined by the same country code. Missing numerator/denominator or zero denominator is unknown. For rural-urban distribution, the rural share is sufficient and urban share is its complement."
            else:
                result[task]["clarification"] += " Use forest coverage in 2021 minus 2011, in percentage points over the archived decade. Negative values indicate loss; this is not an annual compound percentage or absolute forest area. Both years must exist."
        if task in GROUP_COMPARISONS:
            field, groups = GROUP_COMPARISONS[task]
            result[task]["clarification"] += f" Also compare unweighted means of known original country features by these fixed {field} groups: {json.dumps(groups)}. Do not treat missing values as zero. These are country comparisons, not basin-clipped or population-weighted estimates."
            result[task]["outputContract"] += " Include a metrics object in the final JSON with group-name keys and their numeric means (or null if no known members), and explain the comparison."
    return result


def map_assets():
    return {key: {"file": filename, "kind": "table", "title": f"World Bank {indicator}",
                  "edition": f"Frozen GeoBenchX World Development Indicators; use {year}", "units": {year: unit}}
            for key, (indicator, year, unit, filename) in INDICATORS.items()}


def map_source_terms():
    return {key: {"status": "verified", "license": "CC-BY-4.0",
                  "attribution": f"World Bank World Development Indicators {indicator}; original archived producer attribution retained.",
                  "evidence": f"https://data.worldbank.org/indicator/{indicator}",
                  "finding": "Official indicator page declares CC BY-4.0. Frozen archive only, no live value substitution."}
            for key, (indicator, _, _, _) in INDICATORS.items()}
