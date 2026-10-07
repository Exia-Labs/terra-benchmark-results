"""Disclosed input semantics only. No answers, reference values or recipes."""

DENSITY_CONVENTION = (
    "Derive population density as the declared year's total population divided by the complete supplied country area in km². "
    "Some countries have several original features sharing ISO_A3: sum their original polygon areas once per ISO_A3, and assign that same country density to every corresponding original feature. Do not divide a full country population by each separate fragment. Unmatched placeholder codes remain unknown. "
    "Measure WGS84 ellipsoidal area using shortest geodesic edges between original vertices, subtracting holes and summing polygon parts. "
    "Longitude roundoff up to 1e-8 degrees at ±180 is tolerated; this does not move or replace the source geometry. "
    "This is population per supplied country-geometry area, NOT an official land-only density or subnational raster. "
    "Preserve all original features. Missing population, invalid/empty geometry, nonpositive area, or polygon rings spanning more than 180 degrees after longitude unwrapping remain unknown. "
    "Do not silently repair geometry, substitute current boundaries, or drop unknown countries. "
)
