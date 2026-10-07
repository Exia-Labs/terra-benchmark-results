"""Explicit task selection. Frozen campaigns own their protocol, not a global pair."""
from pathlib import Path

from .bivariate_tasks import bivariate_protocols
from .change_tasks import change_protocols
from .common import ROOT, TASK_IDS, Blocked, read
from .contour_tasks import contour_protocols
from .control_tasks import CONTROL_TASKS, control_protocols
from .county_tasks import county_heat_protocols, county_protocols
from .heat_tasks import heat_protocols
from .map_tasks import map_protocols, map_source_terms
from .overlay_tasks import overlay_protocols
from .population_tasks import population_protocols, population_terms
from .proximity_tasks import proximity_protocols
from .remaining_tasks import remaining_protocols, remaining_terms
from .series_tasks import series_protocols


def protocol_for(task_ids=TASK_IDS):
    base = read(ROOT / "protocol.json")
    extra = read(ROOT / "protocol-expansion.json")
    parallel = read(ROOT / "protocol-parallel.json")
    maps = map_protocols()
    contours = contour_protocols()
    bivariates = bivariate_protocols()
    changes = change_protocols()
    heats = heat_protocols()
    known = {**base["tasks"], **extra["tasks"], **parallel["tasks"], **maps, **contours, **bivariates, **changes, **heats, **series_protocols(), **county_protocols(), **county_heat_protocols(), **population_protocols()}
    known.update(overlay_protocols())
    known.update(proximity_protocols())
    known.update(remaining_protocols())
    from .water_tasks import protocols as water_protocols
    known.update(water_protocols())
    from .flood_tasks import protocols as flood_protocols
    known.update(flood_protocols())
    known.update({task: spec for task, spec in contours.items() if task == "480358"})
    from .lake_snow import protocol as lake_snow_protocol
    known.update(lake_snow_protocol())
    from .snow_rail import protocol as snow_rail_protocol
    known.update(snow_rail_protocol())
    from .point_count import protocol as point_count_protocol
    known.update(point_count_protocol())
    from .county_density import protocol as county_density_protocol
    known.update(county_density_protocol())
    from .snow_population import protocol as snow_population_protocol
    known.update(snow_population_protocol())
    if set(task_ids) & CONTROL_TASKS.keys():
        known.update(control_protocols())
    ids = tuple(task_ids)
    if not ids or len(ids) != len(set(ids)) or set(ids) - known.keys():
        raise Blocked("Select distinct known benchmark task IDs.")
    base["tasks"] = {task: known[task] for task in ids}
    if any(task in extra["tasks"] for task in ids):
        base["version"] = 2
        base["adaptations"] = [*base["adaptations"], *extra["adaptations"]]
    if any(task in parallel["tasks"] for task in ids):
        base["version"] = 3
        base["adaptations"] = [*base["adaptations"], *parallel["adaptations"]]
    if any(task in maps for task in ids):
        base["version"] = 4
        base["adaptations"].append("Country-map family: frozen year/indicator, exact ISO_A3 join, complete unknown coverage, five quantile classes and inspectable map binding; independently verified values and legend.")
    if any(task in contours for task in ids):
        base["version"] = 5
        base["adaptations"].append("Contour family: disclosed levels and original-grid marching-square geometry; verified complete isolines and actual map/overlay bindings.")
    if any(task in bivariates for task in ids):
        base["version"] = 6
        base["adaptations"].append("Bivariate family: frozen years, exact joins and paired three-quantile joint classification; numerical values and actual legend independently verified.")
    if any(task in changes for task in ids):
        base["version"] = 7
        base["adaptations"].append("Country-change selections: explicitly frozen multi-year definitions and strict thresholds, exact source IDs and unknown-location accounting.")
    if any(task in heats for task in ids):
        base["version"] = 8
        base["adaptations"].append("Heatmap family: fixed 25 km equal-area EPSG:6933 cells, 150 km three-sigma Gaussian radius, declared count or numeric weights; metric raster adaptation replaces screen-pixel heatmaps and is exhaustively checked against independent binning/convolution.")
    if any(task in series_protocols() for task in ids):
        base['version']=9
        base['adaptations'].append('Map series: independently checked years, full original feature coverage, per-year classifications and distinct authoritative map bindings; no single-panel substitution.')
    if any(task in county_protocols() or task in county_heat_protocols() for task in ids):
        base['version']=10
        base['adaptations'].append('County public-health maps: frozen public county aggregates, exact state-qualified joins, disclosed quantitative map or geometric-centroid heatmap; no individual patient locations inferred.')
    if any(task in population_protocols() for task in ids):
        base['version']=11
        base['adaptations'].append('Population-density shares: derive density from original count rasters and ellipsoidal cell areas, retain original grid/masks and independently verify every output cell and final total. These capability cases extend archived refusal references, not claim matching those refusals.')
    return base


def campaign_tasks(campaign):
    campaign = Path(campaign)
    for name in ("frozen.json", "preflight.json"):
        if (campaign / name).exists():
            value = read(campaign / name)
            return tuple(value.get("tasks") or value.get("protocol", {}).get("tasks") or TASK_IDS)
    return TASK_IDS


def campaign_protocol(campaign):
    campaign = Path(campaign)
    for name in ("frozen.json", "preflight.json"):
        if (campaign / name).exists() and (value := read(campaign / name)).get("protocol"):
            return value["protocol"]
    return protocol_for(campaign_tasks(campaign))


def source_terms(directory):
    from .flood_tasks import terms as flood_terms
    from .water_tasks import terms as water_terms
    path = Path(directory) / "source-terms.json"
    if path.exists():
        return read(path)
    base = read(ROOT / "source-terms.json")
    extra = read(ROOT / "source-terms-expansion.json")
    parallel = read(ROOT / "source-terms-parallel.json")
    return {**base, "reviewedAt": parallel["reviewedAt"],
            "assets": {**map_source_terms(), **population_terms(), **base["assets"], **extra["assets"], **parallel["assets"], **remaining_terms(), **water_terms(), **flood_terms(),
                "africa_railways": {"status":"verified", "license":"US public domain (USGS compilation)", "attribution":"Padilla et al., 2021, Compilation of Geospatial Data for the Mineral Industries and Related Infrastructure of Africa, USGS, doi:10.5066/P97EQWXP.", "evidence":["Pinned Data_Sources.bib Africa-minerals-power-railways", "https://doi.org/10.5066/P97EQWXP", "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"], "finding":"Same USGS-authored compiled release as existing authorized Africa mineral/power fixtures; frozen original railway geometry and attributes retained. No imagery or unrelated third-party data included."},
                "na_railways": {"status":"verified", "license":"US public domain", "attribution":"Federal Railroad Administration and Bureau of Transportation Statistics, North American Rail Network. Original pinned GeoBenchX snapshot, unchanged geometry and attributes.", "evidence":["Pinned Data_Sources.bib North American rail source", "https://rosap.ntl.bts.gov/view/dot/53568/dot_53568_DS1.pdf", "https://catalog.data.gov/dataset/north-american-rail-network-lines"], "finding":"Official NARN 1995-present README identifies public-domain data; original archive edition retained, no current network substitution. Reviewed 2026-10-06."},
                "snow_previous": {**base["assets"]["snow"], "attribution": "NOAA/NWS NOHRSC seasonal snowfall, 2023-09-30 to 2024-09-30; original GeoBenchX bytes, NoData recoded by benchmark producer.", "evidence": ["Pinned Data_Sources.bib NOAA-Snow-2025", "https://www.weather.gov/disclaimer"]},
                "seaports":{"status":"verified","license":"US public domain (USGS-produced compilation)","attribution":"Baker et al., USGS Open-File Report 2017-1079, mineral commodity exporting ports of Latin America and the Caribbean.","evidence":["Pinned Data_Sources.bib LA-seaports-from","https://www.usgs.gov/publications/compilation-geospatial-data-mineral-industries-and-related-infrastructure-latin","https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"],"finding":"USGS-authored compiled port dataset; frozen archive port attributes and geometry retained. Third-party imagery or unrelated database layers are not used."},
                "states":{"status":"verified","license":"US public domain","attribution":"US Census Bureau TIGER/Line 2024 state boundaries","evidence":["Pinned archive tl_2024_us_state metadata","https://www.census.gov/about/policies/copyright.html"]},
                "tb_ma":{"status":"verified","license":"Public aggregate factual data; internal research reuse, not a blanket state-document license","attribution":"Massachusetts Department of Public Health, 2023 Tuberculosis Summary Data (2024); pinned GeoBenchX CSV transcription, reviewed 2026-10-06.","evidence":["Pinned Data_Sources.bib MA-TB-2023","https://www.mass.gov/lists/tuberculosis-data-and-statistics","https://www.mass.gov/guides/social-media-legal-guidance-toolkit"],"finding":"County counts and rates only; preserve source footnote and attribution, do not redistribute document design or claim official endorsement. Massachusetts identifies public records and research reuse; this is not permission for unrelated copyrighted material."},
                "tb_ny":{"status":"verified","license":"NYSDOH data-use permission with attribution and unchanged source","attribution":"New York State Department of Health, Tuberculosis Cases and Rates by County 2019–2023, published 2024, reviewed 2026-10-06; frozen GeoBenchX transcription.","evidence":["https://www.health.ny.gov/about/data_use.htm","https://www.health.ny.gov/statistics/diseases/communicable/tuberculosis/docs/2023_cases_rates.pdf","Pinned Data_Sources.bib NYSDOH-TB-2023"],"finding":"Keep frozen source and attribution unchanged; format-only conversion preserves counts, missing-rate markers and summary rows. Derived analyses are separately identified and not endorsed by NYSDOH."},
                **{k:{"status":"verified","license":"CC-BY-4.0","attribution":"Ritchie, Rosado and Roser, Our World in Data, CO2 and Greenhouse Gas Emissions (2023), frozen GeoBenchX wide-table extraction; cite original providers GCP and Jones et al.","evidence":["Pinned Data_Sources.bib owid-co2-and-greenhouse-gas-emissions","https://ourworldindata.org/grapher/co-emissions-per-capita","https://ourworldindata.org/grapher/per-capita-ghg-emissions","https://ourworldindata.org/faqs"],"finding":"OWID-produced harmonized table, numerical observations preserved. No live replacement; retain source attribution and license caveats."} for k in ("co2","ghg")},
                "angola_population": {"status": "verified", "license": "CC-BY-4.0", "attribution": "WorldPop and CIESIN. Angola population counts 2020, UN adjusted, 1 km. DOI 10.5258/SOTON/WP00671.", "evidence": ["Pinned Data_Sources.bib WorldPop-Angola-2020", "https://www.worldpop.org/faq/"], "finding": "Archive citation identifies population counts, not density; CC4.0international, consistent with official WorldPop redistribution terms."}}}
