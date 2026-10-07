import copy

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from terra_bench.bivariate_oracles import bivariate_answer
from terra_bench.common import Blocked
from terra_bench.fixtures import ROW_ID
from terra_bench.geometry_oracles import polygon_area_km2
from terra_bench.map_oracles import map_answer
from terra_bench.policy import authorize
from terra_bench.tasks import protocol_for


def test_density_oracle_zero_missing_geography_holes_and_reversed_winding():
    polygon = Polygon(box(0, 0, 2, 2).exterior.coords, [box(0.5, 0.5, 1.5, 1.5).exterior.coords])
    area = polygon_area_km2(polygon)
    assert area == pytest.approx(36924.1745728, rel=1e-8)
    assert polygon_area_km2(
        Polygon(list(polygon.exterior.coords)[::-1], [list(polygon.interiors[0].coords)[::-1]])
    ) == pytest.approx(area)
    countries = gpd.GeoDataFrame(
        {
            ROW_ID: ["a", "b", "c", "d"],
            "ISO_A3": ["AAA", "BBB", "CCC", "DDD"],
            "SUBREGION": ["Southern Asia"] * 3 + ["Eastern Asia"],
            "CONTINENT": ["Asia"] * 4,
        },
        geometry=[polygon] * 4,
        crs=4326,
    )
    table = pd.DataFrame(
        {
            "Country Code": ["AAA", "BBB", "CCC", "DDD"],
            "2023": [0.0, area * 500, None, area * 999],
            "2021": [0.0, area * 400, None, area * 888],
        }
    )
    result = map_answer("946748", countries, table)
    assert (
        result["values"]["a"] == 0.0
        and result["values"]["b"] == pytest.approx(500.0)
        and result["values"]["c"] is None
    )
    assert result["ids"] == ["a", "b", "c"] and result["unknownIds"] == ["c"]
    forest = pd.DataFrame({"Country Code": ["AAA", "BBB", "CCC", "DDD"], "2021": [0.0, 10, 20, 30]})
    joint = bivariate_answer("958938", countries, {"population": table, "forest_percent": forest})
    assert joint["values"]["b"] == pytest.approx(400.0) and joint["valuesY"]["c"] == 20.0
    assert joint["count"] == 3 and joint["classes"]["c"] == 0
    assert polygon_area_km2(None) is None
    assert polygon_area_km2(Polygon()) is None


def test_density_policy_preserves_units_year_scope_and_original_source():
    inputs = {
        k: {"collectionId": k, "itemId": "one", "assetKey": "data"}
        for k in ["countries", "population", "forest_percent"]
    }
    node = {
        "id": "area",
        "type": "processor",
        "processId": "vector-measure",
        "inputs": {
            "source": inputs["countries"],
            "measure": "area",
            "unit": "km2",
            "outputField": "area",
            "onInvalid": "null",
        },
    }
    manifest = {
        "valid": True,
        "approvalDigest": "exact",
        "readiness": {"status": "ready"},
        "definition": {"nodes": [node]},
    }
    authorize(manifest, "946748", inputs)
    for field, value in [("measure", "length"), ("unit", "m")]:
        bad = copy.deepcopy(manifest)
        bad["definition"]["nodes"][0]["inputs"][field] = value
        with pytest.raises(Blocked):
            authorize(bad, "946748", inputs)
    scope = {
        "id": "asia",
        "type": "processor",
        "processId": "vector-filter",
        "inputs": {
            "source": inputs["countries"],
            "predicates": [{"field": "CONTINENT", "operator": "eq", "value": "Asia"}],
        },
    }
    manifest["definition"]["nodes"].append(scope)
    authorize(manifest, "958938", inputs)
    scope["inputs"]["predicates"][0]["value"] = "Europe"
    with pytest.raises(Blocked):
        authorize(manifest, "958938", inputs)
    for task in ["946748", "170096", "958938"]:
        text = protocol_for([task])["tasks"][task]["clarification"]
        assert "NOT an official land-only density" in text and "archived reference" not in text


def test_country_fragments_share_one_population_denominator():
    shapes = [box(0, 0, 1, 1), box(2, 0, 3, 1), box(4, 0, 5, 1)]
    countries = gpd.GeoDataFrame(
        {ROW_ID: ["a", "b", "c"], "ISO_A3": ["AAA", "AAA", "BBB"]}, geometry=shapes, crs=4326
    )
    a = polygon_area_km2(shapes[0])
    table = pd.DataFrame({"Country Code": ["AAA", "BBB"], "2023": [a * 1000, a * 1000]})
    result = map_answer("170096", countries, table)
    assert result["values"]["a"] == pytest.approx(500.0)
    assert result["values"]["b"] == pytest.approx(500.0)
    assert result["values"]["c"] == pytest.approx(1000.0)
