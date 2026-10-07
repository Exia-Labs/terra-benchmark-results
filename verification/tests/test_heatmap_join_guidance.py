"""A geographic selection must not acquire an impossible table-join requirement."""
import pytest

from terra_bench.heat_tasks import HEAT_TASKS, heat_protocols


@pytest.mark.parametrize("task", sorted(HEAT_TASKS))
def test_join_guidance_only_for_country_indicator_tables(task):
    spec = HEAT_TASKS[task]
    text = heat_protocols()[task]["clarification"]
    has_indicator = bool(spec.get("indicator") or spec.get("derived"))
    assert ("Country Code" in text) is has_indicator
    if has_indicator:
        assert "supplied indicator table's Country Code" in text
        assert "countries" in spec["assets"]
        assert len(spec["assets"]) >= 3


@pytest.mark.parametrize("task", ["565545", "921361"])
def test_geographic_earthquake_tasks_only_require_spatial_membership(task):
    spec = HEAT_TASKS[task]
    result = heat_protocols()[task]
    assert spec["assets"] == ["earthquakes", "countries"]
    assert result["question"] == spec["question"]
    assert "strictly within the original selected country polygons" in result["clarification"]
    assert "Join country" not in result["clarification"]
