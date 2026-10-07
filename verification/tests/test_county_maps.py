import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from terra_bench.common import Blocked
from terra_bench.county_oracles import county_answer
from terra_bench.county_tasks import COUNTY_TASKS
from terra_bench.fixtures import ROW_ID, table_convert
from terra_bench.policy import authorize


def test_county_map_exact_state_join_zero_missing_and_duplicate_rejection():
    field = COUNTY_TASKS["476053"]["field"]
    counties = gpd.GeoDataFrame(
        {
            ROW_ID: ["a", "b", "c", "foreign"],
            "STATEFP": ["25", "25", "25", "36"],
            "NAME": ["Essex", "Zero", "Unknown", "Essex"],
        },
        geometry=[box(i, 0, i + 1, 1) for i in range(4)],
        crs=4326,
    )
    table = pd.DataFrame(
        {
            "County": ["Essex", "Zero", "Footnote"],
            "Number of Cases": [2.0, 0.0, None],
            field: [1.5, 0.0, None],
        }
    )
    answer = county_answer("476053", counties, table)
    assert answer["ids"] == ["a", "b", "c"] and answer["count"] == 2 and answer["unknownIds"] == ["c"]
    assert answer["values"] == {"a": 1.5, "b": 0.0, "c": None}
    with pytest.raises(Blocked, match="ambiguous"):
        county_answer("476053", counties, pd.concat([table, table.iloc[:1]]))


def test_plain_csv_conversion_preserves_footnotes_zeros_and_missing(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("County,Number of Cases,rate,\nA,0,0,\nB,2,---,\nFootnote,,,\n")
    result = table_convert(
        source, tmp_path / "out.parquet", {"format": "csv", "textFields": ["County"], "nullTokens": ["---"]}
    )
    assert result.County.tolist() == ["A", "B", "Footnote"]
    assert result.iloc[0]["Number of Cases"] == 0 and pd.isna(result.iloc[1]["rate"])
    assert len(result.columns) == 3 and pd.isna(result.iloc[2]["Number of Cases"])


def test_county_approval_denies_foreign_state_and_changed_units():
    inputs = {"counties": {"collectionId": "c", "itemId": "i", "assetKey": "data"}}
    node = {
        "id": "f",
        "type": "processor",
        "processId": "vector-filter",
        "inputs": {
            "source": inputs["counties"],
            "predicates": [{"field": "STATEFP", "operator": "eq", "value": "25"}],
        },
    }
    manifest = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {"nodes": [node]},
    }
    authorize(manifest, "476053", inputs)
    node["inputs"]["predicates"][0]["value"] = "36"
    with pytest.raises(Blocked):
        authorize(manifest, "476053", inputs)
