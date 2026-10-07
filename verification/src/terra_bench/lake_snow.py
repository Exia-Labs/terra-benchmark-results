"""Lakes close to observed deep-snow pixel areas, not to contour lines."""

TASK = "150069"


def protocol():
    return {
        TASK: {
            "question": "How many major lakes in North America are within 20 km of areas with snow cover over 2 feet?",
            "title": "Lakes near observed deep-snow areas",
            "family": "water-feature-selection",
            "bbox": [-180, 18, 180, 85],
            "clarification": "Major lakes means every original lake/reservoir polygon in the supplied CEC inventory, with no added size/name/type filter. Snow is the frozen 2024-09-30 to 2025-05-20 accumulation raster, original band 1 in inches, not instantaneous snow depth. Deep-snow areas are CLOSED original pixel footprints with finite unmasked snowfall strictly >24 inches after scale/offset; preserve the grid and do not interpolate or simplify. Measure minimum distance from the full original lake geometry to the union of those observed pixel footprints in EPSG:5070, with transformed straight segments, strictly <20000 metres. A lake intersecting deep-snow area has distance zero. This corrects the released reference's distance-to-isolines shortcut, which misses lakes inside deep-snow areas. Invalid lake polygons may be linework make-valid repaired in their original CRS for measurement only; retain all polygon parts, original attributes/IDs and original geometry in the final selection. Count each lake once. The result is the number near OBSERVED deep snow in the supplied US raster, not proof of low snow or absence elsewhere in North America. NoData/outside coverage remains unknown and must be disclosed; do not turn it into a qualifying zero-snow class. Unknown_count in the JSON counts missing/empty original lake geometries only, NOT the geographic snow coverage gap. The coverage_note must explicitly explain that observed-coverage count is not an exhaustive continental assessment. Source and derived data are internal benchmark only.",
            "outputContract": "Publish an inspectable selected-lake artifact with original benchmark_row_id, attributes and geometry. Map optional. End with fenced JSON {count:integer,unknown_count:integer,coverage_note:string,selection:{collectionId,itemId,assetKey}}. State season, units, strict thresholds, projected-distance approximation and incomplete North American snow coverage.",
        }
    }


def oracle(directory, assets):
    import geopandas as gpd
    import numpy as np
    import rasterio
    import shapely
    from rasterio.features import shapes
    from shapely.geometry import shape

    from .common import Blocked
    from .fixtures import ROW_ID

    lakes = gpd.read_parquet(directory / assets["na_lakes"]["path"])
    unknown = lakes.geometry.isna() | lakes.geometry.is_empty
    base = lakes.loc[~unknown].copy()
    base.geometry = shapely.make_valid(base.geometry.to_numpy())
    base = base.to_crs(5070)
    with rasterio.open(directory / assets["snow"]["path"]) as source:
        raw = source.read(1, masked=True)
        valid = ~np.ma.getmaskarray(raw) & np.isfinite(raw.data)
        high = valid & (raw.data * source.scales[0] + source.offsets[0] > 24)
        polygons = [
            shape(geom)
            for geom, value in shapes(high.astype("uint8"), mask=high, transform=source.transform)
            if value == 1
        ]
        targets = gpd.GeoDataFrame(geometry=polygons, crs=source.crs).to_crs(5070)
    if targets.empty or not targets.is_valid.all():
        raise Blocked("Deep-snow target regions are empty or invalid")
    index, dist = shapely.STRtree(targets.geometry.to_numpy()).query_nearest(
        base.geometry.to_numpy(), all_matches=False, return_distance=True
    )
    distances = np.full(len(base), np.nan)
    distances[index[0]] = dist
    if not np.isfinite(distances).all() or np.any(np.abs(distances - 20000) < 1e-5):
        raise Blocked("Lake/snow distance is incomplete or threshold-ambiguous")
    selected = set(base.loc[distances < 20000, ROW_ID])
    cross = set(gpd.sjoin(base[[ROW_ID, "geometry"]], targets, predicate="dwithin", distance=20000)[ROW_ID])
    if selected != cross:
        raise Blocked("Lake/snow independent distance cross-check differs")
    return {
        "family": "water-feature-selection",
        "count": len(selected),
        "ids": sorted(selected),
        "unknownIds": sorted(lakes.loc[unknown, ROW_ID]),
        "identityField": ROW_ID,
        "answerConcepts": [
            ["2024", "2025"],
            ["unknown", "unobserved", "incomplete", "outside"],
            ["observed", "coverage"],
        ],
    }
