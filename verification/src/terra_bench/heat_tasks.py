"""Geographic heatmap adaptations: fixed physical grid, not screen-pixel radius."""

GRID = {
    "bounds": [-18000000, -7325000, 18000000, 7325000],
    "crs": "EPSG:6933",
    "resolutionX": 25000,
    "resolutionY": 25000,
}
RADIUS_M = 150000
HEAT_TASKS = {
    "782046": {
        "question": "Make a heatmap final size of fire incidents in USA.",
        "assets": ["fires"], "base": "fires", "allPoints": True,
        "years": [], "weight": "IncidentSi", "weightUnit": "acres",
        "reportingCohort": "reference-aligned-adaptation",
        "literalQuestionSupported": False,
        "meaning": "Explicit reference-aligned adaptation: the released reference uses IncidentSi (reported incident size in acres), while every supplied FinalAcres value is missing. Produce a REPORTED incident-size heatmap, never describe these weights as final burned acreage. This separately reported adaptation cannot answer the literal final-size question. Include all original incident types, including prescribed burns; the original question and reference do not filter types. Preserve each original record and benchmark_row_id. Missing/nonfinite sizes or invalid locations are unknown; genuine zero size remains valid. Use only this frozen historical release, not a current fire feed. The metric grid and Gaussian convention below also replace the reference's zoom-dependent screen-pixel rendering and are explicitly disclosed, not claimed equivalent.",
    },
    "367674": {
        "question": "Make a heatmap showing population concentration in earthquake-affected zones",
        "assets": ["earthquakes", "us_population"], "base": "earthquakes", "raster": "us_population",
        "operator": "gte", "threshold": 0, "weight": "population_at_event", "weightUnit": "people", "years": [],
        "meaning": "Use the released reference's explicit US-raster method, not a global damage assessment: sample the original USA 2020 WorldPop population-count band at each original frozen earthquake point, using its containing original cell with no interpolation or resampling. Eligible points have a finite count at least zero. Include valid zero counts; off-grid, masked or nonfinite samples are unknown, not zero. Weight each eligible event by its sampled people-per-source-cell count. Repeated events can weight the same population repeatedly: this is an event-location population context heatmap, NOT unique affected population, casualty estimates, shaking extent or a claim that all residents experienced damage. The event file is the original 2025-01-16 through 2025-02-15 snapshot; the raster is 2020. This US coverage and the meaning of affected zones are explicit benchmark-derived adaptations of the vague question."},
    "968087": {
        "question": "Generate a heatmap of earthquake occurrences near railway lines in Canada.",
        "assets": ["earthquakes", "na_railways"],
        "base": "earthquakes",
        "years": [],
        "nearLines": "na_railways",
        "lineField": "COUNTRY",
        "lineValue": "CA",
        "distanceCrs": "EPSG:3978",
        "threshold": 10000,
        "meaning": "Select original earthquake points at planar distance strictly less than 10,000 metres from original railway features whose COUNTRY is CA. Transform original vertices to EPSG:3978 (Canada Atlas Lambert); segments are straight in that projection, with no densification. This explicitly fixes the archived reference's unspecified 10 km buffer projection; it is not an exact geodesic or travel-distance measurement. Include points near Canadian rail even if across an international boundary, matching the railway-buffer selection. Use one unit per event to show occurrences, not magnitude weights: the frozen event file contains negative magnitudes, so this is an explicitly disclosed count-weight adaptation of the archived heatmap. Use original January–February 2025 events, not current earthquakes.",
    },
    "621471": {
        "question": "Make a heatmap of seaport density along the Pacific coast of South America",
        "assets": ["seaports"],
        "base": "seaports",
        "directPoints": True,
        "field": "COUNTRY",
        "members": ["Chile", "Peru", "Ecuador", "Colombia"],
        "years": [],
        "meaning": "Use the reference's country-attribute approximation: ports whose COUNTRY is Chile, Peru, Ecuador or Colombia. This includes the full supplied port inventory in those countries, not a measured coastal buffer. Count each port with unit weight; FACID_NUM is an identifier, not port size or density. The source reference uses that identifier as a weight; this protocol explicitly corrects that dimensional error.",
    },
    "605895": {
        "question": "Make a heatmap of seaport density in regions with high freshwater withdrawals in Latin America.",
        "assets": ["seaports", "countries", "water_withdrawal"],
        "base": "seaports",
        "field": "REGION_WB",
        "members": ["Latin America & Caribbean"],
        "indicator": "water_withdrawal",
        "years": ["2021"],
        "operator": "gte",
        "threshold": 90,
        "meaning": "High withdrawals means 2021 ER.H2O.FWTL.ZS at least 90 percent of internal freshwater resources. Select ports within the qualified countries, correcting the archived reference's accidental selection against the unfiltered country variable. Use unit count weights, not the FACID_NUM identifier.",
    },
    "253892": {
        "question": "Create a heatmap of seaport density in regions with high GDP growth in Latin America.",
        "assets": ["seaports", "countries", "gdp"],
        "base": "seaports",
        "field": "SUBREGION",
        "members": ["South America", "Caribbean", "Central America"],
        "derived": "gdp_growth",
        "years": ["2018", "2023"],
        "operator": "gte",
        "threshold": 1.34,
        "meaning": "High growth follows the released reference: 2023 current-USD GDP per capita divided by 2018 GDP per capita at least 1.34. It is nominal GDP-per-capita growth, not inflation-adjusted total GDP growth. Use unit port count weights, not the FACID_NUM identifier.",
    },
    "822439": {
        "question": "Create a heatmap of earthquake occurrences in Pacific US states.",
        "assets": ["earthquakes", "states"],
        "base": "earthquakes",
        "geographyAsset": "states",
        "field": "NAME",
        "members": ["Alaska", "Hawaii", "California", "Oregon", "Washington"],
        "predicate": "intersects",
        "years": [],
        "meaning": "Use original points within or touching the selected original state boundaries, as in the released reference. Use one unit weight per event to show occurrences. The source includes genuine negative magnitudes; the archived reference's magnitude-weighted heatmap is not a nonnegative occurrence density. This protocol explicitly uses counts instead, without dropping small earthquakes or clamping their magnitudes. The event timestamps in the supplied frozen file govern; do not query current events.",
    },
    "112207": {
        "question": "Create a heatmap showing railway station density in areas with high snow accumulation in the USA.",
        "assets": ["stations", "snow"],
        "base": "stations",
        "raster": "snow",
        "operator": "gt",
        "threshold": 39.37,
        "weight": "snow_depth",
        "weightUnit": "inches",
        "years": [],
        "meaning": "Select stations whose containing original raster cell has band-1 snowfall strictly greater than 39.37 inches. NoData and off-grid samples are unknown, not zero; no interpolation or reprojection of the source raster. Retain sampled inches as snow_depth and weight by that field, following the archived reference: this is a snowfall-weighted station heatmap, not an unweighted station count.",
    },
    "565545": {
        "question": "Create a heatmap of earthquakes magnitude in Indonesia, Malaysia and Phillippines",
        "assets": ["earthquakes", "countries"],
        "base": "earthquakes",
        "field": "NAME_EN",
        "members": ["Indonesia", "Malaysia", "Philippines"],
        "weight": "mag",
        "weightUnit": "magnitude",
        "years": [],
    },
    "921361": {
        "question": "Create a heatmap of earthquakes in South Asia.",
        "assets": ["earthquakes", "countries"],
        "base": "earthquakes",
        "field": "SUBREGION",
        "members": ["Southern Asia"],
        "weight": "mag",
        "weightUnit": "magnitude",
        "years": [],
    },
    "217200": {
        "question": "Create a heatmap of mineral facility density in African countries with large labor forces",
        "assets": ["facilities", "countries", "labor"],
        "base": "facilities",
        "indicator": "labor",
        "years": ["2023"],
        "operator": "gt",
        "threshold": 5764399,
        "meaning": "Large labor force means strictly more than 5,764,399 people in WDI SL.TLF.TOTL 2023. Use one unit weight per facility, not DsgAttr07 (a commodity descriptor, not a count).",
    },
    "486122": {
        "question": "Generate a heatmap of mineral extraction facilities in regions with high water withdrawals in Africa. ",
        "assets": ["facilities", "countries", "water_volume"],
        "base": "facilities",
        "indicator": "water_volume",
        "years": ["2021"],
        "operator": "gte",
        "threshold": 18.29,
        "meaning": "High withdrawals means at least 18.29 billion cubic metres per year, WDI ER.H2O.FWTL.K3 2021. Use one unit weight per facility, not the commodity descriptor DsgAttr07.",
    },
    "435973": {
        "question": "Generate a heatmap of power station density in regions with water scarcity",
        "assets": ["power_stations", "countries", "water_withdrawal"],
        "base": "power_stations",
        "indicator": "water_withdrawal",
        "years": ["2021"],
        "operator": "gte",
        "threshold": 100,
        "weight": "DsgAttr02",
        "weightUnit": "MW",
        "meaning": "Scarcity is the benchmark proxy of WDI ER.H2O.FWTL.ZS 2021 withdrawals at least 100% of internal freshwater resources. Weight stations by DsgAttr02 MW, a capacity-weighted heatmap, not a count or proof of current generation.",
    },
    "911650": {
        "question": "Generate a heatmap of power station density in African regions with high rural population",
        "assets": ["power_stations", "countries", "rural", "population"],
        "base": "power_stations",
        "derived": "rural_share",
        "years": ["2023"],
        "operator": "gt",
        "threshold": 0.5,
        "weight": "DsgAttr02",
        "weightUnit": "MW",
        "meaning": "High rural population means 2023 rural population divided by total population strictly greater than 0.5, using WDI SP.RUR.TOTL and SP.POP.TOTL. Weight points by DsgAttr02 MW; this is capacity-weighted, not a station count surface.",
    },
    "470604": {
        "question": "Make a heatmap of power station density in regions with high forest depletion",
        "assets": ["power_stations", "countries", "forest_percent"],
        "base": "power_stations",
        "derived": "forest_change",
        "years": ["1990", "2021"],
        "operator": "lt",
        "threshold": 0,
        "weight": "DsgAttr02",
        "weightUnit": "MW",
        "meaning": "Forest depletion follows the released reference: WDI AG.LND.FRST.ZS 2021 less than 1990, any decline in forest percentage. Weight points by DsgAttr02 MW. It is not a causal relationship or a measured local forest-loss surface.",
    },
    "133682": {
        "question": "Create a heatmap of earthquake occurrences in regions with high population growth.",
        "assets": ["earthquakes", "countries", "population"],
        "base": "earthquakes",
        "derived": "population_growth",
        "years": ["2010", "2023"],
        "operator": "gte",
        "threshold": 0.23,
        "globalCountries": True,
        "weight": "mag",
        "weightUnit": "magnitude",
        "meaning": "High growth means (2023 population minus 2010 population) divided by 2010 population at least 0.23, using WDI SP.POP.TOTL. Use magnitude weights from the frozen event file, not inferred earthquake energy.",
    },
}


def heat_protocols():
    import json

    result = {}
    for task, s in HEAT_TASKS.items():
        geography = s.get("geographyAsset", "countries")
        scope = (
            "Use all original point records in the supplied historical incident file; do not impose a new geographic or incident-type filter. "
            if s.get("allPoints")
            else
            "Use the original point and line fixtures with the following precise near-rail convention. "
            if s.get("nearLines")
            else f"Use supplied {'point records' if s.get('directPoints') else geography} with {s['field']} in {json.dumps(s['members'])}. "
            if s.get("field")
            else "Use the frozen raster to select source points. "
            if s.get("raster")
            else "Use all supplied countries. "
            if s.get("globalCountries")
            else "Use supplied countries with CONTINENT=Africa. "
        )
        unit = f"sum of {s['weightUnit']} per grid cell" if s.get("weight") else "events per grid cell"
        result[task] = {
            "title": s["question"].strip().rstrip("."),
            "question": s["question"],
            "family": "geographic-heatmap",
            "bbox": [-180, -85, 180, 85],
            "clarification": scope
            + s.get(
                "meaning",
                f"Weight the selected earthquake points by {s.get('weight', 'one unit')}; magnitude is not energy.",
            )
            + " "
            + (
                "Use original point records and the declared attribute/raster selection; do not infer a separate geographic boundary. "
                if s.get("directPoints") or s.get("raster") or s.get("nearLines") or s.get("allPoints")
                else "Use original point records within or touching the original selected state polygons. "
                if s.get("predicate") == "intersects"
                else "Use original point records strictly within the original selected country polygons; no clipped polygons, location guesses or current data. "
            )
            + (
                "Join country ISO_A3 to the supplied indicator table's Country Code exactly. "
                if s.get("indicator") or s.get("derived")
                else ""
            )
            + "Unknown country indicators, nonpositive ratio denominators, missing geometry and missing/nonfinite weights are unknown, not zero. Known zero weights remain valid. "
            "Exclude valid points outside the specified geography. Include only eligible points with a finite nonnegative weight in the contributing artifact; report other potentially eligible points as unknown. "
            f"Use this explicit geographic heatmap convention: grid={json.dumps(GRID)}, radius {RADIUS_M} metres = three Gaussian standard deviations. "
            "First bin each point into its containing grid cell and sum its weight. Smooth using a normalized separable Gaussian, numerical support four standard deviations, constant-zero exterior; do not renormalize edges. "
            "Use both grid resolutions for the two axes; keep original grid alignment. This is a declared metric raster adaptation to the original interactive screen-pixel heatmap, not an equivalent zoom-dependent rendering. "
            f"Output unit: {unit}. Zero cells are valid; this is not density per square kilometre. Do not rescale the values for presentation.",
            "outputContract": "Add the heatmap raster to the map and retain an inspectable selected-point artifact with original geometry and benchmark_row_id. "
            "End with one fenced JSON object: {count: contributing point records, unknown_count: records with unknown eligibility or weight, unlocated_count: original points lacking valid geometry, "
            "coverage_note: string, selection: {collectionId,itemId,assetKey}, density: {collectionId,itemId,assetKey}, map_layer_id: heatmap_layer_id}. "
            "Explain the data edition, numerical weights, grid, smoothing and coverage limitations. The source-point artifact is not itself the requested heatmap.",
        }
        if s.get("reportingCohort"):
            result[task].update(reportingCohort=s["reportingCohort"],
                                literalQuestionSupported=s["literalQuestionSupported"])
            result[task]["outputContract"] += (
                ' Include measurement: "reported_incident_size" and final_acreage_available: false '
                'in the final JSON, and clearly explain that final acreage is unavailable.'
            )
    return result
