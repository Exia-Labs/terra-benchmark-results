import copy

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import Point, box

from terra_bench.common import ROOT, Blocked, read, sha
from terra_bench.fixtures import ROW_ID, TASK_ASSETS
from terra_bench.heat_grading import check_heat_values, grade_heat
from terra_bench.heat_oracles import heat_selection, heat_values
from terra_bench.heat_tasks import GRID, HEAT_TASKS, RADIUS_M
from terra_bench.policy import authorize
from terra_bench.tasks import protocol_for


def test_sampling_alias_and_geography_union_preserve_authorized_inputs():
    inputs = {k: {'collectionId': k, 'itemId': 'one', 'assetKey': 'data'} for k in ['stations', 'snow', 'states', 'earthquakes']}
    sample = {'id': 'sample', 'type': 'processor', 'processId': 'raster-sample', 'inputs': {
        'features': inputs['stations'], 'rasters': {'temporary_name': inputs['snow']}, 'bands': {'temporary_name': 1}}}
    def manifest(nodes):
        return {'valid': True, 'approvalDigest': 'exact', 'readiness': {'status': 'ready'}, 'definition': {'nodes': nodes}}
    authorize(manifest([sample]), '112207', inputs)
    for field, value in [('features', inputs['earthquakes']), ('bands', {'temporary_name': 2}), ('rasters', {})]:
        wrong = copy.deepcopy(sample)
        wrong['inputs'][field] = value
        with pytest.raises(Blocked):
            authorize(manifest([wrong]), '112207', inputs)
    union = {'id': 'union', 'type': 'processor', 'processId': 'vector-dissolve', 'inputs': {'source': inputs['states'], 'aggregations': []}}
    join = {'id': 'join', 'type': 'processor', 'processId': 'vector-spatial-join', 'inputs': {
        'target': inputs['earthquakes'], 'join': {'$output': {'nodeId': 'union'}}, 'predicate': 'intersects'}}
    authorize(manifest([union, join]), '822439', inputs)
    union['inputs']['source'] = inputs['earthquakes']
    with pytest.raises(Blocked):
        authorize(manifest([union, join]), '822439', inputs)


def test_actual_ratio_denominator_validity_is_not_an_added_analytical_threshold():
    inputs = {'countries': {'collectionId': 'countries', 'itemId': 'one', 'assetKey': 'data'}}
    calculate = {'id': 'ratio', 'type': 'processor', 'processId': 'vector-field-calculate', 'inputs': {
        'source': inputs['countries'], 'calculations': [{'fields': {'a': '2023', 'b': '2018'}, 'expression': 'a / b', 'outputField': 'ratio'}]}}
    invalid = {'id': 'unknown', 'type': 'processor', 'processId': 'vector-filter', 'inputs': {
        'source': inputs['countries'], 'combine': 'any', 'predicates': [{'field': '2018', 'operator': 'is-null'}, {'field': '2018', 'operator': 'lte', 'value': 0}]}}
    m = {'valid': True, 'readiness': {'status': 'ready'}, 'approvalDigest': 'exact', 'definition': {'nodes': [calculate, invalid]}}
    authorize(m, '253892', inputs)
    invalid['inputs']['predicates'][1]['value'] = 100
    with pytest.raises(Blocked):
        authorize(m, '253892', inputs)
    invalid['inputs']['predicates'][1].update(field='unrelated', value=0)
    with pytest.raises(Blocked):
        authorize(m, '253892', inputs)


def test_grid_outside_projection_domain_fails_before_live_admission():
    from shapely.geometry import Point

    from terra_bench.heat_oracles import heat_values
    frame = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs=4326)
    with pytest.raises(Blocked, match="projection"):
        heat_values(frame, [1], {**GRID, "bounds": [-18000000, -7350000, 18000000, 7350000]})


def test_null_coverage_diagnostics_do_not_block_valid_independent_branches():
    inputs = {"earthquakes": {"collectionId": "quakes", "itemId": "one", "assetKey": "data"}}
    node = {"id": "unknown", "type": "processor", "processId": "vector-filter", "inputs": {
        "source": inputs["earthquakes"], "combine": "any", "predicates": [
            {"field": "mag", "operator": "is-null"}, {"field": "geometry", "operator": "is-null"}]}}
    proposal = {"valid": True, "approvalDigest": "exact", "readiness": {"status": "ready"}, "definition": {"nodes": [node]}}
    authorize(proposal, "565545", inputs)
    node["inputs"]["predicates"][0] = {"field": "mag", "operator": "gte", "value": 5}
    with pytest.raises(Blocked):
        authorize(proposal, "565545", inputs)


def test_independent_binning_gaussian_non_square_zero_edges():
    grid = {"bounds": [0, 0, 7, 10], "crs": "EPSG:3857", "resolutionX": 1, "resolutionY": 2}
    pts = gpd.GeoDataFrame(geometry=[Point(3.5, 5), Point(3.5, 5), Point(6.5, 9)], crs=3857)
    raw = heat_values(pts, [1.0, 2.0, 0.0], grid, 0)
    assert raw.shape == (5, 7) and raw[2, 3] == 3 and raw.sum() == 3
    smooth = heat_values(pts, [1.0, 2.0, 0.0], grid, 3)
    kx = np.exp(-(np.arange(-4, 5) ** 2) / 2)
    kx /= kx.sum()
    ky = np.exp(-(np.arange(-2, 3) ** 2) / (2 * 0.5**2))
    ky /= ky.sum()
    np.testing.assert_allclose(smooth, 3 * np.outer(ky, kx)[:, 1:-1])
    assert smooth.sum() < 3
    with pytest.raises(Blocked, match="cover"):
        heat_values(gpd.GeoDataFrame(geometry=[Point(7, 5)], crs=3857), [1], grid, 0)


def test_heat_selection_strict_boundary_zero_missing_and_duplicate_keys():
    countries = gpd.GeoDataFrame(
        {"ISO_A3": ["AAA", "BBB", "CCC"], "CONTINENT": ["Africa"] * 3},
        geometry=[box(i, 0, i + 1, 1) for i in range(3)],
        crs=4326,
    )
    points = gpd.GeoDataFrame(
        {
            ROW_ID: ["yes", "zero", "missing", "unknown", "boundary", "unlocated"],
            "DsgAttr02": [5, 0, None, 7, 1, 2],
        },
        geometry=[Point(0.5, 0.5), Point(0.4, 0.4), Point(0.6, 0.6), Point(2.5, 0.5), Point(1, 0.5), None],
        crs=4326,
    )
    table = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC"], "2021": [100, 99, None]})
    selected, weights, unknown, unlocated = heat_selection(
        "435973", points, countries, {"water_withdrawal": table}
    )
    assert list(selected[ROW_ID]) == ["yes", "zero"] and list(weights) == [5, 0]
    assert unknown == ["missing", "unknown", "unlocated"] and unlocated == ["unlocated"]
    with pytest.raises(Blocked, match="unique"):
        heat_selection("435973", points, countries, {"water_withdrawal": pd.concat([table, table])})
    with pytest.raises(Blocked, match="Negative"):
        heat_selection("435973", points.assign(DsgAttr02=-1), countries, {"water_withdrawal": table})


def test_heatmap_full_raster_grading_rejects_wrong_grid_units_mask_values(tmp_path):
    grid = {"bounds": [0, 0, 2, 2], "crs": "EPSG:3857", "resolutionX": 1, "resolutionY": 1}
    reference = tmp_path / "reference.npz"
    values = np.array([[1.0, 0.0], [0.0, 2.0]])
    np.savez_compressed(reference, values=values)
    expected = {
        "reference": reference.name,
        "referenceSha256": sha(reference),
        "grid": grid,
        "unit": "events per grid cell",
        "tolerance": {"absolute": 1e-7, "relative": 2e-6},
    }
    output = tmp_path / "result.tif"

    def save(data=values, unit="events per grid cell", bounds=(0, 0, 2, 2)):
        with rasterio.open(
            output,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="float32",
            crs=grid["crs"],
            transform=from_bounds(*bounds, 2, 2),
            nodata=-9999,
        ) as ds:
            ds.write(data.astype("float32"), 1)
            ds.set_band_unit(1, unit)

    save()
    check_heat_values(output, expected, tmp_path)
    for kw, message in [
        ({"data": values + 1}, "pixel values"),
        ({"data": np.array([[-9999, 0], [0, 2]])}, "masked"),
        ({"unit": "people/km2"}, "units"),
        ({"bounds": (1, 0, 3, 2)}, "grid"),
    ]:
        save(**kw)
        with pytest.raises(Blocked, match=message):
            check_heat_values(output, expected, tmp_path)
    save()
    with pytest.raises(Blocked, match="checksum"):
        check_heat_values(output, {**expected, "referenceSha256": "wrong"}, tmp_path)


def test_heat_protocols_preserve_questions_policy_grid_weights_years():
    original = {
        t["task_ID"].rsplit("_", 1)[-1]: t["task_text"]
        for t in read(ROOT / "data/upstream/benchmark_set/tasks_and_reference_solutions.json")["tasks"]
    }
    for task, spec in HEAT_TASKS.items():
        assert protocol_for([task])["tasks"][task]["question"] == original[task]
        assert TASK_ASSETS[task] == tuple(spec["assets"])
        inputs = {k: {"collectionId": k, "itemId": "one", "assetKey": "data"} for k in spec["assets"]}
        settings = {
            "source": inputs[spec["base"]],
            "grid": copy.deepcopy(GRID),
            "radiusM": RADIUS_M,
            "weightField": spec.get("weight"),
            "weightUnit": spec.get("weightUnit"),
        }
        node = {"id": "density", "type": "processor", "processId": "point-density", "inputs": settings}
        manifest = {
            "valid": True,
            "approvalDigest": "exact",
            "readiness": {"status": "ready"},
            "definition": {"nodes": [node]},
        }
        authorize(manifest, task, inputs)
        for field, value in [
            ("radiusM", 1),
            ("weightField", "invented"),
            ("grid", {**GRID, "resolutionX": 50000}),
        ]:
            wrong = copy.deepcopy(manifest)
            wrong["definition"]["nodes"][0]["inputs"][field] = value
            with pytest.raises(Blocked, match="convention"):
                authorize(wrong, task, inputs)
        settings["grid"]["resolutionY"] = None
        authorize(manifest, task, inputs)


def test_heat_delivery_requires_collected_lineage_and_verified_binding(tmp_path, monkeypatch):
    from terra_bench import heat_grading

    artifact = {
        "collectionId": "a",
        "itemId": "b",
        "assetKey": "data",
        "finishedAt": "2026-01-01T00:00:00Z",
        "path": "r.tif",
        "sha256": "known",
    }
    claim = {
        "density": {k: artifact[k] for k in ("collectionId", "itemId", "assetKey")},
        "map_layer_id": "layer",
    }
    snapshot = {"artifacts": [artifact]}
    frozen = {"fixtureDirectory": str(tmp_path)}
    with pytest.raises(Blocked, match="pre-deadline"):
        grade_heat("435973", claim, {}, snapshot, frozen, {"inputs": {}}, tmp_path, 0)
    monkeypatch.setattr(heat_grading, "trusted_reuse", lambda *a, **k: [])
    with pytest.raises(Blocked, match="lineage"):
        grade_heat("435973", claim, {}, snapshot, frozen, {"inputs": {}}, tmp_path, 2e9)
    monkeypatch.setattr(heat_grading, "trusted_reuse", lambda *a, **k: [artifact])
    monkeypatch.setattr(heat_grading, "sha", lambda p: "known")
    monkeypatch.setattr(heat_grading, "check_heat_values", lambda *a, **k: None)
    with pytest.raises(Blocked, match="binding"):
        grade_heat("435973", claim, {}, snapshot, frozen, {"inputs": {}}, tmp_path, 2e9)


def test_point_attribute_scope_does_not_weight_by_identifier():
    points = gpd.GeoDataFrame(
        {
            ROW_ID: ["chile", "other", "missing"],
            "COUNTRY": ["Chile", "Brazil", None],
            "FACID_NUM": [999, 1, 2],
        },
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
        crs=4326,
    )
    selected, weights, unknown, _ = heat_selection("621471", points, None, {})
    assert list(selected[ROW_ID]) == ["chile"] and weights.tolist() == [1.0]
    assert unknown == ["missing"]


def test_state_intersection_includes_boundary_and_negative_magnitude_event():
    states = gpd.GeoDataFrame(
        {"NAME": ["California", "Nevada"]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=4326
    )
    points = gpd.GeoDataFrame(
        {ROW_ID: ["boundary", "inside", "outside"], "mag": [-1, 3, 4]},
        geometry=[Point(1, 0.5), Point(0.5, 0.5), Point(1.5, 0.5)],
        crs=4326,
    )
    selected, weights, unknown, _ = heat_selection("822439", points, states, {})
    assert set(selected[ROW_ID]) == {"boundary", "inside"} and weights.tolist() == [1.0, 1.0]
    assert unknown == []


def test_raster_threshold_weight_mask_and_off_grid_unknown(tmp_path):
    raster = tmp_path / "snow.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float64",
        crs=4326,
        transform=from_bounds(0, 0, 2, 2, 2, 2),
        nodata=-9999,
    ) as ds:
        ds.write(np.array([[40.0, 39.37], [-9999, 0]]), 1)
    points = gpd.GeoDataFrame(
        {ROW_ID: ["yes", "equal", "masked", "zero", "outside", "absent"]},
        geometry=[Point(0.5, 1.5), Point(1.5, 1.5), Point(0.5, 0.5), Point(1.5, 0.5), Point(3, 3), None],
        crs=4326,
    )
    selected, weights, unknown, unlocated = heat_selection("112207", points, None, {}, raster)
    assert selected[ROW_ID].tolist() == ["yes"] and weights.tolist() == [40.0]
    assert selected.snow_depth.tolist() == [40.0]
    assert unknown == ["absent", "masked", "outside"] and unlocated == ["absent"]


def test_population_event_context_retains_zero_but_not_missing(tmp_path):
    raster = tmp_path / "population.tif"
    with rasterio.open(raster, "w", driver="GTiff", width=2, height=2,
                       count=1, dtype="float64", crs=4326,
                       transform=from_bounds(0, 0, 2, 2, 2, 2), nodata=-9999) as ds:
        ds.write(np.array([[10.0, 0.0], [-9999, np.nan]]), 1)
    points = gpd.GeoDataFrame(
        {ROW_ID: ["positive", "zero", "masked", "nan", "outside", "absent", "repeat"]},
        geometry=[Point(.5, 1.5), Point(1.5, 1.5), Point(.5, .5), Point(1.5, .5),
                  Point(3, 3), None, Point(.5, 1.5)], crs=4326)
    selected, weights, unknown, unlocated = heat_selection("367674", points, None, {}, raster)
    assert selected[ROW_ID].tolist() == ["positive", "zero", "repeat"]
    assert weights.tolist() == [10.0, 0.0, 10.0]
    assert selected.population_at_event.tolist() == weights.tolist()
    assert unknown == ["absent", "masked", "nan", "outside"]
    assert unlocated == ["absent"]
