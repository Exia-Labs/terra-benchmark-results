"""Independent GeographicLib accumulator, not production PROJ measurement code."""
import math

import numpy as np
from geographiclib.geodesic import Geodesic
from geographiclib.polygonarea import PolygonArea


def polygon_area_km2(geometry):
    if geometry is None or geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        return None

    def ring_area(ring):
        xy = np.asarray(ring.coords)[:, :2]
        if not np.isfinite(xy).all() or (abs(xy[:, 0]) > 180 + 1e-8).any() or (abs(xy[:, 1]) > 90).any():
            return None
        if np.ptp(np.unwrap(np.deg2rad(xy[:, 0]))) > math.pi + 1e-10:
            return None
        accumulator = PolygonArea(Geodesic.WGS84, False)
        for longitude, latitude in xy:
            accumulator.AddPoint(float(latitude), float(longitude))
        return abs(accumulator.Compute(False, True)[2])

    total = 0
    for polygon in geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry]:
        rings = [ring_area(r) for r in [polygon.exterior, *polygon.interiors]]
        if any(v is None for v in rings):
            return None
        area = rings[0] - sum(rings[1:])
        if area <= 0:
            return None
        total += area
    return total / 1e6 if total > 0 else None


def country_areas(countries):
    """One physical denominator per original country key, retaining every fragment."""
    areas = countries.to_crs(4326).geometry.map(polygon_area_km2)
    totals = {}
    for code in countries.ISO_A3.unique():
        selected = areas.loc[countries.ISO_A3.eq(code)]
        totals[code] = None if selected.isna().any() else float(selected.sum())
    return countries.ISO_A3.map(totals)
