"""Frozen water-source cases and independent selectors; no production calculations."""

WATER_SELECTIONS = {
    "645898": ("counties", "na_rivers"),
    "154613": ("towns", "na_lakes", "na_rivers"),
    "129699": ("na_lakes", "countries"),
}
DISTANCE_CRS = "EPSG:5070"
FIVE_MILES_M = 8046.72


def assets():
    return {
        key: {
            "file": f"northamerica_{kind}_cec_2023.shp",
            "kind": "vector",
            "title": f"North American {kind}, CEC 2023 frozen benchmark source",
            "edition": "CEC North American Environmental Atlas version 4.0 (2023), original benchmark snapshot; benchmark-only use",
        }
        for key, kind in (("na_lakes", "lakes"), ("na_rivers", "rivers"))
    }


def terms():
    return {
        key: {
            "status": "benchmark-only-user-directed",
            "license": "Original CEC notices retained; conflicting metadata not relicensed",
            "attribution": "Commission for Environmental Cooperation, North American Environmental Atlas Lakes and Rivers, 2023, version 4.0. NRCan, INEGI, CONAGUA, USGS.",
            "evidence": [
                "Pinned GeoBenchX archive and original CEC sidecars",
                "User remaining-15 benchmark-only direction, 2026-10-06",
            ],
            "finding": "Use supplied files solely for this internal benchmark under explicit user direction. Prior permission uncertainty is not a dispatch hold; no claim of broader rights.",
            "sharingRestriction": "No product reuse, source redistribution or external derived-map publication.",
        }
        for key in assets()
    }


def protocols():
    contract = (
        "Return an inspectable selected-feature artifact preserving original attributes, geometry and benchmark_row_id. "
        "End with one fenced JSON object: {count:integer,unknown_count:integer,coverage_note:string,selection:{collectionId,itemId,assetKey}}. "
    )
    result = {
        "645898": {
            "title": "Counties touching the Mississippi River",
            "question": "List and make a map of all counties that touch or include the Mississippi River",
            "family": "water-feature-selection",
            "bbox": [-100, 25, -80, 50],
            "clarification": "Use the original CEC 2023 river geometries where NameEn equals 'Mississippi River', not tributaries or similarly named rivers. Select original 2024 county polygons intersecting any selected river line, including boundary touches. Compare in the county source CRS; no buffer, simplification or clipping. Duplicate river matches count each original county once. These are intersections between generalized river/cartographic county sources, not surveyed legal shoreline determinations. Unknown_count counts missing/invalid county geometries; do not silently treat them as no intersection. Keep source editions and all original IDs. Supplied water data is for this internal benchmark only.",
            "outputContract": contract
            + "List county names and state/GEOID, add the selected counties to this map, and include map_layer_id in that JSON.",
        },
        "154613": {
            "title": "US towns near both lakes and rivers",
            "question": "How many US towns are within 5 miles of both a lake and a river?",
            "family": "water-feature-selection",
            "bbox": [-180, 18, 180, 72],
            "clarification": "Use all original US town points and all original CEC 2023 lake/reservoir polygons and river lines; no population, name, area or subtype filter. Freeze shortest planar distances in EPSG:5070 after transforming original vertices, with polygon interiors at zero distance. Each of the two distances must be strictly less than 8046.72 metres (five international miles; corrects the reference's rounded 8047). Count each original town once, even if near multiple features. This is a disclosed projected screening approximation, not geodesic or route access; no densification. Unknown_count is missing/invalid town locations. The answer is relative to supplied mapped water features, not an exhaustive real-world water inventory. No source substitutions or clipped source geometries. Internal benchmark-only use.",
            "outputContract": contract
            + "Map optional. Explain projected distance, source coverage and editions.",
        },
        "129699": {
            "title": "Lakes near Canada's mapped boundary",
            "question": "How many lakes are within 10 km of the Canadian border?",
            "family": "water-feature-selection",
            "bbox": [-180, 18, 180, 85],
            "clarification": "Use all original CEC lake/reservoir polygons and the original country polygons with NAME_EN exactly Canada. The frozen interpretation of border is Canada's complete mapped polygon boundary, including coasts and islands, not just its international land boundary. Measure shortest planar distance from each entire lake geometry to the Canadian polygon boundary after transforming original vertices to EPSG:3978, strictly less than 10000 metres. This corrects the reference's buffered-polygon overlaps operation, which is not distance to a border. Do not replace lake polygons by centroids, silently include every interior Canadian lake, densify or simplify. Explicitly make-valid invalid lake polygons for measurement using linework in the original source CRS, retaining all polygon components; retain original IDs and geometry in the selected output. This is a generalized projected screening approximation, not a surveyed international-boundary calculation. Count original lakes once; all supplied lake/reservoir types count as the inventory. Unknown_count is missing/empty original lake geometry. Source and derived data are internal benchmark only.",
            "outputContract": contract
            + "Map optional. State the boundary interpretation and projected distance limitation.",
        },
    }
    result["154613"]["clarification"] += (
        " For invalid lake targets explicitly apply linework make-valid in their original CRS, retaining every resulting polygon part and target row; do not omit the records. This is measurement preparation, not new observations."
    )
    return result


def answer(task, frames):
    import geopandas as gpd
    import numpy as np
    import shapely

    from .common import Blocked
    from .fixtures import ROW_ID

    base = frames[WATER_SELECTIONS[task][0]]
    valid = base.geometry.notna() & ~base.geometry.is_empty
    if task == "645898":
        valid &= base.geometry.is_valid
    unknown = sorted(base.loc[~valid, ROW_ID])
    located = base.loc[valid]
    if task == "645898":
        rivers = frames["na_rivers"].loc[lambda f: f.NameEn == "Mississippi River"].to_crs(base.crs)
        if rivers.empty or not rivers.is_valid.all():
            raise Blocked("Frozen Mississippi selection is absent or invalid")
        ids = set(
            gpd.sjoin(located[[ROW_ID, "geometry"]], rivers[["geometry"]], predicate="intersects")[ROW_ID]
        )
        cross = set(located.loc[located.intersects(rivers.geometry.union_all()), ROW_ID])
        if ids != cross:
            raise Blocked("Independent river/county cross-check differs")
    elif task == "129699":
        located = located.copy()
        located.geometry = shapely.make_valid(located.geometry.to_numpy())
        located = located.to_crs(3978)
        country = frames["countries"].loc[lambda f: f.NAME_EN == "Canada"].to_crs(3978)
        from shapely.geometry import LineString
        pieces = []
        for boundary in country.geometry.boundary:
            for ring in getattr(boundary, "geoms", [boundary]):
                coords = np.asarray(ring.coords)
                pieces.extend(LineString(coords[i:i+257]) for i in range(0, len(coords)-1, 256))
        borders = gpd.GeoSeries(pieces, crs=3978)
        indices, cross_distance = shapely.STRtree(borders.to_numpy()).query_nearest(
            located.geometry.to_numpy(), all_matches=False, return_distance=True
        )
        values = np.full(len(located), np.nan)
        values[indices[0]] = cross_distance
        cross = set(gpd.sjoin(located[[ROW_ID, "geometry"]], gpd.GeoDataFrame(geometry=borders), predicate="dwithin", distance=10000)[ROW_ID])
        if cross != set(located.loc[values < 10000, ROW_ID]) or np.any(np.abs(values - 10000) < 1e-5):
            raise Blocked("Canadian boundary distance cross-check or threshold precision needs investigation")
        ids = set(located.loc[values < 10000, ROW_ID])
    else:
        located = located.to_crs(DISTANCE_CRS)
        near = np.ones(len(located), dtype=bool)
        for key in ("na_lakes", "na_rivers"):
            targets = frames[key].copy()
            targets.geometry = shapely.make_valid(targets.geometry.to_numpy())
            targets = targets.to_crs(DISTANCE_CRS)
            if targets.empty or targets.geometry.isna().any() or not targets.is_valid.all():
                raise Blocked("Water distance target inventory is incomplete/invalid")
            indices, distances = shapely.STRtree(targets.geometry.to_numpy()).query_nearest(
                located.geometry.to_numpy(), all_matches=False, return_distance=True
            )
            values = np.full(len(located), np.nan)
            values[indices[0]] = distances
            # Independent within-distance spatial-join cross-check, not production code.
            cross = set(
                gpd.sjoin(
                    located[[ROW_ID, "geometry"]],
                    targets[["geometry"]],
                    predicate="dwithin",
                    distance=FIVE_MILES_M,
                )[ROW_ID]
            )
            if np.any(np.abs(values - FIVE_MILES_M) < 1e-5):
                raise Blocked("Boundary-distance precision needs a frozen decision")
            selected = values < FIVE_MILES_M
            if cross != set(located.loc[selected, ROW_ID]):
                raise Blocked("Water proximity independent cross-check differs")
            near &= selected
        ids = set(located.loc[near, ROW_ID])
    return {
        "family": "water-feature-selection",
        "count": len(ids),
        "ids": sorted(ids),
        "unknownIds": unknown,
        "identityField": ROW_ID,
        "selectionMapRequired": task == "645898",
    }
