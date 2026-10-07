import copy

import pandas as pd
import pytest

from terra_bench.common import Blocked
from terra_bench.contour_grading import check_level_legend
from terra_bench.policy import authorize
from terra_bench.proximity_tasks import SOUTH_AMERICA


def test_native_level_legend_uses_one_column_not_duplicate_column_names():
    import pandas as pd

    frame = pd.DataFrame({"level": [100., 500., 100., 500.]})
    claim = {"level_field": "level"}
    expected = {"levels": [100, 500], "unit": "people per cell"}
    view = {"categoryField": "level", "categories": [
        {"value": 100., "label": "100 people per cell", "color": "#123456"},
        {"value": 500., "label": "500 people per cell", "color": "#abcdef"},
    ]}
    check_level_legend(frame, claim, expected, view)
    for change in ("level", "color", "unit"):
        bad = copy.deepcopy(view)
        if change == "level":
            bad["categories"][1]["value"] = 501.
        elif change == "color":
            bad["categories"][1]["color"] = "#123456"
        else:
            bad["categories"][1]["label"] = "500 people per km2"
        with pytest.raises(Blocked):
            check_level_legend(frame, claim, expected, bad)


def test_level_classes_preserve_one_to_one_legend_and_units():
    frame = pd.DataFrame({"level": [50, 50, 100, 200], "class": [1, 1, 2, 3]})
    claim = {"level_field": "level"}
    expected = {"levels": [50, 100, 200], "unit": "people/km2"}
    view = {
        "categoryField": "class",
        "categories": [
            {"value": i, "label": f"{v} people/km²", "color": str(i)} for i, v in enumerate([50, 100, 200], 1)
        ],
    }
    check_level_legend(frame, claim, expected, view)
    reserved = copy.deepcopy(view)
    reserved["categories"].insert(0, {"value": 0, "label": "No data", "color": "gray"})
    check_level_legend(frame, claim, expected, reserved)
    spurious = copy.deepcopy(view)
    spurious["categories"].append({"value": 9, "label": "900 people/km²", "color": "red"})
    with pytest.raises(Blocked, match="levels"):
        check_level_legend(frame, claim, expected, spurious)
    bad = frame.copy()
    bad.loc[3, "class"] = 2
    with pytest.raises(Blocked, match="combines"):
        check_level_legend(bad, claim, expected, view)
    wrong = copy.deepcopy(view)
    wrong["categories"][0]["label"] = "50 people/m2"
    with pytest.raises(Blocked, match="units"):
        check_level_legend(frame, claim, expected, wrong)


def test_port_unknown_complement_not_additional_qualifying_filter():
    inputs = {
        k: {"collectionId": k, "itemId": "fixture", "assetKey": "data"} for k in ["seaports", "sa_rivers"]
    }
    graph = {
        "valid": True,
        "readiness": {"status": "ready"},
        "approvalDigest": "exact",
        "definition": {
            "nodes": [
                {
                    "id": "d",
                    "type": "processor",
                    "processId": "vector-nearest-distance",
                    "inputs": {
                        "source": inputs["seaports"],
                        "targets": inputs["sa_rivers"],
                        "distanceCrs": "ESRI:102033",
                        "outputField": "d_m",
                    },
                },
                {
                    "id": "u",
                    "type": "processor",
                    "processId": "vector-filter",
                    "inputs": {
                        "source": {"$output": {"nodeId": "d"}},
                        "predicates": [
                            {"field": "COUNTRY", "operator": "not-in", "value": SOUTH_AMERICA},
                            {"field": "d_m", "operator": "gte", "value": 5000},
                        ],
                    },
                },
            ]
        },
    }
    authorize(graph, "741001", inputs)
    bad = copy.deepcopy(graph)
    bad["definition"]["nodes"][1]["inputs"]["predicates"][1]["value"] = 6000
    with pytest.raises(Blocked):
        authorize(bad, "741001", inputs)
    bad = copy.deepcopy(graph)
    bad["definition"]["nodes"][1]["inputs"]["predicates"].pop(0)
    with pytest.raises(Blocked):
        authorize(bad, "741001", inputs)
