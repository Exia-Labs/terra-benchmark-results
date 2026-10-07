"""Remaining original questions, explicit historical conventions, no oracle hints."""

COUNTY_FIRE_TASK = "955741"


def remaining_protocols():
    result = {"365343": {
        "title": "River records intersecting highly forested South American countries",
        "question": "How many rivers flow through areas with significant forest coverage in South America?",
        "family": "forest-river-intersection", "bbox": [-92, -56, -34, 15],
        "clarification": "Use the released reference's country-level definition: South American countries (CONTINENT='South America') with World Bank 2021 forest area strictly greater than 50 percent of land area. Join original ISO_A3 to Country Code, not fuzzy names. Count distinct original FAO river records intersecting those polygons, including boundary touches. A record can meet several countries but counts once; these are river segments, not unique named whole rivers. National forest percentage is NOT a map of actual forest along a river. Keep unknown/missing indicator countries explicit; unknown_count is the number of river records that intersect an unknown eligible country and no qualifying known country, plus invalid/missing river geometries. Use the original frozen data, no live substitution. This is internal research; FAO-derived outputs are not cleared for promotional publication.",
        "outputContract": "Return the original selected river features with benchmark_row_id, attributes and unchanged geometry. Map optional. Finish with fenced JSON {count:integer,unknown_count:integer,coverage_note:string,selection:{collectionId,itemId,assetKey}}. Explain the country-level proxy, 2021 year and segment-count unit.",
    }, COUNTY_FIRE_TASK: {
        "title": "Counties shared by historical earthquake and wildfire snapshots",
        "question": "Which US counties experiencing earthquakes in the last 30 days also have active wildfires?",
        "family": "county-event-intersection", "bbox": [-180, 18, 180, 72],
        "clarification": "Use the original county polygons, supplied earthquake snapshot (observed dates 2025-01-16 through 2025-02-15), and the archived NIFC current-incident feed (latest ModifiedOn 2024-02-27). Last 30 days and active mean those supplied snapshots, not today. These files are NOT contemporaneous: the result identifies counties represented in BOTH snapshots, not evidence of simultaneous hazards. NIFC's feed excludes contained, controlled, out and certified incidents. Select IncidentTy=WF, excluding RX prescribed burns. A county qualifies if its original polygon intersects at least one earthquake AND at least one selected wildfire point; boundary-touching qualifies. Count each original county once despite multiple events. Keep all county attributes and original geometry. Missing/invalid event geometry cannot establish absence; disclose source coverage and dates.",
        "outputContract": "List qualifying county names with state/GEOID and publish an inspectable county selection preserving benchmark_row_id. A map is optional. End with one fenced JSON object: {count:integer,unknown_count:number of original events with missing or invalid geometry,coverage_note:string,selection:{collectionId,itemId,assetKey}}. Explicitly state that the two snapshots differ in year and do not prove concurrent earthquake/fire conditions.",
    }}
    result[COUNTY_FIRE_TASK]["clarification"] += " Select earthquake records with type='earthquake'; the source also contains quarry blasts, explosions and ice quakes, which are not the requested earthquake events."
    return result


def forest_river_answer(rivers, countries, forest):
    import geopandas as gpd
    import pandas as pd

    from .common import Blocked
    from .fixtures import ROW_ID
    if forest["Country Code"].duplicated().any():
        raise Blocked("Forest indicator has duplicate country codes")
    mapping = pd.to_numeric(forest.set_index("Country Code")["2021"], errors="raise")
    region = countries.loc[countries.CONTINENT == "South America"].copy()
    values = region.ISO_A3.map(mapping)
    valid = rivers.geometry.notna() & ~rivers.geometry.is_empty & rivers.geometry.is_valid
    located = rivers.loc[valid].to_crs(countries.crs)
    def matches(frame):
        if frame.empty:
            return set()
        found = set(gpd.sjoin(located[[ROW_ID, "geometry"]], frame[["geometry"]], predicate="intersects")[ROW_ID])
        direct = set(located.loc[located.intersects(frame.geometry.union_all()), ROW_ID])
        if found != direct:
            raise Blocked("Forest-river oracle independent predicate check disagrees")
        return found
    selected = matches(region.loc[values > 50])
    unknown = matches(region.loc[values.isna()]) - selected
    unknown.update(rivers.loc[~valid, ROW_ID])
    return {"family": "forest-river-intersection", "count": len(selected), "ids": sorted(selected), "unknownIds": sorted(unknown), "identityField": ROW_ID}


def county_fire_answer(counties, earthquakes, fires):
    import geopandas as gpd

    from .common import Blocked
    from .fixtures import ROW_ID

    fires = fires.loc[fires.IncidentTy == "WF"].copy()
    if "type" in earthquakes:
        earthquakes = earthquakes.loc[earthquakes["type"] == "earthquake"].copy()
    sets, unknown = [], []
    for events in (earthquakes, fires):
        valid = events.geometry.notna() & ~events.geometry.is_empty & events.geometry.is_valid
        unknown.extend(events.loc[~valid, ROW_ID].tolist())
        located = events.loc[valid].to_crs(counties.crs)
        matched = set(gpd.sjoin(counties[[ROW_ID, "geometry"]], located[["geometry"]], predicate="intersects")[ROW_ID])
        direct = set(counties.loc[counties.intersects(located.geometry.union_all()), ROW_ID])
        if matched != direct:
            raise Blocked("County event intersection oracle cross-check differs.")
        sets.append(matched)
    ids = sorted(sets[0] & sets[1])
    return {"family": "county-event-intersection", "ids": ids, "count": len(ids),
            "unknownIds": sorted(unknown), "identityField": ROW_ID,
            "answerConcepts": [["2024"], ["2025"], ["not contemporaneous", "not simultaneous", "different", "differ", "non-contemporaneous", "do not prove concurrent", "not evidence of simultaneous"]]}


def remaining_terms():
    return {
        'peru_provinces': {
            'status':'verified', 'license':'CC-BY-IGO-3.0', 'attribution':'Peru IGN / OCHA COD-AB, ADM2 provinces, frozen 2020-07-14 edition.',
            'evidence':['https://data.humdata.org/api/3/action/package_show?id=cod-ab-per'],
            'finding':'Official package declares CC BY IGO; identifies 196 ADM2 provinces and July 2020 release. Retain original frozen geometry, not current source.'},
        "sa_rivers": {
            "status": "verified", "license": "FAO research reuse / CC-BY-4.0 default plus HydroSHEDS data licence; local non-promotional evaluation only",
            "attribution": "FAO AQUAmaps, regional rivers_samerica_37330 derived from WWF HydroSHEDS. Lehner, Verdin and Jarvis (2008). Original GeoBenchX edition retained.",
            "evidence": ["https://www.fao.org/contact-us/terms/db-terms-of-use/en/", "https://www.fao.org/fishery/static/geonetwork/b891ca64-4cd4-4efd-a7ca-b386e98d52e8/data/Aquamaps-River_Data_description.pdf", "https://www.hydrosheds.org/products/hydrosheds"],
            "finding": "Exact regional dataset 37330 identified by producer documentation. FAO encourages research/statistical use; underlying HydroSHEDS permits scientific and commercial use. Keep FAO/HydroSHEDS attribution. FAO additional terms prohibit commercial promotion. This campaign is internal evaluation; its FAO-derived outputs/graphics are not cleared for product marketing or source redistribution.",
            "sharingRestriction": "Internal research only; do not use these results or maps to promote Terra without separate clearance.",
        },
        "brazil_municipalities": {
            "status": "verified", "license": "CC-BY-IGO-3.0", "attribution": "IBGE / OCHA COD-AB Brazil, 2020 municipal boundaries.",
            "evidence": ["https://data.humdata.org/api/3/action/package_show?id=cod-ab-bra"],
            "finding": "Official OCHA package declares CC BY IGO 3.0 and IBGE authorship; use original 2020 frozen file, not refreshed current geometry.",
        },
        "brazil_railways": {
            "status": "verified", "license": "ODC-ODbL-1.0", "attribution": "OpenStreetMap contributors / HOTOSM, frozen Brazil railway extract.",
            "evidence": ["https://data.humdata.org/api/3/action/package_show?id=hotosm_bra_railways", "https://www.openstreetmap.org/copyright"],
            "finding": "Official HOTOSM package declares Open Database License. Preserve frozen source and attribution; no source database is redistributed.",
        },
        "brazil_population": {
            "status": "verified", "license": "CC-BY-4.0", "attribution": "WorldPop / CIESIN, Brazil 2018 UN-adjusted population counts aggregated to 1 km cells.",
            "evidence": ["https://www.worldpop.org/faq/", "Pinned Data_Sources.bib"],
            "finding": "Original WorldPop count raster retained. Values are people per cell; density must be calculated, not relabeled.",
        },
        "fires": {
            "status": "verified", "license": "Public federal interagency data; source usage disclaimer retained",
            "attribution": "NIFC/WFIGS, US DOI Office of Wildland Fire IRWIN and participating agencies. Frozen GeoBenchX incident snapshot, latest record update 2024-02-27, not current live observations.",
            "evidence": ["https://www.arcgis.com/sharing/rest/content/items/4181a117dc9e43db8598533e29972015?f=json",
                         "https://nationaldataplatform.org/catalog/dataset/current-wildland-fire-incident-locations",
                         "https://www.nifc.gov/fire-information/maps"],
            "finding": "Official source item publishes federal interagency incident data with accuracy/use disclaimers, no noncommercial restriction. Keep attribution, no endorsement/current-status claim, preserve original bytes. Feed semantics and exported fields checked; FinalAcres is entirely missing, so IncidentSi cannot be claimed as final size.",
        },
    }
