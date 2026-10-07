import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from terra_bench.fixtures import frame_metadata


@pytest.mark.parametrize("count", [0, 2])
def test_vector_fixture_publishes_observed_feature_count(count):
    frame = gpd.GeoDataFrame({"id": list(range(count))},
                             geometry=[Point(i, i) for i in range(count)], crs=4326)
    metadata = frame_metadata(frame)
    assert metadata["blue:feature_count"] == metadata["table:row_count"] == count
    assert metadata["table:columns"] == [{"name": "id", "type": "number"}]


def test_plain_table_does_not_claim_spatial_features():
    metadata = frame_metadata(pd.DataFrame({"id": [1, 2]}))
    assert metadata["table:row_count"] == 2
    assert "blue:feature_count" not in metadata
