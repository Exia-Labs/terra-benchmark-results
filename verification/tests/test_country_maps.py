import copy

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from terra_bench.common import ROOT, Blocked, read
from terra_bench.fixtures import ROW_ID, TASK_ASSETS
from terra_bench.grading import check_extra_results
from terra_bench.map_oracles import check_map, map_answer, reference_quantiles
from terra_bench.map_tasks import MAP_TASKS, map_protocols
from terra_bench.policy import authorize
from terra_bench.tasks import protocol_for


def fixture():
    countries = gpd.GeoDataFrame({ROW_ID: ["a", "b", "c", "d"], "ISO_A3": ["AAA", "BBB", "CCC", "-99"]},
        geometry=[box(i, 0, i + .5, .5) for i in range(4)], crs=4326)
    table = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC"], "2023": [-10., 0., 20.]})
    expected = map_answer("702855", countries, table)
    frame = countries.copy()
    frame["migration"] = [-10., 0., 20., float('nan')]
    frame["class"] = frame[ROW_ID].map(expected["classes"])
    categories = [{"value": i, "color": f"#{i:06x}", "label": "No data" if i == 0 else f"class {i} people (net migration)"}
                  for i in range(len(expected["breaks"]) + 2)]
    view = {"categoryField": "class", "categories": categories, "facets": []}
    artifact = {"collectionId": "out", "itemId": "one", "assetKey": "data", "item": {"properties": {
        "blue:numeric_classification": {"method": "quantile", "breaks": expected["breaks"]}}}}
    snapshot = {"mapDisplays": {"layer": {"tilesets": [{"blue:vector_presentation": view}]}},
        "workflows": [{"nodes": [{"node_id": "map", "outputs": {"result": {
            **artifact, "mapReceipt": {"layerId": "layer"}}}}], "verifiedMapOutputs": {"map": True}}]}
    claim = {"value_field": "migration", "class_field": "class", "map_layer_id": "layer"}
    return frame, claim, expected, snapshot, artifact


def test_independent_quantile_reference_ties_and_missing():
    assert reference_quantiles([1., 1., None, 1., 2.]) == pytest.approx([1.4])
    assert reference_quantiles([0., 0., None]) == []
    assert reference_quantiles([]) == []
    assert reference_quantiles([-10., 0., 20.]) == pytest.approx([-6., -2., 4., 12.])


def test_map_grades_all_country_values_unknown_and_actual_renderer_contract():
    frame, claim, expected, snapshot, artifact = fixture()
    assert expected["ids"] == ["a", "b", "c", "d"]
    assert expected["count"] == 3 and expected["unknownIds"] == ["d"]
    check_extra_results(frame, ROW_ID, claim, expected)
    check_map(frame, ROW_ID, claim, expected, snapshot, artifact)
    frame.loc[3, "migration"] = 0
    with pytest.raises(Blocked, match="measurement"):
        check_extra_results(frame, ROW_ID, claim, expected)


@pytest.mark.parametrize("mutation", ["class", "binding", "no_style", "same_colors", "no_units", "wrong_breaks"])
def test_plain_blue_layer_or_wrong_legend_is_not_a_thematic_map_pass(mutation):
    frame, claim, expected, snapshot, artifact = fixture()
    if mutation == "class":
        frame.loc[0, "class"] = 0
    elif mutation == "binding":
        snapshot["workflows"][0]["verifiedMapOutputs"]["map"] = False
    elif mutation == "no_style":
        snapshot["mapDisplays"] = {}
    elif mutation in {"same_colors", "no_units"}:
        for c in snapshot["mapDisplays"]["layer"]["tilesets"][0]["blue:vector_presentation"]["categories"]:
            c["color" if mutation == "same_colors" else "label"] = "#111111" if mutation == "same_colors" else "value"
    else:
        artifact["item"]["properties"]["blue:numeric_classification"]["breaks"] = [10]
    with pytest.raises(Blocked):
        check_map(frame, ROW_ID, claim, expected, snapshot, artifact)


def test_map_policy_year_units_classification_no_extra_geography():
    inputs = {key: {"collectionId": key, "itemId": "one", "assetKey": "data"} for key in ["countries", "migration"]}
    nodes = [{"id": "join", "type": "processor", "processId": "table-attribute-join", "inputs": {
        "vector": inputs["countries"], "table": inputs["migration"], "fields": ["2023"]}},
        {"id": "class", "type": "processor", "processId": "vector-classify", "inputs": {
            "source": {"$output": {"nodeId": "join"}}, "field": "2023", "method": "quantile", "classes": 5, "unit": "people (net migration)"}}]
    proposal = {"valid": True, "approvalDigest": "exact", "readiness": {"status": "ready"}, "definition": {"nodes": nodes}}
    authorize(proposal, "702855", inputs)
    for field, wrong in [("method", "equal-interval"), ("classes", 3), ("unit", "percent")]:
        bad = copy.deepcopy(proposal)
        bad["definition"]["nodes"][-1]["inputs"][field] = wrong
        with pytest.raises(Blocked):
            authorize(bad, "702855", inputs)


def test_map_questions_match_original_inventory_and_all_have_fixtures():
    original = {t["task_ID"].rsplit('_', 1)[-1]: t["task_text"] for t in read(ROOT / 'data/upstream/benchmark_set/tasks_and_reference_solutions.json')["tasks"]}
    assert len(MAP_TASKS) == 61
    for task, protocol in map_protocols().items():
        assert protocol["question"].strip() == original[task].strip()
        assert TASK_ASSETS[task][0] == "countries"
        assert protocol_for([task])["tasks"][task]["family"] == "country-choropleth"


def test_enclosing_extent_is_not_reduced_scope_or_graph_mutation():
    from terra_bench.policy import contains_fixture
    bounds = [-179.9999999999, -59.47, 180.0000000001, 83.64]
    inputs = {"countries": {"collectionId": "countries", "itemId": "one", "assetKey": "data"}}
    node = {"id": "class", "type": "processor", "processId": "vector-classify", "inputs": {
        "source": inputs["countries"], "field": "2023", "method": "quantile", "classes": 5,
        "unit": "people", "area": {"bbox": [-180, -90, 180, 90]}}}
    proposal = {"valid": True, "approvalDigest": "same", "readiness": {"status": "ready"}, "definition": {"nodes": [node]}}
    before = copy.deepcopy(proposal)
    assert authorize(proposal, "908870", inputs, fixture_bounds={"countries": bounds})["approvalDigest"] == "same"
    assert proposal == before
    assert contains_fixture({"bbox": [-180, -59.47, 180, 83.64]}, bounds)
    for crs in ("OGC:CRS84", "http://www.opengis.net/def/crs/OGC/1.3/CRS84"):
        assert contains_fixture({"bbox": [-180, -90, 180, 90], "crs": crs}, bounds)
    assert not contains_fixture({"bbox": [-180, -90, 180, 90], "crs": "EPSG:3857"}, bounds)
    for invalid in ({"bbox": [-179, -90, 180, 90]}, {"bbox": [-180, -50, 180, 90]}, {"bbox": [0, 0, 1, 1]}, {"geometry": {}}):
        assert not contains_fixture(invalid, bounds)
        node["inputs"]["area"] = invalid
        with pytest.raises(Blocked, match="clipping"):
            authorize(proposal, "908870", inputs, fixture_bounds={"countries": bounds})


def test_units_are_semantic_spellings_and_field_copy_is_not_an_extra_analysis():
    from terra_bench.units import same_unit
    assert same_unit("billion m³/year", "billion m³ per year")
    assert same_unit("people/km²", "people per km^2")
    assert not same_unit("million m³/year", "billion m³ per year")
    assert not same_unit("mW", "MW")
    assert same_unit("%", "% of population")
    assert same_unit("percent", "% of population")
    assert same_unit("percentage points", "percentage points (2021 minus 2011)")
    assert same_unit("percent of internal freshwater resources", "% of internal resources")
    assert not same_unit("percent", "percentage points")
    assert not same_unit("fraction", "% of population")
    from terra_bench.units import label_has_unit
    assert label_has_unit("10–20%", "% of population")
    assert not label_has_unit("1–2 percentage points", "% of population")
    inputs = {"water_volume": {"collectionId": "water", "itemId": "one", "assetKey": "data"}}
    node = {"id": "copy", "type": "processor", "processId": "vector-field-calculate", "inputs": {
        "source": inputs["water_volume"], "calculations": [{"expression": "(value)", "fields": {"value": "2021"},
            "outputField": "water", "unit": "billion m³/year"}]}}
    manifest = {"valid": True, "approvalDigest": "exact", "readiness": {"status": "ready"}, "definition": {"nodes": [node]}}
    assert authorize(manifest, "595832", inputs)["approvalDigest"] == "exact"
    for expression in ["value * 100", "value / 1000", "other", "abs(value)"]:
        bad = copy.deepcopy(manifest)
        bad["definition"]["nodes"][0]["inputs"]["calculations"][0]["expression"] = expression
        with pytest.raises(Blocked, match="lossless"):
            authorize(bad, "595832", inputs)
