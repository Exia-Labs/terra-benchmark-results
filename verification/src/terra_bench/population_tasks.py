"""Population-count questions with explicitly derived, not fabricated, density."""

POPULATION_TASKS = {
    "618282": {
        "question": "How many people live within 1 km from a railway in Bangladesh",
        "raster": "bangladesh_density",
        "country": "Bangladesh",
        "bbox": [88, 20, 93, 27],
        "points": "bangladesh_railways",
        "threshold": 1000,
        "operator": "lte",
        "year": "2018",
        "sourceQuantity": "density",
        "method": "projected-features",
        "distanceCrs": "EPSG:32646",
    },
    "673274": {
        "question": "What percentage of Bangladesh's population lives within 5 km of a railway line?",
        "raster": "bangladesh_density",
        "country": "Bangladesh",
        "bbox": [88, 20, 93, 27],
        "points": "bangladesh_railways",
        "threshold": 5000,
        "operator": "lte",
        "year": "2018",
        "sourceQuantity": "density",
        "method": "projected-features",
        "distanceCrs": "EPSG:32646",
    },
    "208110": {
        "question": "Compare the population density along railways in Bangladesh with the national average",
        "raster": "bangladesh_density",
        "country": "Bangladesh",
        "bbox": [88, 20, 93, 27],
        "points": "bangladesh_railways",
        "threshold": 5000,
        "operator": "lte",
        "year": "2018",
        "sourceQuantity": "density",
        "method": "projected-features",
        "distanceCrs": "EPSG:32646",
        "compareDensity": True,
    },
    "785163": {
        "question": "Calculate the percentage of Angola's population living within 20km of mineral extraction facilities",
        "raster": "angola_population",
        "country": "Angola",
        "bbox": [11, -19, 25, -4],
        "points": "facilities",
        "countryField": "Country",
        "threshold": 20000,
        "operator": "lte",
        "year": "2020",
    },
    "197777": {
        "question": "Calculate the percentage of Peru's population living more than 100km from seaports",
        "raster": "peru_population",
        "country": "Peru",
        "bbox": [-83, -19, -68, 1],
        "points": "seaports",
        "countryField": "COUNTRY",
        "threshold": 100000,
        "operator": "gt",
        "year": "2018",
    },
    "551060": {
        "question": "Calculate the percentage of Angola's population living in areas with density above 1000 people per square kilometer",
        "raster": "angola_population",
        "country": "Angola",
        "bbox": [11, -19, 25, -4],
    },
    "819657": {
        "question": "What percentage of Chile's population lives in areas with population density over 1000 people per square km?",
        "raster": "chile_population",
        "country": "Chile",
        "bbox": [-110, -57, -65, -17],
    },
}


def population_protocols():
    result = {
        task: {
            "question": spec["question"],
            "title": spec["question"],
            "family": "population-density-share",
            "bbox": spec["bbox"],
            "clarification": "Use the frozen WorldPop 2020 UN-adjusted population-count raster, band 1, not current data. Its values are people PER CELL, not people/km². "
            "Define density as each original valid cell count divided by that geographic cell’s full WGS84 ellipsoidal area in km² (meridian/parallel cell edges). Do not use a constant 1 km² approximation or resample counts. "
            "Strict density >1000 qualifies; sum the original counts in qualifying cells and divide by the sum of original counts over all valid cells, then multiply by 100. "
            "The denominator is the supplied raster’s valid country coverage, not an invented census total. Genuine zeros remain zero; NoData is unknown, not zero. "
            "Return a full-grid selected-population raster: original population for qualifying cells, zero for other valid cells, and the original missing-data mask. Also retain the density raster with the same grid and mask.",
            "outputContract": "Compute the percentage and publish the two inspectable rasters. A map is optional. End with one fenced JSON object: "
            "{count: qualifying cell count, unknown_count: original masked/nonfinite cell count, coverage_note, "
            "selection:{collectionId,itemId,assetKey} for selected-population counts, density:{collectionId,itemId,assetKey}, "
            "metrics:{selected_people: number, total_people: number, percentage: number}}. Report original year and the valid-raster coverage limitation. "
            "Do not round the machine-readable metrics to whole people or whole percentages.",
        }
        for task, spec in POPULATION_TASKS.items()
    }
    for task, spec in POPULATION_TASKS.items():
        if not spec.get("points"):
            continue
        relationship = "at most" if spec["operator"] == "lte" else "strictly more than"
        result[task]["family"] = "population-distance-share"
        result[task]["clarification"] = (
            f"Use the frozen WorldPop {spec['year']} UN-adjusted population-count raster, original band 1 and grid; values are people per cell. "
            f"Use the supplied {spec['points']} records with {spec.get('countryField', 'country')} exactly {spec['country']!r}. Do not invent missing facilities or include another country. "
            f"A valid population cell qualifies when its centre is {relationship} {spec['threshold']} metres from its nearest selected original Point, using shortest WGS84 ellipsoid surface distance. "
            "This frozen centre-distance convention avoids overlapping-buffer double counts and projected-map scale ambiguity. It is not road travel distance or within-cell population positioning. "
            "Sum original counts in qualifying cells, divide by all original valid country-raster counts and multiply by 100. No resampling, constant-cell-area conversion or invented census denominator. "
            "Zero population stays valid; NoData is unknown. Count each cell once. The result describes the supplied facility inventory and raster coverage, not proof that every facility is recorded. "
            "Retain the full-grid distance raster and selected-population raster (original count when eligible, zero otherwise, original missing-data mask)."
        )
        result[task]["outputContract"] = (
            "Compute the percentage and publish both inspectable rasters. A map is optional. End with a fenced JSON object: "
            "{count: qualifying cell count, unknown_count: original masked/nonfinite cell count, coverage_note, selection:{collectionId,itemId,assetKey}, "
            "distance:{collectionId,itemId,assetKey}, metrics:{selected_people:number,total_people:number,percentage:number}}. "
            "Label selected population as people per cell and distance as metres. Report the historical year and coverage limitations. Do not round machine-readable metrics to integers."
        )
        if spec.get("method") == "projected-features":
            result[task]["clarification"] = (
                "Use the frozen Bangladesh WorldPop 2018 bgd_pd_2018_1km_UNadj raster. Its verified units are people/km², NOT people per cell; preserve its original band, grid and missing mask. "
                "Convert density to population per cell using each original full WGS84 ellipsoidal meridian/parallel cell area in km², not a constant nominal 1 km². "
                "Use all original features in the supplied Bangladesh railway line inventory; no live railway substitutions, attribute exclusions or duplicated population from overlapping corridors. "
                f"Define proximity by shortest planar distance from each original raster cell centre to the original railway geometries transformed into EPSG:32646 (UTM zone 46N), with original straight segments. A cell qualifies at distance <= {spec['threshold']} metres. "
                "This is an explicit local projected cell-centre approximation, not travel distance or exact ellipsoidal distance. Projection distortion and unresolved within-cell population location remain limitations. "
                "The corridor includes the full cell when its centre qualifies, counting each cell once. Zero density is valid; missing/nonfinite cells remain unknown. "
                "Total and selected population are sums of density times physical cell area over valid cells; percentage is 100 times selected/total. "
                "Publish a selected-population raster (derived people per cell when qualifying, zero in other valid cells, original mask) and a distance raster in metres on that same original grid. "
                "The historical population and later railway snapshot do not prove contemporaneous access or census accuracy."
            )
            if spec.get("compareDensity"):
                result[task]["clarification"] += (
                    "Along railways means the declared 5 km corridor. Compare area-weighted density: selected people divided by total area of qualifying valid cells versus total people divided by area of all valid cells. Do not average cell densities without area weighting or treat NoData as zero."
                )
                result[task]["outputContract"] += (
                    " Also include metrics corridor_density and national_density in people/km², plus selected_area_km2 and total_area_km2. Explain which density is greater."
                )
    return result


def population_assets():
    return {
        "us_population": {
            "file": "usa_ppp_2020_1km_Aggregated_UNadj.tif",
            "kind": "raster",
            "title": "USA population count, WorldPop 2020",
            "edition": "2020 UN-adjusted population counts aggregated to 1 km cells",
            "units": {"band1": "people per cell"},
        },
        "bangladesh_density": {
            "file": "bgd_pd_2018_1km_UNadj.tif",
            "kind": "raster",
            "title": "Bangladesh population density, WorldPop 2018",
            "edition": "2018 UN-adjusted 1 km density; exact bytes verified against WorldPop product 45189, DOI WP00675",
            "units": {"band1": "people/km²"},
        },
        "bangladesh_railways": {
            "file": "Bangladesh_gis_osm_railways_free_1.shp",
            "kind": "vector",
            "title": "Bangladesh railway lines, frozen OpenStreetMap extract",
            "edition": "GeoBenchX Geofabrik Bangladesh extract, 2025-02-01; ODbL attribution required",
        },
        "peru_population": {
            "file": "per_ppp_2018_1km_Aggregated_UNadj.tif",
            "kind": "raster",
            "title": "Peru population count, WorldPop 2018",
            "edition": "2018 UN-adjusted population counts, aggregated to 1 km cells",
            "units": {"band1": "people per cell"},
        },
        "chile_population": {
            "file": "chl_ppp_2020_1km_Aggregated_UNadj.tif",
            "kind": "raster",
            "title": "Chile population count, WorldPop 2020",
            "edition": "2020 UN-adjusted population counts aggregated to 1 km cells",
            "units": {"band1": "people per cell"},
        },
    }


def population_terms():
    return {
        "us_population": {
            "status": "verified",
            "license": "CC-BY-4.0",
            "attribution": "WorldPop and CIESIN. USA population counts 2020, UN adjusted, 1 km. DOI 10.5258/SOTON/WP00671.",
            "evidence": ["Pinned Data_Sources.bib WorldPop-USA-2020", "https://www.worldpop.org/faq/"],
            "finding": "Original archived population-count file retained with WorldPop attribution. Values are counts per original cell, not density, unique affected people or casualty estimates.",
        },
        "bangladesh_density": {
            "status": "verified",
            "license": "CC-BY-4.0",
            "attribution": "WorldPop and CIESIN 2018. DOI 10.5258/SOTON/WP00675.",
            "evidence": ["https://hub.worldpop.org/geodata/summary?id=45189"],
            "finding": "Producer explicitly documents people per square kilometre. Downloaded product matches all 850416 frozen bytes, SHA256 c7eede1eb6bbf27e203de10c49c01155c1841a2011079e4c47fef332dfc167a4. The archive bibliography mislabels counts; verified product metadata governs. No values substituted.",
        },
        "bangladesh_railways": {
            "status": "verified",
            "license": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors; Geofabrik Bangladesh extract, 2025-02-01.",
            "evidence": [
                "Pinned Data_Sources.bib",
                "https://download.geofabrik.de/asia/bangladesh.html",
                "https://www.openstreetmap.org/copyright",
            ],
            "finding": "Original OSM-derived railway geometry is retained, attributed and remains under ODbL. Public redistribution of derived databases must preserve applicable share-alike terms.",
        },
        "peru_population": {
            "status": "verified",
            "license": "CC-BY-4.0",
            "attribution": "WorldPop and CIESIN. Peru population counts 2018, UN adjusted, 1 km. DOI 10.5258/SOTON/WP00671.",
            "evidence": ["Pinned Data_Sources.bib WorldPop-Peru-2018", "https://www.worldpop.org/faq/"],
            "finding": "Original archived population-count raster retained; official reuse terms verified with attribution.",
        },
        "chile_population": {
            "status": "verified",
            "license": "CC-BY-4.0",
            "attribution": "WorldPop and CIESIN. Chile population counts 2020, UN adjusted, 1 km. DOI 10.5258/SOTON/WP00671.",
            "evidence": ["Pinned Data_Sources.bib WorldPop-Chile-2020", "https://www.worldpop.org/faq/"],
            "finding": "Original archived population-count file retained; official WorldPop attribution/reuse terms checked 2026-10-06. Density is a derived result, never advertised as an original field.",
        },
    }
