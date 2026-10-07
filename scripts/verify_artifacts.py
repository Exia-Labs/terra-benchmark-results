"""Compare small exported artifacts to independently generated references.

This checks artifact agreement, not whether a reference answers a benchmark task.
No network, agent, database or application service is used.
"""
import argparse
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare_geojson(actual, reference, id_field, fields):
    from shapely.geometry import shape

    def features(filename):
        document = json.loads(Path(filename).read_text())
        require(document.get("type") == "FeatureCollection", "Expected a FeatureCollection")
        require(not document.get("crs"), "Use RFC 7946 longitude/latitude GeoJSON, without a custom CRS")
        indexed = {}
        for feature in document["features"]:
            properties = feature.get("properties") or {}
            identity = feature.get("id") if id_field == "$id" else properties.get(id_field)
            require(isinstance(identity, (str, int)) and not isinstance(identity, bool), "Missing stable feature identity")
            key = (type(identity).__name__, identity)
            require(key not in indexed, "Duplicate feature identity")
            geometry = shape(feature["geometry"])
            require(not geometry.is_empty and geometry.is_valid, "Empty or invalid geometry")
            require(all(math.isfinite(v) for v in geometry.bounds), "Nonfinite geometry")
            for field in fields:
                require(field in properties, f"Missing comparison field: {field}")
            indexed[key] = (geometry, {field: properties[field] for field in fields})
        return indexed

    left, right = features(actual), features(reference)
    require(left.keys() == right.keys(), "Feature identities differ")
    for identity in left:
        require(left[identity][0].equals(right[identity][0]), "Geometry differs")
        require(left[identity][1] == right[identity][1], "Selected attributes differ")
    return {"kind": "geojson", "matches": True, "features": len(left), "fields": fields,
            "geometry_comparison": "Exact topological equality; no reprojection or tolerance"}


def compare_raster(actual, reference, atol, rtol):
    import numpy as np
    import rasterio

    require(all(math.isfinite(v) and v >= 0 for v in (atol, rtol)), "Tolerances must be finite and nonnegative")
    with rasterio.open(actual) as left, rasterio.open(reference) as right:
        require(left.crs is not None and left.crs == right.crs, "Raster CRS missing or different")
        require((left.count, left.width, left.height) == (right.count, right.width, right.height), "Raster dimensions differ")
        require(left.transform == right.transform, "Raster alignment differs")
        require((left.units, left.scales, left.offsets) == (right.units, right.scales, right.offsets), "Raster units or scaling differ")
        valid = 0
        for _, window in left.block_windows(1):
            a, b = left.read(window=window, masked=True), right.read(window=window, masked=True)
            mask = np.ma.getmaskarray(a)
            require(np.array_equal(mask, np.ma.getmaskarray(b)), "NoData masks differ")
            require(np.all(np.isfinite(a.data[~mask])) and np.all(np.isfinite(b.data[~mask])), "Unmasked nonfinite values")
            require(np.allclose(a.data[~mask], b.data[~mask], atol=atol, rtol=rtol), "Raster values differ")
            valid += int(np.count_nonzero(~mask))
        return {"kind": "raster", "matches": True, "valid_band_cells": valid, "atol": atol, "rtol": rtol}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Setup (Python 3.12+, inside a virtual environment):
  python -m pip install -r requirements-verification.txt

Examples:
  python scripts/verify_artifacts.py geojson actual.geojson reference.geojson --id-field feature_id --field rank
  python scripts/verify_artifacts.py raster actual.tif reference.tif --atol 0.001

Full verification tests:
  python -m pip install -r verification/requirements.lock
  npm run test:verification
""",
    )
    parser.add_argument("kind", choices=["geojson", "raster"])
    parser.add_argument("actual"); parser.add_argument("reference")
    parser.add_argument("--id-field", default="$id")
    parser.add_argument("--field", action="append", default=[])
    parser.add_argument("--atol", type=float, default=0)
    parser.add_argument("--rtol", type=float, default=0)
    args = parser.parse_args()
    try:
        result = compare_geojson(args.actual, args.reference, args.id_field, args.field) if args.kind == "geojson" else compare_raster(args.actual, args.reference, args.atol, args.rtol)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"matches": False, "reason": str(error)}))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))
