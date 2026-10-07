"""Independent reference calculations. Never imported by Terra or used in its prompt."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

from .common import Blocked, digest, write
from .family_oracles import country_stat, snow_stations
from .fixtures import ROW_ID, validate_files


def snow_answer(towns, raster_path):
    eligible = towns[pd.to_numeric(towns.pop_2010, errors="raise") > 5000].copy()
    selected, unknown = [], []
    with rasterio.open(raster_path) as raster:
        projected = eligible.to_crs(raster.crs)
        # Full-raster direct indexing is cross-checked against independent window reads.
        values = raster.read(1, masked=True)
        for _, row in projected.iterrows():
            r, c = raster.index(row.geometry.x, row.geometry.y)
            if not (0 <= r < raster.height and 0 <= c < raster.width) or np.ma.is_masked(values[r, c]):
                unknown.append(row[ROW_ID])
                continue
            cell = float(raster.read(1, window=Window(c, r, 1, 1), masked=True)[0, 0])
            if cell != float(values[r, c]) or not np.isfinite(cell):
                raise Blocked("Snow oracle window/index cross-check failed.")
            if cell > 36:
                selected.append(row[ROW_ID])
    return {"ids": sorted(selected), "count": len(selected), "unknownIds": sorted(unknown),
            "eligiblePopulationRows": len(eligible), "identityField": ROW_ID,
            "coverage": "Count is for valid cells of the frozen snowfall raster; uncovered towns are unknown.",
            "semantics": {"population": ">5000", "snow": ">36 inches", "sampling": "containing pixel",
                          "populationYear": 2010, "snowSeason": "2024-09-30/2025-05-20"}}


def migration_answer(facilities, countries, migration):
    if migration["Country Code"].duplicated().any():
        raise Blocked("Migration join keys are duplicated.")
    africa = countries[countries.CONTINENT == "Africa"].copy()
    table = migration.set_index("Country Code")
    mapping = pd.to_numeric(table["2023"], errors="raise").to_dict()
    negative = africa[africa.ISO_A3.map(mapping) < 0]
    unknown = africa[africa.ISO_A3.map(mapping).isna()]
    points = facilities.to_crs(countries.crs)
    # Deliberately not Terra's implementation: per-polygon prepared predicates, then
    # a separate indexed join. A union would incorrectly absorb shared boundaries.
    from shapely.prepared import prep
    def membership(polygons):
        prepared = [prep(g) for g in polygons]
        return points.geometry.map(lambda p: any(g.contains(p) for g in prepared))
    selected = points.loc[membership(negative.geometry), ROW_ID].tolist()
    joined = gpd.sjoin(points[[ROW_ID, "geometry"]], negative[["geometry"]], how="inner", predicate="within")
    if set(selected) != set(joined[ROW_ID]):
        raise Blocked("Migration oracle cross-check failed.")
    missing = points.loc[membership(unknown.geometry), ROW_ID].tolist() if len(unknown) else []
    outside = points.loc[~membership(africa.geometry), ROW_ID].tolist()
    return {"ids": sorted(selected), "count": len(selected), "identityField": ROW_ID,
            "unknownIds": sorted(missing), "outsideGeometryIds": sorted(outside),
            "unmatchedCountries": sorted(unknown.NAME_EN.tolist()),
            "coverage": "Verified ISO_A3/Country Code correspondence, CONTINENT=Africa; outside polygons is excluded.",
            "semantics": {"migrationYear": 2023, "migration": "<0", "spatialPredicate": "within",
                          "adaptation": "Resolve country identity, not exact name spelling. Four name mismatches "
                                        "and obsolete WB_A3=ZAR are not missing migration evidence."}}


def density_answer(facilities, raster_path):
    eligible = facilities[facilities.Country == "Algeria"].copy()
    selected, unknown = [], []
    with rasterio.open(raster_path) as raster:
        points = eligible.to_crs(raster.crs)
        samples = list(raster.sample([(p.x, p.y) for p in points.geometry], masked=True))
        for (_, row), sampled in zip(points.iterrows(), samples, strict=True):
            r, c = raster.index(row.geometry.x, row.geometry.y)
            if not (0 <= r < raster.height and 0 <= c < raster.width) or np.ma.is_masked(sampled[0]):
                unknown.append(row[ROW_ID])
                continue
            value = raster.read(1, window=Window(c, r, 1, 1), masked=True)[0, 0]
            if np.ma.is_masked(value) or not np.isfinite(value):
                unknown.append(row[ROW_ID])
                continue
            if value != sampled[0]:
                raise Blocked("Density oracle sample/window cross-check failed.")
            if value > 1000:
                selected.append(row[ROW_ID])
    return {"ids": sorted(selected), "count": len(selected), "unknownIds": sorted(unknown),
            "identityField": ROW_ID, "eligibleRows": len(eligible),
            "semantics": {"density": ">1000 people/km²", "year": 2020, "sampling": "containing pixel"}}


def station_answer(stations, counties, earthquakes):
    quakes = earthquakes.to_crs(counties.crs)
    points = stations.to_crs(counties.crs)
    unknown = points.loc[points.geometry.isna() | points.geometry.is_empty | ~points.geometry.is_valid, ROW_ID].tolist()
    points = points.loc[~points[ROW_ID].isin(unknown)]
    # Independent geometry predicates plus an indexed-join cross-check. Keep
    # each county separate: unioning boundaries changes strict within semantics.
    from shapely.prepared import prep
    quake_union = quakes.geometry.union_all()
    affected = counties[counties.intersects(quake_union)]
    prepared = [prep(g) for g in affected.geometry]
    selected = points.loc[points.geometry.map(lambda p: any(g.contains(p) for g in prepared)), ROW_ID].tolist()
    matched_counties = gpd.sjoin(counties[[ROW_ID, "geometry"]], quakes[["geometry"]], predicate="intersects")
    cross = gpd.sjoin(points[[ROW_ID, "geometry"]],
                     counties.loc[counties.index.isin(matched_counties.index.unique()), ["geometry"]],
                     predicate="within")
    if set(selected) != set(cross[ROW_ID]):
        raise Blocked("Station oracle predicate/join cross-check failed.")
    return {"ids": sorted(selected), "count": len(selected), "unknownIds": sorted(unknown), "identityField": ROW_ID,
            "affectedCountyIds": sorted(affected[ROW_ID]),
            "semantics": {"countyPredicate": "intersects", "stationPredicate": "within",
                          "unknown": "missing or invalid station geometry; valid outside-coverage points do not qualify",
                          "earthquakes": "all records in archive labelled Feb142025; observed 2025-01-16/2025-02-15 UTC"}}


def build_oracles(directory):
    directory = Path(directory)
    fixtures = validate_files(directory)
    assets = fixtures["assets"]
    def vector(key):
        return gpd.read_parquet(directory / assets[key]["path"])
    from .change_oracles import change_answer
    from .change_tasks import CHANGE_TASKS
    from .water_tasks import WATER_SELECTIONS
    from .water_tasks import answer as water_answer
    builders = {
        "333321": lambda: snow_answer(vector("towns"), directory / assets["snow"]["path"]),
        "130168": lambda: migration_answer(vector("facilities"), vector("countries"),
                                           pd.read_parquet(directory / assets["migration"]["path"])),
        "332083": lambda: density_answer(vector("facilities"), directory / assets["density"]["path"]),
        "417961": lambda: station_answer(vector("stations"), vector("counties"), vector("earthquakes")),
        "883928": lambda: snow_stations(vector("stations"), directory / assets["snow"]["path"]),
        "806525": lambda: country_stat(vector("countries"), pd.read_parquet(directory / assets["water_withdrawal"]["path"]),
                                       "2021", points=vector("power_stations"), minimum=6, africa=True),
        "429627": lambda: country_stat(vector("countries"), pd.read_parquet(directory / assets["electricity"]["path"]),
                                       "2014", points=vector("power_stations").loc[lambda f: pd.to_numeric(f.DsgAttr02) > 1000], africa=True),
        "918547": lambda: country_stat(vector("countries"), pd.read_parquet(directory / assets["gdp"]["path"]),
                                       "2020", points=vector("earthquakes")),
        "977524": lambda: country_stat(vector("countries"), pd.read_parquet(directory / assets["fertility"]["path"]),
                                       "2022", income=True),
    }
    if "955741" in fixtures["tasks"]:
        from .remaining_tasks import county_fire_answer
        builders["955741"] = lambda: county_fire_answer(vector("counties"), vector("earthquakes"), vector("fires"))
    if "365343" in fixtures["tasks"]:
        from .remaining_tasks import forest_river_answer
        builders["365343"] = lambda: forest_river_answer(vector("sa_rivers"), vector("countries"), pd.read_parquet(directory / assets["forest_percent"]["path"]))
    builders.update({task: lambda task=task,spec=spec: change_answer(task,vector(spec["base"]),vector("countries"),
        {key:pd.read_parquet(directory/assets[key]["path"]) for key in spec["assets"] if key not in {"countries",spec["base"]}})
        for task,spec in CHANGE_TASKS.items()})
    builders.update({task: lambda task=task, keys=keys: water_answer(task, {key: vector(key) for key in keys})
                     for task, keys in WATER_SELECTIONS.items()})
    from .flood_tasks import FLOOD_TASKS
    from .flood_tasks import oracle as flood_oracle
    builders.update({task: lambda task=task: flood_oracle(directory, task, assets) for task in FLOOD_TASKS})
    from .lake_snow import oracle as lake_snow_oracle
    builders["150069"] = lambda: lake_snow_oracle(directory, assets)
    from .map_oracles import map_answer
    from .map_tasks import MAP_TASKS
    from .regional_tasks import assets_for
    builders.update({task: lambda task=task, key=spec[0]: map_answer(task, vector("countries"), pd.read_parquet(directory / assets[key]["path"]),
                         {k: pd.read_parquet(directory / assets[k]["path"]) for k in assets_for(task, key) if k not in {"countries", key}})
                     for task, spec in MAP_TASKS.items()})
    from .contour_oracles import contour_answer
    from .contour_tasks import CONTOUR_TASKS
    builders.update({task: lambda task=task: contour_answer(directory, task, assets) for task in CONTOUR_TASKS})
    from .bivariate_oracles import bivariate_answer
    from .bivariate_tasks import BIVARIATE_TASKS
    builders.update({task: lambda task=task, spec=spec: bivariate_answer(task, vector("countries"), {
        key: pd.read_parquet(directory / assets[key]["path"]) for key in spec["assets"] if key != "countries"}) for task, spec in BIVARIATE_TASKS.items()})
    from .heat_oracles import heat_answer
    from .heat_tasks import HEAT_TASKS
    builders.update({task:lambda task=task:heat_answer(directory,task,assets) for task in HEAT_TASKS})
    from .series_oracles import series_answer
    from .series_tasks import SERIES_TASKS
    builders.update({task:lambda task=task,spec=spec:series_answer(task,vector('countries'),
        {key:pd.read_parquet(directory/assets[key]['path']) for key in spec['assets'] if key!='countries'}) for task,spec in SERIES_TASKS.items()})
    from .county_oracles import county_answer
    from .county_tasks import COUNTY_TASKS
    builders.update({task:lambda task=task,spec=spec:county_answer(task,vector('counties'),pd.read_parquet(directory/assets[spec['table']]['path'])) for task,spec in COUNTY_TASKS.items()})
    from .county_heat_oracles import county_heat_answer
    from .county_tasks import COUNTY_HEAT_TASKS
    builders.update({task:lambda task=task:county_heat_answer(directory,task,assets) for task in COUNTY_HEAT_TASKS})
    from .population_oracles import population_answer
    from .population_tasks import POPULATION_TASKS
    builders.update({task:lambda task=task:population_answer(directory,task,assets) for task in POPULATION_TASKS})
    from .overlay_grading import overlay_answer
    from .overlay_tasks import OVERLAY_TASKS
    builders.update({task:lambda task=task:overlay_answer(directory,task,assets) for task in OVERLAY_TASKS})
    from .control_tasks import CONTROL_TASKS, control_answer
    builders.update({task:lambda task=task:control_answer(task) for task in CONTROL_TASKS})
    from .proximity_tasks import PROXIMITY_TASKS, proximity_answer
    builders.update({task: lambda task=task,spec=spec: proximity_answer(vector(spec['base']),vector(spec['lines']),task) for task,spec in PROXIMITY_TASKS.items()})
    from .snow_rail import answer as snow_rail_answer
    builders['310610'] = lambda: snow_rail_answer(directory, assets)
    from .point_count import oracle as point_count_oracle
    builders['586288'] = lambda: point_count_oracle(directory, assets)
    from .county_density import oracle as county_density_oracle
    builders['419069'] = lambda: county_density_oracle(directory, assets)
    from .snow_population import oracle as snow_population_oracle
    builders['321268'] = lambda: snow_population_oracle(directory, assets)
    results = {task: builders[task]() for task in fixtures["tasks"]}
    value = {"fixtureFingerprint": fixtures["fingerprint"], "tasks": results}
    value["fingerprint"] = digest(value)
    write(directory / "oracle.json", value)
    return value
