import copy
import math

import numpy as np
import pytest
import rasterio
from affine import Affine

from terra_bench.common import ROOT, Blocked, read, sha
from terra_bench.policy import authorize
from terra_bench.population_grading import check_population_raster, grade_population
from terra_bench.population_oracles import population_answer, quadrature_areas
from terra_bench.population_tasks import POPULATION_TASKS
from terra_bench.tasks import protocol_for


def write_raster(path, values, transform=Affine(1, 0, 10, 0, -1, 2), unit="people per cell", crs="EPSG:4326"):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="float64",
        crs=crs,
        transform=transform,
        nodata=-9999,
    ) as ds:
        ds.write(np.where(np.isfinite(values), values, -9999), 1)
        ds.set_band_unit(1, unit)


def test_independent_area_quadrature_sphere_world_latitude_and_count_units():
    radius = 6371000
    grid = Affine(90, 0, -180, 0, -90, 90)
    areas = quadrature_areas(grid, 2, f"+proj=longlat +R={radius}")
    np.testing.assert_allclose(areas, 4 * math.pi * radius**2 / 8 / 1e6, rtol=1e-12)
    northern = quadrature_areas(Affine(1, 0, 0, 0, -1, 80), 1, 4326)
    equatorial = quadrature_areas(Affine(1, 0, 0, 0, -1, 1), 1, 4326)
    assert northern[0] < equatorial[0] * 0.2


def fixture(tmp_path):
    grid = Affine(0.01, 0, 10, 0, -0.01, 2)
    areas = quadrature_areas(grid, 2, 4326)
    values = areas[:, None] * np.array([[1001.0, 999.0], [0.0, 1002.0]])
    values[1, 1] = np.nan
    write_raster(tmp_path / "counts.tif", values, grid)
    expected = population_answer(tmp_path, "551060", {"angola_population": {"path": "counts.tif"}})
    return expected, values, grid


def test_population_oracle_zero_missing_threshold_and_full_denominator(tmp_path):
    expected, values, grid = fixture(tmp_path)
    assert expected["count"] == 1 and expected["unknownCount"] == 1
    assert expected["metrics"]["selected_people"] == values[0, 0]
    assert expected["metrics"]["total_people"] == np.nansum(values)
    assert expected["metrics"]["percentage"] == pytest.approx(50.05)
    ambiguous = values.copy()
    ambiguous[0, 0] = quadrature_areas(grid, 2, 4326)[0] * 1000
    write_raster(tmp_path / "counts.tif", ambiguous, grid)
    with pytest.raises(Blocked, match="ambiguous"):
        population_answer(tmp_path, "551060", {"angola_population": {"path": "counts.tif"}})


def test_complete_raster_verifier_rejects_wrong_membership_with_same_total_units_grid_mask(tmp_path):
    expected, _, grid = fixture(tmp_path)
    with np.load(tmp_path / expected["reference"]) as reference:
        selected = reference["selected"]
    path = tmp_path / "selected.tif"
    write_raster(path, selected, grid)
    check_population_raster(path, selected, expected, "people per cell")
    swapped = selected.copy()
    swapped[0] = swapped[0, ::-1]
    write_raster(path, swapped, grid)
    with pytest.raises(Blocked, match="cell-by-cell"):
        check_population_raster(path, selected, expected, "people per cell")
    for values, transform, unit in [
        (np.nan_to_num(selected), grid, "people per cell"),
        (selected, grid, "people/km2"),
        (selected, Affine(0.01, 0, 11, 0, -0.01, 2), "people per cell"),
    ]:
        write_raster(path, values, transform, unit)
        with pytest.raises(Blocked):
            check_population_raster(path, selected, expected, "people per cell")


def test_final_population_requires_artifacts_lineage_exact_metrics_and_deadline(tmp_path, monkeypatch):
    from terra_bench import population_grading

    expected, _, grid = fixture(tmp_path)
    artifacts = []
    claim = {
        "count": expected["count"],
        "unknown_count": expected["unknownCount"],
        "metrics": copy.deepcopy(expected["metrics"]),
    }
    with np.load(tmp_path / expected["reference"]) as reference:
        for key, field, unit in [
            ("selection", "selected", "people per cell"),
            ("density", "density", "people/km2"),
        ]:
            path = tmp_path / f"{key}.tif"
            write_raster(path, reference[field], grid, unit)
            artifact = {
                "collectionId": key,
                "itemId": "one",
                "assetKey": "data",
                "path": path.name,
                "sha256": sha(path),
                "finishedAt": "2026-01-01T00:00:00Z",
            }
            artifacts.append(artifact)
            claim[key] = {k: artifact[k] for k in ("collectionId", "itemId", "assetKey")}
    monkeypatch.setattr(population_grading, "trusted_reuse", lambda *args, **kwargs: artifacts)
    args = (
        "551060",
        claim,
        expected,
        {"artifacts": artifacts},
        {"fixtureDirectory": str(tmp_path)},
        {"inputs": {}},
        tmp_path,
        2e9,
    )
    grade_population(*args)
    claim["metrics"]["percentage"] += 1
    with pytest.raises(Blocked, match="totals disagree"):
        grade_population(*args)
    claim["metrics"] = expected["metrics"]
    with pytest.raises(Blocked, match="deadline"):
        grade_population(*args[:-1], 0)
    monkeypatch.setattr(population_grading, "trusted_reuse", lambda *args, **kwargs: [])
    with pytest.raises(Blocked, match="lineage"):
        grade_population(*args)


def test_population_protocols_preserve_questions_and_approval_rejects_other_sources():
    original = {
        t["task_ID"].split("_")[-1]: t["task_text"]
        for t in read(ROOT / "data/upstream/benchmark_set/tasks_and_reference_solutions.json")["tasks"]
    }
    for task, spec in POPULATION_TASKS.items():
        assert protocol_for([task])["tasks"][task]["question"] == original[task]
        if spec.get('points'):
            continue
        source = {"collectionId": "fixture", "itemId": "one", "assetKey": "data"}
        node = {
            "id": "area",
            "type": "processor",
            "processId": "raster-cell-area",
            "inputs": {"source": source, "unit": "km2"},
        }
        manifest = {
            "valid": True,
            "readiness": {"status": "ready"},
            "approvalDigest": "exact",
            "definition": {"nodes": [node]},
        }
        authorize(manifest, task, {spec["raster"]: source})
        node["inputs"]["band"] = 2
        with pytest.raises(Blocked):
            authorize(manifest, task, {spec["raster"]: source})
