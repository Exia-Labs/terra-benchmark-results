"""Contour tasks: explicit source, levels and geometry conventions, never answers."""

NORTHERN_STATES = ["ME", "NH", "VT", "NY", "MA", "CT", "RI", "PA", "MI", "WI", "MN", "ND", "MT", "WA"]
CONTOUR_TASKS = {
    "480358": {"question": "Make contour lines of population density in flood-affected areas of Bangladesh.", "raster": "bangladesh_density", "levels": [100, 500, 1000, 5000, 10000], "unit": "people/km2", "bbox": [88, 20, 93, 27], "floodMask": "flood_bangladesh"},
    "131687": {"question": "Generate contour lines of snow accumulation near major US lakes",
               "raster": "snow", "levels": [5, 10, 20, 40, 80, 160, 320], "unit": "inches", "bbox": [-125, 24, -66, 50],
               "overlay": "na_lakes", "overlaySelector": {"geography": "countries", "field": "NAME_EN", "value": "United States", "predicate": "intersects"}},
    "996706": {"question": "Create contour lines of snow accumulation near major water bodies",
               "raster": "snow", "levels": [5, 10, 20, 40, 80, 160, 320], "unit": "inches", "bbox": [-125, 24, -66, 50],
               "overlay": "na_lakes", "contexts": ["na_rivers"]},
    "620811": {"question":"Create contour lines of population density along major rivers in Brazil",
               "raster":"brazil_population", "levels":[500,1000,2000,5000,10000], "unit":"people/km2", "bbox":[-75,-35,-28,6],
               "overlay":"sa_rivers", "deriveDensity":True, "year":"2018",
               "overlaySelector":{"geography":"countries", "field":"NAME_EN", "value":"Brazil", "predicate":"intersects"}},
    "655059": {"question": "Generate contour lines from Peru's population data and overlap with provincial borders and rivers in the country.",
               "raster": "peru_population", "levels": [100, 500, 1000, 5000, 10000], "unit": "people per cell", "bbox": [-83, -19, -68, 1],
               "overlay": "sa_rivers", "contexts": ["peru_provinces"],
               "overlaySelector": {"geography": "peru_provinces", "predicate": "within"}},
    "763412": {"question": "Create contour lines from Chile's population density data in relation to rivers",
               "raster": "chile_population", "levels": [50, 100, 200, 400, 800], "unit": "people/km2", "bbox": [-110, -57, -65, -17],
               "overlay": "sa_rivers", "deriveDensity": True,
               "overlaySelector": {"geography": "countries", "field": "NAME_EN", "value": "Chile", "predicate": "intersects"}},
    "118857": {"question": "Chart contour lines for accumulated snow fall in winter 2023-2024 in USA",
               "raster": "snow_previous", "levels": [20, 40, 80, 160, 320, 640], "unit": "inches", "bbox": [-125, 24, -66, 50]},
    "251255": {"question": "Make contour lines of snow accumulation for areas with railway stations in the USA",
               "raster": "snow", "levels": [5, 10, 20, 40, 80, 160, 320], "unit": "inches", "bbox": [-125, 24, -66, 50],
               "overlay": "stations"},
    "554817": {"question": "Generate contour lines from snow cover data for 2023-2024 season and compare with railway stations locations in the northern states",
               "raster": "snow_previous", "levels": [5, 10, 20, 40, 80, 160, 320], "unit": "inches", "bbox": [-125, 24, -66, 50],
               "overlay": "stations", "filter": {"State": NORTHERN_STATES}},
    "291123": {"question": "Create contour lines from Angola's population data in relation to power stations",
               "raster": "angola_population", "levels": [50, 100, 200, 400, 600], "unit": "people per cell", "bbox": [11, -19, 25, -4],
               "overlay": "power_stations", "filter": {"Country": ["Angola"]}},
}


def contour_protocols():
    import json
    result = {}
    for task, spec in CONTOUR_TASKS.items():
        clarification = (f"Use band 1 of the frozen {spec['raster']} raster at the original grid without resampling, smoothing or clipping. "
            f"Draw the explicit contour levels {spec['levels']} in {spec['unit']}. These levels are a disclosed evaluation convention, not a requested interval. "
            "Use piecewise-linear marching-squares isolines through pixel-center values, low-valued connectivity at ambiguous saddles. "
            "Respect the native mask, NoData and nonfinite cells; do not bridge holes or extrapolate at the outside edge. "
            "Apply any source scale and offset. NoData means unknown, never zero. Preserve source coverage; levels outside the observed range may have no line. "
            "Do not substitute a current raster. Count nonempty requested contour LEVELS, not polyline fragments. "
            "The population-count raster, where supplied, is people per original cell; do not label it population density. ")
        if spec.get("overlay"):
            clarification += f"Overlay the supplied {spec['overlay']} original geometries on the same map. "
            if spec.get('overlaySelector'):
                sel = spec['overlaySelector']
                selection = f" selected by {sel['field']}={sel['value']!r}" if sel.get('field') else ''
                clarification += f"Retain original overlay features matching predicate {sel['predicate']} against each original {sel['geography']} polygon{selection}; duplicated matches count once. Do not clip the line geometries. "
                if sel['predicate'] == 'within':
                    clarification += 'Do not dissolve the province polygons: within an individual province differs from within their union. '
                else:
                    clarification += 'A dissolved union of the selected country polygons is equivalent for intersects. '
            elif spec.get("filter"):
                clarification += f"Retain exactly the point rows matching {json.dumps(spec['filter'])}. "
            else:
                clarification += "Retain every original overlay row, including those outside the raster; disclose their lack of raster coverage. "
            clarification += "This is a visual spatial comparison; no invented causal correlation or extra buffer is requested. "
        result[task] = {"title": spec["question"], "question": spec["question"], "bbox": spec["bbox"], "family": "contour-map",
            "clarification": clarification,
            "outputContract": "Deliver an inspectable vector contour artifact and add it to the map with a level/units legend. "
                "End with one fenced JSON object containing: count (number of nonempty requested levels), unknown_count (number of masked or nonfinite source pixels), "
                "coverage_note, selection: {collectionId,itemId,assetKey}, level_field, feature_count (actual contour feature rows), map_layer_id. "
                + ("Also include overlay: {selection: {collectionId,itemId,assetKey}, map_layer_id, count}, retaining original benchmark_row_id. " if spec.get("overlay") else "")
                + "Explain the source season/year, units, missing coverage, and visual relationship where an overlay is requested."}
        if spec.get("floodMask"):
            from .flood_tasks import protocols as flood_protocols
            result[task]["clarification"] = flood_protocols()[task]["clarification"] + " For this contour question retain original population-density values only at observed flooded cell centres; observed dry cells, permanent water and unknown coverage must all be NoData, not zero. Then " + clarification.replace("The population-count raster, where supplied, is people per original cell; do not label it population density. ", "The supplied Bangladesh raster is verified people/km2, not counts; do not divide it by area again. ")
        if spec.get('deriveDensity'):
            result[task]['clarification'] = (
                f"First derive people/km2 from original WorldPop {spec.get('year', '2020')} people-per-cell counts by dividing each valid count by its original full WGS84 ellipsoidal meridian/parallel cell area in km2; apply scale/offset, preserve zeros, grid and NoData. "
                + clarification.replace("The population-count raster, where supplied, is people per original cell; do not label it population density. ", "Contour the derived density, NOT the original counts. ")
                + "This is a visual comparison, not an estimate of population specifically living near rivers. FAO-derived outputs are internal research only, not promotional publication.")
        if spec.get('contexts'):
            if task == '655059':
                result[task]['clarification'] += " Also add all original Peru ADM2 province polygons as a separate visible boundary layer, not ADM1 regions. Values are 2018 people per original cell; this question does not request conversion to density. FAO-derived outputs are internal research only, not promotional publication."
            else:
                result[task]['clarification'] += " Also add all original features from these context assets as separate map layers: " + ', '.join(spec['contexts']) + '. '
            result[task]['outputContract'] += " Include context_layers: [{name:asset_name, selection:{collectionId,itemId,assetKey}, map_layer_id, count}] in the same final JSON."
        if task in {'131687', '996706'}:
            result[task]['clarification'] += " As in the released reference, near means visual comparison on the same map, not an invented proximity buffer. Major water bodies means the supplied CEC inventory, not an added size threshold. The seven explicit levels replace the reference's dense five-inch interval as a disclosed presentation convention. Keep the actual 2024-09-30 to 2025-05-20 season, not the reference's stale February plot title. Water data and derived maps are for this benchmark only."
    return result


def contour_assets():
    return {
        'brazil_population': {'file':'bra_ppp_2018_1km_Aggregated_UNadj.tif', 'kind':'raster',
                             'title':'Brazil population count, WorldPop 2018', 'edition':'2018 UN-adjusted population counts, 1 km aggregate', 'units':{'band1':'people per cell'}},
        "snow_previous": {"file": "sfav2_CONUS_2023093012_to_2024093012_processed.tif", "kind": "raster",
            "title": "US snowfall, 2023–24 frozen season", "edition": "2023-09-30 to 2024-09-30", "units": {"band1": "inches"}},
        "angola_population": {"file": "ago_ppp_2020_1km_Aggregated_UNadj.tif", "kind": "raster",
            "title": "Angola population count, WorldPop 2020", "edition": "2020 UN-adjusted population aggregated to 1 km cells",
            "units": {"band1": "people per cell"}},
    }
