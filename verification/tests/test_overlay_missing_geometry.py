"""Unlocated records retain their identity; missing geometry is not a new point."""

import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, Point

from terra_bench.common import Blocked, sha
from terra_bench.contour_grading import check_vector_overlay
from terra_bench.fixtures import ROW_ID


@pytest.mark.parametrize("geometry", [None, GeometryCollection(), Point(1, 2)])
def test_overlay_preserves_source_geometry_including_unlocated_records(tmp_path, monkeypatch, geometry):
    from terra_bench import contour_grading

    path = tmp_path / "source.parquet"
    gpd.GeoDataFrame({ROW_ID: ["001"]}, geometry=[geometry], crs=4326).to_parquet(path)
    selection = {"collectionId": "source", "itemId": "one", "assetKey": "data"}
    monkeypatch.setattr(contour_grading, "bound_layer", lambda *args: None)
    args = ("291123", "power", {"selection": selection, "count": 1}, ["001"], {},
            {"fixtureDirectory": str(tmp_path)},
            {"assets": {"power": {"path": path.name, "sha256": sha(path)}}},
            {"inputs": {"power": selection}}, tmp_path, 1)
    check_vector_overlay(*args)
    with pytest.raises(Blocked, match="membership"):
        check_vector_overlay(*args[:3], ["001", "missing"], *args[4:])


@pytest.mark.parametrize("actual,expected,equal", [
    (None, None, True), (None, Point(1, 2), False), (Point(1, 2), None, False),
    (GeometryCollection(), None, False), (GeometryCollection(), GeometryCollection(), True),
    (Point(1, 2), Point(1, 3), False),
])
def test_geometry_comparison_never_fabricates_a_location(actual, expected, equal):
    from terra_bench.contour_grading import same_overlay_geometry
    assert same_overlay_geometry(actual, expected) is equal
