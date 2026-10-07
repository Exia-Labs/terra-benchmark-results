import copy

import numpy as np
import pytest
import rasterio
from affine import Affine

from terra_bench.common import Blocked
from terra_bench.policy import authorize
from terra_bench.snow_population import BBOX, reference_blocks


def test_native_density_snow_strict_thresholds_unknown_and_unequal_grids(tmp_path):
    from terra_bench.population_oracles import quadrature_areas

    pop = tmp_path / "pop.tif"
    snow = tmp_path / "snow.tif"
    t = Affine(1, 0, 0, 0, -1, 2)
    areas = quadrature_areas(t, 2, "EPSG:4326")
    density = np.array([[1000, 1000.01, 5000, 0], [2000, 2000, 2000, 2000]], dtype="float64")
    counts = density * areas[:, None]
    counts[1, 2] = -9999
    with rasterio.open(
        pop,
        "w",
        driver="GTiff",
        width=4,
        height=2,
        count=1,
        dtype="float64",
        crs=4326,
        transform=t,
        nodata=-9999,
    ) as out:
        out.write(counts, 1)
    # Higher-resolution snow with 15 (boundary), 16, unknown, and zero.
    values = np.repeat(
        np.repeat(np.array([[16, 15, 16, 0], [16, -9999, 16, 16]], dtype="float64"), 2, axis=0), 2, axis=1
    )
    with rasterio.open(
        snow,
        "w",
        driver="GTiff",
        width=8,
        height=4,
        count=1,
        dtype="float64",
        crs=4326,
        transform=Affine(0.5, 0, 0, 0, -0.5, 2),
        nodata=-9999,
    ) as out:
        out.write(values, 1)
    with rasterio.open(pop) as p, rasterio.open(snow) as s:
        labels = next(reference_blocks(p, s, [0, 0, 4, 2]))[0]
        assert labels.tolist() == [[0, 0, 1, 0], [1, 255, 255, 1]]
        padded = next(reference_blocks(p, s, [-1, -1, 5, 3]))[0]
        assert np.all(padded[0] == 255) and np.all(padded[-1] == 255)
        assert np.array_equal(padded[1:-1, 1:-1], labels)
        with pytest.raises(Blocked, match="aligned"):
            next(reference_blocks(p, s, [0.1, 0, 4, 2]))


def test_snow_policy_prevents_population_resampling_and_wrong_season():
    inputs = {
        k: {"collectionId": k, "itemId": "fixture", "assetKey": "data"}
        for k in ["us_population", "snow_previous"]
    }
    manifest = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [
                {
                    "id": "crop",
                    "type": "processor",
                    "processId": "spatial-clip",
                    "inputs": {"source": inputs["us_population"], "area": {"bbox": BBOX}},
                },
                {
                    "id": "snow",
                    "type": "processor",
                    "processId": "raster-align",
                    "inputs": {
                        "source": inputs["snow_previous"],
                        "match": {"$output": {"nodeId": "crop"}},
                        "resampling": "nearest",
                    },
                },
            ]
        },
    }
    authorize(manifest, "321268", inputs)
    aligned_crop = copy.deepcopy(manifest)
    aligned_crop["definition"]["nodes"][0].update(
        processId="raster-align",
        inputs={
            "source": inputs["us_population"],
            "resampling": "nearest",
            "grid": {
                "crs": "EPSG:4326",
                "bounds": BBOX,
                "width": 7561,
                "height": 4705,
                "resolutionX": 0.0083333333,
                "resolutionY": 0.0083333333,
            },
        },
    )
    authorize(aligned_crop, "321268", inputs)
    for field, value in [("width", 7560), ("resolutionX", 0.01), ("crs", "EPSG:3857")]:
        bad = copy.deepcopy(aligned_crop)
        bad["definition"]["nodes"][0]["inputs"]["grid"][field] = value
        with pytest.raises(Blocked):
            authorize(bad, "321268", inputs)
    bad = copy.deepcopy(aligned_crop)
    bad["definition"]["nodes"][0]["inputs"]["resampling"] = "bilinear"
    with pytest.raises(Blocked):
        authorize(bad, "321268", inputs)
    for method in ["bilinear", "average"]:
        bad = copy.deepcopy(manifest)
        bad["definition"]["nodes"][1]["inputs"]["resampling"] = method
        with pytest.raises(Blocked):
            authorize(bad, "321268", inputs)
    bad = copy.deepcopy(manifest)
    bad["definition"]["nodes"][1]["inputs"]["source"] = inputs["us_population"]
    with pytest.raises(Blocked):
        authorize(bad, "321268", inputs)
