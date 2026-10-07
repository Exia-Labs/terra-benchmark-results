import copy

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from terra_bench.bivariate_oracles import bivariate_answer, check_bivariate
from terra_bench.bivariate_tasks import BIVARIATE_TASKS
from terra_bench.common import ROOT, Blocked, read
from terra_bench.fixtures import ROW_ID, TASK_ASSETS
from terra_bench.policy import authorize


def example():
    countries = gpd.GeoDataFrame({ROW_ID: ["a","b","c","d"], "ISO_A3": ["AAA","BBB","CCC","-99"]},
                                geometry=[box(i,0,i+.5,.5) for i in range(4)], crs=4326)
    tables = {"gdp": pd.DataFrame({"Country Code": ["AAA","BBB","CCC"], "2014": [0.,10,30]}),
              "electricity": pd.DataFrame({"Country Code": ["AAA","BBB","CCC"], "2014": [30.,20,None]})}
    expected = bivariate_answer("301626", countries, tables)
    frame = countries.assign(x=countries[ROW_ID].map(expected["values"]), y=countries[ROW_ID].map(expected["valuesY"]),
                             classes=countries[ROW_ID].map(expected["classes"]))
    claim = {"value_field": "x", "y_value_field": "y", "class_field": "classes", "map_layer_id": "layer"}
    artifact = {"collectionId": "out", "itemId": "item", "assetKey": "data", "item": {"properties": {
        "blue:bivariate_classification": {k: expected[k] for k in ("xBreaks","yBreaks","xUnit","yUnit")}}}}
    artifact["item"]["properties"]["blue:bivariate_classification"].update(method="quantile",requestedClasses=3)
    count = (len(expected["xBreaks"])+1)*(len(expected["yBreaks"])+1)
    categories = [{"value": i, "label": "No data" if i == 0 else "current USD per capita; kWh per capita", "color": f"#{i:06x}"} for i in range(count+1)]
    snapshot = {"mapDisplays": {"layer": {"tilesets": [{"blue:vector_presentation": {"categoryField": "classes", "categories": categories}}]}},
        "workflows": [{"nodes": [{"node_id": "map", "outputs": {"result": {**artifact,"mapReceipt":{"layerId":"layer"}}}}], "verifiedMapOutputs":{"map":True}}]}
    return frame,claim,expected,snapshot,artifact


def test_paired_oracle_preserves_single_known_measurement_and_requires_actual_map():
    frame,claim,expected,snapshot,artifact = example()
    assert expected["count"] == 2 and expected["unknownIds"] == ["c","d"]
    assert expected["values"]["c"] == 30 and expected["classes"]["c"] == 0
    check_bivariate(frame,ROW_ID,claim,expected,snapshot,artifact)
    snapshot["workflows"][0]["verifiedMapOutputs"]["map"] = False
    with pytest.raises(Blocked, match="binding"):
        check_bivariate(frame,ROW_ID,claim,expected,snapshot,artifact)


@pytest.mark.parametrize("change",["second_value","class","units","breaks","colors"])
def test_bivariate_grader_rejects_plausible_but_wrong_results(change):
    frame,claim,expected,snapshot,artifact = example()
    if change == "second_value":
        frame.loc[0,"y"] += 1
    elif change == "class":
        frame.loc[0,"classes"] = 0
    elif change == "breaks":
        artifact["item"]["properties"]["blue:bivariate_classification"]["xBreaks"] = [999]
    else:
        for c in snapshot["mapDisplays"]["layer"]["tilesets"][0]["blue:vector_presentation"]["categories"]:
            c["label" if change == "units" else "color"] = "wrong"
    with pytest.raises(Blocked):
        check_bivariate(frame,ROW_ID,claim,expected,snapshot,artifact)


def test_derived_units_zero_denominator_and_real_questions():
    frame,_,_,_,_ = example()
    rural = pd.DataFrame({"Country Code":["AAA","BBB","CCC"],"2019":[0.,10,20]})
    total = pd.DataFrame({"Country Code":["AAA","BBB","CCC"],"2019":[100.,0,50]})
    agri = pd.DataFrame({"Country Code":["AAA","BBB","CCC"],"2019":[10.,20,30]})
    result = bivariate_answer("854050",frame,{"rural":rural,"population":total,"agriculture":agri})
    assert result["values"] == {"a":0.,"b":None,"c":40.,"d":None}
    original = {t["task_ID"].rsplit('_',1)[-1]:t["task_text"] for t in read(ROOT/'data/upstream/benchmark_set/tasks_and_reference_solutions.json')["tasks"]}
    for task,spec in BIVARIATE_TASKS.items():
        assert spec["question"] == original[task]
        assert TASK_ASSETS[task] == tuple(spec["assets"])


def test_bivariate_policy_year_and_axes_are_not_mutable():
    inputs = {"countries":{"collectionId":"country","itemId":"one","assetKey":"data"}}
    node = {"id":"class","type":"processor","processId":"vector-bivariate-classify","inputs":{
        "source":inputs["countries"],"xField":"gdp","yField":"electricity","xUnit":"current USD per capita","yUnit":"kWh per capita"}}
    manifest = {"valid":True,"approvalDigest":"exact","readiness":{"status":"ready"},"definition":{"nodes":[node]}}
    assert authorize(manifest,"301626",inputs)["approvalDigest"] == "exact"
    for key,value in [("classes",4),("xUnit","USD total"),("method","equal-interval")]:
        bad=copy.deepcopy(manifest)
        bad["definition"]["nodes"][0]["inputs"][key]=value
        with pytest.raises(Blocked):
            authorize(bad,"301626",inputs)


def test_africa_rail_comparison_preserves_unknown_and_2018_values():
    countries = gpd.GeoDataFrame(
        {ROW_ID: ["a", "b", "outside"], "ISO_A3": ["AAA", "BBB", "CCC"],
         "CONTINENT": ["Africa", "Africa", "Asia"]},
        geometry=[box(i, 0, i+.5, .5) for i in range(3)], crs=4326)
    tables = {
        "water_volume": pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC"],
                                      "2018": [1., 2., 99.], "2021": [10., 20., 999.]}),
        "rail_length": pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC"],
                                     "2018": [0., None, 99.]})}
    result = bivariate_answer("984439", countries, tables)
    assert result["ids"] == ["a", "b"] and result["count"] == 1
    assert result["values"] == {"a": 1., "b": 2.}
    assert result["valuesY"] == {"a": 0., "b": None}
    assert result["unknownIds"] == ["b"] and result["classes"]["b"] == 0
