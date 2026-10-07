import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from scripts.verify_artifacts import compare_geojson, compare_raster


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def vector(self, name, ids):
        file = self.root / name
        file.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": i, "properties": {"score": i},
             "geometry": {"type": "Point", "coordinates": [i, 0]}} for i in ids]}))
        return file

    def raster(self, name, cells, nodata=-9999):
        file = self.root / name
        with rasterio.open(file, "w", driver="GTiff", width=2, height=2, count=1,
                           dtype="float32", crs="EPSG:3857", transform=from_origin(0, 2, 1, 1), nodata=nodata) as dst:
            dst.write(np.array(cells, dtype="float32"), 1)
        return file

    def test_order_independent_identity(self):
        self.assertEqual(compare_geojson(self.vector("a.json", [1, 2]), self.vector("b.json", [2, 1]), "$id", ["score"])["features"], 2)

    def test_duplicate_and_missing_identity(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            compare_geojson(self.vector("a.json", [1, 1]), self.vector("b.json", [1]), "$id", [])
        with self.assertRaisesRegex(ValueError, "identities"):
            compare_geojson(self.vector("a.json", [1, 2]), self.vector("b.json", [1]), "$id", [])

    def test_valid_zero_and_missing_values(self):
        a = self.raster("a.tif", [[0, 2], [-9999, 4]])
        b = self.raster("b.tif", [[0, 2], [-9999, 4]])
        self.assertEqual(compare_raster(a, b, 0, 0)["valid_band_cells"], 3)
        c = self.raster("c.tif", [[-9999, 2], [-9999, 4]])
        with self.assertRaisesRegex(ValueError, "masks"):
            compare_raster(a, c, 0, 0)

    def test_value_tolerance_is_explicit(self):
        a = self.raster("a.tif", [[0, 2], [3, 4]])
        b = self.raster("b.tif", [[0, 2], [3, 4.01]])
        with self.assertRaisesRegex(ValueError, "values"):
            compare_raster(a, b, 0, 0)
        self.assertTrue(compare_raster(a, b, .011, 0)["matches"])


if __name__ == "__main__":
    unittest.main()
