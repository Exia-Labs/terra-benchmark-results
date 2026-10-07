import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from terra_bench.common import Blocked
from terra_bench.fixtures import ROW_ID
from terra_bench.grading import check_extra_results
from terra_bench.map_oracles import map_answer
from terra_bench.tasks import protocol_for


def source(region):
    return gpd.GeoDataFrame(
        {
            ROW_ID: ["a", "b", "c", "d"],
            "ISO_A3": ["AAA", "BBB", "CCC", "DDD"],
            "NAME_EN": ["Alpha", "Beta", "Gamma", "Delta"],
            "SUBREGION": [region] * 4,
        },
        geometry=[box(i, 0, i + 0.5, 0.5) for i in range(4)],
        crs=4326,
    )


def test_net_migration_rate_ranking_not_total_and_missing_population():
    frame = source("Eastern Africa")
    table = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC", "DDD"], "2019": [100, 500, -5, 40]})
    pop = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC", "DDD"], "2019": [1000, 10000, 500, 0]})
    result = map_answer("734213", frame, table, {"population": pop})
    assert result["values"] == {"a": 100.0, "b": 50.0, "c": -10.0, "d": None}
    assert result["topCountries"] == ["Alpha", "Beta", "Gamma"]
    frame["rate"] = frame[ROW_ID].map(result["values"])
    with pytest.raises(Blocked, match="ranking"):
        check_extra_results(
            frame, ROW_ID, {"value_field": "rate", "top_countries": ["Beta", "Alpha", "Gamma"]}, result
        )
    check_extra_results(
        frame, ROW_ID, {"value_field": "rate", "top_countries": result["topCountries"]}, result
    )


def test_inferred_internal_resource_units_and_unknown_not_zero():
    frame = source("Western Asia")
    volume = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC", "DDD"], "2021": [2.0, 0.0, 5.0, 4.0]})
    share = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC", "DDD"], "2021": [20.0, 10.0, 0.0, None]})
    pop = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC", "DDD"], "2021": [1e6, 1e6, 1e6, 1e6]})
    result = map_answer("399319", frame, volume, {"population": pop, "water_withdrawal": share})
    assert result["values"] == {"a": 10000.0, "b": 0.0, "c": None, "d": None}
    assert result["unit"] == 'm³ per person per year'
    assert "not total renewable resources" in protocol_for(["399319"])["tasks"]["399319"]["clarification"]


@pytest.mark.parametrize("task,year", [("252796", "2023"), ("720409", "2022"), ("348947", "2021")])
def test_regions_use_published_aggregates_not_country_values(task, year):
    frame = source("unused")
    frame["REGION_WB"] = ["South Asia", "South Asia", "North America", "Antarctica"]
    table = pd.DataFrame(
        {
            "Country Code": ["AAA", "BBB", "CCC", "SAS", "NAC"],
            "Country Name": ["Alpha", "Beta", "Gamma", "South Asia", "North America"],
            year: [1, 2, 3, 100, 500],
        }
    )
    answer = map_answer(task, frame, table)
    assert answer["values"] == {"a": 100.0, "b": 100.0, "c": 500.0, "d": None}
    assert answer["unknownIds"] == ["d"]
    assert "REGION_WB/Country Name" in answer["semantics"]["join"]
    assert "published World Bank regional aggregates" in protocol_for([task])["tasks"][task]["clarification"]


def test_annual_resource_units_accept_spelling_not_changed_dimensions():
    from terra_bench.units import label_has_unit, same_unit
    assert same_unit('m3/person/year','m³ per person per year')
    assert label_has_unit('100–200 m3/person/year','m³ per person per year')
    assert not same_unit('m3/person','m³ per person per year')
    assert not same_unit('billion m3/person/year','m³ per person per year')
