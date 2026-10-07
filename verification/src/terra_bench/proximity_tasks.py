"""Frozen metric conventions for point-to-original-line counting questions."""

SOUTH_AMERICA = ['Argentina','Bolivia','Brazil','Chile','Colombia','Ecuador','Falkland Islands','French Guiana','Guyana','Paraguay','Peru','Suriname','Uruguay','Venezuela']
PROXIMITY_TASKS = {
    '741001': {'base':'seaports','lines':'sa_rivers','distanceCrs':'ESRI:102033','threshold':5000,'coverageCountries':SOUTH_AMERICA},
    "311281": {
        "base": "fires", "lines": "stations", "distanceCrs": "EPSG:5070",
        "threshold": 80467.2, "filter": {"IncidentTy": "WF"}, "pointTargets": True,
    },
    "418513": {
        "base": "power_stations",
        "lines": "africa_railways",
        "distanceCrs": "ESRI:102022",
        "threshold": 10000,
    },
}


def proximity_protocols():
    return {
        '741001': {
            'title':'Latin American seaports near supplied South American rivers',
            'question':'How many Latin American seaports are located within 5 km of major rivers?',
            'family':'point-line-proximity','bbox':[-118,-57,-33,35],
            'clarification':"Use every original Latin American port and every supplied FAO South America river record; major rivers means this exact supplied river network as in the reference, not an invented attribute class. The archived buffer method leaves the metric projection unspecified: freeze ESRI:102033 (South America Albers Equal Area Conic), straight transformed original segments, shortest planar distance strictly <5000 metres. This is a disclosed projected screening approximation, not geodesic or navigation distance. Preserve original geometries and IDs. Count each original port once despite multiple nearby segments. IMPORTANT: river coverage is South American, not all Latin America. Report a confirmed count from this supplied inventory, not a complete continental census. unknown_count includes missing/invalid port locations and nonqualifying ports whose COUNTRY is outside this declared source region: " + ', '.join(SOUTH_AMERICA) + ". Regional membership does not establish an exhaustive real-world river census. Do not substitute live rivers or silently drop ports. FAO-derived outputs are internal research only, not promotional publication.",
            'outputContract':"Return an inspectable selected-port artifact preserving original attributes, geometry and benchmark_row_id. Map optional. Explain projection distortion and partial river coverage. End with a fenced JSON {count:integer,unknown_count:integer,coverage_note:string,selection:{collectionId,itemId,assetKey}}. Do not describe unmatched northern ports as confirmed absence of rivers."
        },
        "311281": {
            "title": "Historical active wildfire incidents near Amtrak stations",
            "question": "How many active wildfires are currently burning within 50 miles of Amtrak stations?",
            "family": "point-line-proximity", "bbox": [-180, 18, 180, 72],
            "clarification": "Interpret current as the supplied historical incident snapshot, not today. The NIFC source is the Current Wildland Fire Incident Locations feed, whose documented selection excludes contained, controlled, out and certified incidents. The frozen file's latest ModifiedOn date is 2024-02-27; no capture instant beyond that is established. Select IncidentTy=WF only, excluding prescribed fires (RX). All original containment/control/out date fields are null. This supports feed status at its archived snapshot, not current burning or independent proof of activity. Use all original Amtrak station points, with no invented geographic filters. Within 50 international miles means shortest planar point-to-point distance strictly less than 80,467.2 metres after transformation to EPSG:5070, with no raster approximation. This is a disclosed projected screening convention, not geodesic distance or travel access. Count each original wildfire once; missing source geometry is unknown, never zero distance. Disclose the historical fire/station snapshot mismatch.",
            "outputContract": "Return the count and an inspectable selected-fire artifact preserving every original attribute, geometry and benchmark_row_id. Map optional. End with one fenced JSON object: {count:integer,unknown_count:integer,coverage_note:string,selection:{collectionId,itemId,assetKey}}. Clearly explain that the answer is historical source-snapshot screening, not today's active fires.",
        },
        "418513": {
            "title": "African power stations near railways",
            "question": "How many power stations in Africa are located within 10 km of major railways?",
            "family": "point-line-proximity",
            "bbox": [-20, -36, 55, 38],
            "clarification": "Use every original point in the supplied USGS Africa power-station file and every original line in the matching USGS Africa railway file. As in the released reference, major railways means the entire supplied railway file, not an invented class filter. Near means strictly less than 10,000 metres in ESRI:102022 (Africa Albers Equal Area Conic); transform original vertices, measure planar distance to straight transformed segments, with no densification. This explicit projection resolves the archived buffer method's unspecified CRS and is a disclosed screening approximation, not exact geodesic or route distance. Projection distortion is not corrected. Keep original IDs and geometry, count each station once even if near several railway segments. Invalid/missing point geometry is unknown, never zero distance. Use frozen 2021 compiled observations, not current data.",
            "outputContract": "Return the exact count and an inspectable selected-station artifact with original geometry and benchmark_row_id. A map is optional. End with one fenced JSON object: {count: integer, unknown_count: number of source points with unknown location, coverage_note: string, selection: {collectionId,itemId,assetKey}}. Explain the projection approximation and source edition.",
        }
    }


def proximity_answer(points, lines, task="418513"):
    import numpy as np
    import shapely

    from .common import Blocked
    from .fixtures import ROW_ID
    from .projected_population_oracle import segment_distances, segments

    spec = PROXIMITY_TASKS[task]
    for field, value in spec.get("filter", {}).items():
        points = points.loc[points[field] == value].copy()
    valid = points.geometry.notna() & ~points.geometry.is_empty & points.geometry.is_valid
    located = points.loc[valid].to_crs(spec["distanceCrs"])
    target = lines.to_crs(spec["distanceCrs"])
    xy = np.column_stack([located.geometry.x, located.geometry.y])
    if spec.get("pointTargets"):
        target_xy = np.column_stack([target.geometry.x, target.geometry.y])
        if not len(target_xy):
            raise Blocked("No station targets in the frozen source.")
        distances = np.array([np.sqrt(((target_xy - point) ** 2).sum(axis=1)).min() for point in xy])
    else:
        distances = segment_distances(xy, segments(target.geometry))
    tree = shapely.STRtree(target.geometry.to_numpy())
    ids, check = tree.query_nearest(located.geometry.to_numpy(), all_matches=False, return_distance=True)
    if len(check) != len(distances) or not np.allclose(check, distances[ids[0]], atol=1e-7, rtol=1e-10):
        raise Blocked("Independent African point-to-segment distance cross-check failed.")
    if np.any(np.abs(distances - spec["threshold"]) < 0.01):
        raise Blocked("Near-threshold station needs a declared precision convention before admission.")
    selected = located.loc[distances < spec["threshold"]]
    unknown=set(points.loc[~valid, ROW_ID])
    if spec.get('coverageCountries'):
        unknown.update(set(points.loc[~points.COUNTRY.isin(spec['coverageCountries']),ROW_ID])-set(selected[ROW_ID]))
    return {
        "family": "point-line-proximity",
        "count": len(selected),
        "ids": sorted(selected[ROW_ID]),
        "unknownIds": sorted(unknown),
        "identityField": ROW_ID,
    }
