import copy

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from terra_bench.common import Blocked
from terra_bench.fixtures import ROW_ID
from terra_bench.lake_snow import oracle
from terra_bench.policy import authorize


def test_closed_pixel_areas_threshold_and_unknown_geometry(tmp_path):
    # The qualifying square spans x=100..200, y=0..100. Twenty-four
    # inches and masked pixels are not deep snow; an interior lake is zero away.
    with rasterio.open(
        tmp_path / "snow.tif",
        "w",
        driver="GTiff",
        count=1,
        width=3,
        height=1,
        dtype="float32",
        nodata=-9999,
        crs=5070,
        transform=from_origin(0, 100, 100, 100),
    ) as ds:
        ds.write(np.array([[24, 25, -9999]], dtype="float32"), 1)
    lakes = gpd.GeoDataFrame(
        {ROW_ID: ["inside", "near", "far", "unknown"]},
        geometry=[box(110, 10, 120, 20), box(20199, 10, 20200, 20), box(20201, 10, 20202, 20), None],
        crs=5070,
    )
    lakes.to_parquet(tmp_path / "lakes.parquet")
    actual = oracle(tmp_path, {"na_lakes": {"path": "lakes.parquet"}, "snow": {"path": "snow.tif"}})
    assert actual["ids"] == ["inside", "near"]
    assert actual["unknownIds"] == ["unknown"]


def test_policy_allows_mask_class_but_not_lake_size_filter():
    inputs = {key: {"collectionId": key, "itemId": "one", "assetKey": "data"} for key in ["na_lakes", "snow"]}

    def ref(name):
        return {"$output": {"nodeId": name}}

    nodes = [
        {
            "id": "mask",
            "type": "processor",
            "processId": "raster-map-algebra",
            "inputs": {"sources": {"s": inputs["snow"]}, "expression": "where(s > 24, 1, 0)"},
        },
        {
            "id": "polygons",
            "type": "processor",
            "processId": "raster-polygonize",
            "inputs": {"source": ref("mask")},
        },
        {
            "id": "high",
            "type": "processor",
            "processId": "vector-filter",
            "inputs": {
                "source": ref("polygons"),
                "predicates": [{"field": "value", "operator": "eq", "value": 1}],
            },
        },
        {
            "id": "distance",
            "type": "processor",
            "processId": "vector-nearest-distance",
            "inputs": {
                "source": inputs["na_lakes"],
                "targets": ref("high"),
                "distanceCrs": "EPSG:5070",
                "outputField": "distance_m",
            },
        },
        {
            "id": "keep",
            "type": "processor",
            "processId": "vector-filter",
            "inputs": {
                "source": ref("distance"),
                "predicates": [{"field": "distance_m", "operator": "lt", "value": 20000}],
            },
        },
    ]
    manifest = {
        "valid": True,
        "approvalDigest": "exact",
        "readiness": {"status": "ready"},
        "definition": {"nodes": nodes},
    }
    authorize(manifest, "150069", inputs)
    bad = copy.deepcopy(manifest)
    bad["definition"]["nodes"][-1]["inputs"]["predicates"].append(
        {"field": "Shape_Area", "operator": "gt", "value": 100}
    )
    with pytest.raises(Blocked):
        authorize(bad, "150069", inputs)
